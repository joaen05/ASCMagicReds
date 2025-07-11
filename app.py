from flask import Flask, redirect, session, url_for, render_template, request, send_file, jsonify
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
import psycopg2
import os
from functools import wraps
from babel.dates import format_datetime, pytz
import datetime
from datetime import datetime
import threading
import time
import requests
import pytz
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from io import BytesIO
from models import Query



# Laad omgevingsvariabelen uit .env-bestand
load_dotenv()
ADMIN_EMAIL = "jonahaertssen05@gmail.com"
ADMIN_EMAIL2 = "denis.bienstman@hotmail.com"
ADMIN_EMAIL3 = "sandy.de.cock@hotmail.com"

# Tijdzone instellen (bijvoorbeeld 'Europe/Brussels')
TIMEZONE = pytz.timezone('Europe/Brussels')


app = Flask(__name__)
app.secret_key = os.getenv('APP_SECRET_KEY')  # Gebruik APP_SECRET_KEY uit .env

# Auth0 configuratie
oauth = OAuth(app)
auth0 = oauth.register(
    'auth0',
    client_id=os.getenv('AUTH0_CLIENT_ID'),  # Gebruik AUTH0_CLIENT_ID uit .env
    client_secret=os.getenv('AUTH0_CLIENT_SECRET'),  # Gebruik AUTH0_CLIENT_SECRET uit .env
    server_metadata_url=f"https://{os.getenv('AUTH0_DOMAIN')}/.well-known/openid-configuration",
    client_kwargs={
        'scope': 'openid profile email',
    },
)

def keep_alive():
    while True:
        try:
            # Vervang 'your-app-url' met de URL van je applicatie
            requests.get('https://ascmagicreds.onrender.com/ping')
        except:
            pass
        time.sleep(180)  # Wacht 3 minuten tussen elke ping


def get_naam():
    email = session.get('user', {}).get('userinfo', {}).get('email')
    if not email:
        return "Onbekende gebruiker"

    try:
        return Query.getFullname(email)
    except psycopg2.Error:
        return "Databasefout"

@app.context_processor
def inject_get_naam():
    return dict(get_naam=get_naam)

# Hulpfunctie om toegang te controleren
def is_email_in_database(email):
    try:
       return Query.is_email_in_db(email)
    except psycopg2.Error:
        return False

def is_naam_in_database(name):
    Query.is_name_in_db(name)

def is_authorized():
    user_info = session.get("user")
    if not user_info:
        return False
    user_email = user_info.get("userinfo", {}).get("email")
    if not user_email:
        return False
    return is_email_in_database(user_email)

# Decorator voor admin-only routes
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("is_admin", False):
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not 'user' in session:
            return redirect(url_for("no_access"))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/ping')
def ping():
    return 'OK', 200
@app.route('/')
def home():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login')
def login():
    return auth0.authorize_redirect(redirect_uri=url_for('callback', _external=True))

@app.route('/callback')
def callback():
    token = auth0.authorize_access_token()
    session['user'] = token
    user_info = token.get("userinfo", {})

    # Haal het emailadres van de gebruiker op
    user_email = user_info.get("email")

    # Controleer of het e-mailadres in de database zit
    if not is_email_in_database(user_email):
        # Als het e-mailadres niet in de database zit, log dan uit en geef een foutmelding
        session.clear()
        return redirect(url_for("no_access"))

    # Check admin status
    if user_email == ADMIN_EMAIL or user_email == ADMIN_EMAIL2 or user_email == ADMIN_EMAIL3:
        session["is_admin"] = True
    else:
        session["is_admin"] = False

    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    user_info = session.get("user")
    user_name = user_info.get("userinfo", {}).get("name", "Onbekend")
    return render_template("dashboard.html", name=user_name)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(
        f"https://{os.getenv('AUTH0_DOMAIN')}/v2/logout?returnTo={url_for('home', _external=True)}&client_id={os.getenv('AUTH0_CLIENT_ID')}"
    )

@app.route("/no_access")
def no_access():
    return render_template("noAcces.html")


@app.route('/points_list')
@login_required
def points_list():
    if not is_authorized():
        return redirect(url_for("no_access"))

    logged_in_email = session.get('user', {}).get('userinfo', {}).get('email')
    is_admin = session.get("is_admin", False)

    try:
        if is_admin:
            # Admin ziet alle leden
            leden = Query.getPointList()
            leden_dict = [
                {
                    'voornaam': lid[0],
                    'naam': lid[1],
                    'email': lid[2],
                    'puntenaantal': lid[3],
                    'is_logged_in': (lid[2] == logged_in_email)
                }
                for lid in leden
            ]
        else:
            # Normale gebruiker ziet alleen zichzelf
            lid = Query.getUserByEmail(logged_in_email)
            if lid:
                leden_dict = [{
                    'voornaam': lid[0],
                    'naam': lid[1],
                    'email': lid[2],
                    'puntenaantal': lid[3],
                    'is_logged_in': True
                }]
            else:
                leden_dict = []

        return render_template('points_list.html', leden=leden_dict, is_admin=is_admin)
    except psycopg2.Error:
        return redirect(url_for("dashboard"))
@app.route('/beheer_leden')
@login_required
@admin_required
def beheer_leden():
    try:
        leden = Query.getSortedListUsers()
        leden_dict = [{'id': lid[0], 'voornaam': lid[1], 'naam': lid[2]} for lid in leden]
        return render_template('beheer_leden.html', leden=leden_dict)
    except psycopg2.Error:
        return redirect(url_for("dashboard"))

@app.route('/add_user', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    if request.method == 'POST':
        data = {
            'voornaam': request.form['voornaam'].title(),
            'naam': request.form['naam'].title(),
            'email': request.form['email'],
            'one_account_id': int(request.form['one_account_id']),
            'adres_straat': request.form['adres_straat'],
            'adres_nr': request.form['adres_nr'],
            'adres_postcode': int(request.form['adres_postcode']),
            'adres_gemeente': request.form['adres_gemeente'],
            'rijksregisternummer': request.form['rijksregisternummer'],
            'abo_ja_nee': request.form['abo_ja_nee'],
            'telefoonnummer': request.form['telefoonnummer'],
            'puntenaantal': int(request.form['puntenaantal']),
        }

        if is_email_in_database(data['email']):
            return render_template('add_user.html', error="E-mailadres bestaat al!", **data)

        try:
            Query.addUser (data['voornaam'], data['naam'], data['email'],
                           data['one_account_id'], data['adres_straat'],
                           data['adres_nr'], data['adres_postcode'],
                           data['adres_gemeente'], data['rijksregisternummer'],
                           data['abo_ja_nee'], data['telefoonnummer'], data['puntenaantal'])

            return redirect(url_for('beheer_leden'))
        except psycopg2.Error:
            return render_template('add_user.html', error="Fout bij het toevoegen van de gebruiker.")

    # Geef lege waarden door voor de eerste keer als de gebruiker de pagina bezoekt
    empty_data = {
        'voornaam': '',
        'naam': '',
        'email': '',
        'one_account_id': '',
        'adres_straat': '',
        'adres_nr': '',
        'adres_postcode': '',
        'adres_gemeente': '',
        'rijksregisternummer': '',
        'abo_ja_nee': '',
        'telefoonnummer': '',
        'puntenaantal': ''
    }
    return render_template('add_user.html', **empty_data)

@app.route('/edit_member/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_member(id):
    try:
        if request.method == 'POST':
            # Haal de formuliergegevens op en werk het lid bij
            voornaam = request.form['voornaam'].title()
            naam = request.form['naam'].title()
            email = request.form['email']
            one_account_id = int(request.form['one_account_id'])
            adres_straat = request.form['adres_straat']
            adres_nr = request.form['adres_nr']
            adres_postcode = int(request.form['adres_postcode'])
            adres_gemeente = request.form['adres_gemeente']
            rijksregisternummer = request.form['rijksregisternummer']
            abo_ja_nee = request.form['abo_ja_nee']
            telefoonnummer = request.form['telefoonnummer']
            puntenaantal = int(request.form['puntenaantal'])

            Query.updateUser(voornaam, naam, email, one_account_id, adres_straat,
                             adres_nr, adres_postcode,adres_gemeente, rijksregisternummer,
                             abo_ja_nee, telefoonnummer, puntenaantal, id)

            # Oplossing: Omleiden naar 'beheer_leden' na een succesvolle update
            return redirect(url_for("beheer_leden"))

        else:
            # Dit deel wordt uitgevoerd bij een GET-verzoek (om het formulier te tonen)
            member = Query.getUser(id)
            if not member:
                return "Lid niet gevonden", 404

            # Zet de lid-gegevens om naar een dictionary
            keys = ['id', 'voornaam', 'naam', 'email', 'one_account_id', 'adres_straat', 'adres_nr',
                    'adres_postcode', 'adres_gemeente', 'rijksregisternummer', 'abo_ja_nee', 'telefoonnummer',
                    'puntenaantal']
            member_dict = dict(zip(keys, member))

            # Stuur de gegevens naar de template
            return render_template('edit_member.html', member=member_dict)
    except psycopg2.Error as e:
        # Foutafhandeling voor databasefouten
        print(f"Databasefout: {e}") # Log de fout voor debugging
        return redirect(url_for("beheer_leden")) # Omleiden bij een fout, ook naar beheer_leden


@app.route('/delete_member/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_member(id):
    try:
        Query.deleteUser(id)
        return redirect(url_for('beheer_leden'))
    except psycopg2.Error:
        return redirect(url_for("dashboard"))



@app.route('/inschrijven_away', methods=['GET', 'POST'])
@login_required
def inschrijven_away():
    print("inschrijven_away route wordt uitgevoerd")  # Debug-informatie

    # Haal de pagina parameter uit de URL (standaard naar 1 als deze niet bestaat)
    page = request.args.get('page', 1, type=int)
    print(f"Huidige pagina: {page}")  # Debug-informatie

    Query.setTimezone()
    now = datetime.now(pytz.timezone('Europe/Brussels')).strftime('%Y-%m-%d %H:%M:%S')

    Query.setAwayDetailIsClosed(now)

    expired_aways = Query.getClosedInschrijvingen()
    print(f"Verlopen inschrijvingen: {expired_aways}")  # Debug-informatie

    available_aways = Query.getOpenInschrijvingen()
    print(f"Aantal beschikbare aways: {len(available_aways)}")  # Debug-informatie

    # Verkrijg de huidige tijd voor de server-side logica
    current_time = datetime.now(pytz.timezone('Europe/Brussels'))
    print(f"Huidige tijd: {current_time}")  # Debug-informatie

    # Converteer de 'away_datum' en 'inschrijving_einde' naar datetime objecten
    formatted_aways = []
    for away in available_aways:
        away_id, naam, aantal_kaarten, beschrijving, away_datum_str, inschrijving_einde_str, is_closed = away

        # Converteer away_datum
        if isinstance(away_datum_str, str):
            away_datum = datetime.strptime(away_datum_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=pytz.timezone('Europe/Brussels'))
        else:
            away_datum = away_datum_str

        # Converteer inschrijving_einde
        if isinstance(inschrijving_einde_str, str):
            inschrijving_einde = datetime.strptime(inschrijving_einde_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=pytz.timezone('Europe/Brussels'))
        else:
            inschrijving_einde = inschrijving_einde_str

        formatted_aways.append((away_id, naam, aantal_kaarten, beschrijving, away_datum, inschrijving_einde, is_closed))

    # Haal de huidige gebruiker op
    user_email = session.get('user', {}).get('userinfo', {}).get('email')

    user_id = Query.getUserId(user_email)
    print(f"User ID: {user_id}")  # Debug-informatie

    # Controleer voor elke away of de gebruiker al heeft ingeschreven
    away_inschrijving_status = {}
    if user_id:
        for away in formatted_aways:
            away_id = away[0]
            status = Query.getAwayInschrijvingStatus(user_id, away_id)
            if status:
                away_inschrijving_status[away_id] = "ja"
            else:
                away_inschrijving_status[away_id] = "nee"
    print(f"Away inschrijving status: {away_inschrijving_status}")  # Debug-informatie

    # Bereken het aantal pagina's van inschrijvingen
    per_page = 1  # Aantal aways per pagina
    total_aways = len(formatted_aways)
    total_pages = (total_aways + per_page - 1) // per_page  # Berekent het totaal aantal pagina's
    print(f"Totaal aantal pagina's: {total_pages}")  # Debug-informatie

    # Bepaal welke inschrijvingen we moeten weergeven voor de huidige pagina
    start_index = (page - 1) * per_page
    end_index = min(page * per_page, total_aways)

    # Toon alleen de activiteiten voor de huidige pagina
    paginated_aways = formatted_aways[start_index:end_index]
    print(f"Paginated aways: {paginated_aways}")  # Debug-informatie


    return render_template('inschrijven_away.html',
                           available_aways=paginated_aways,
                           current_page=page,
                           total_pages=total_pages,
                           current_time=current_time,
                           format_datetime=format_datetime,
                           away_inschrijving_status=away_inschrijving_status)

@app.route('/beheren_away')
@login_required
@admin_required
def beheren_away():
    try:
        aways = Query.getAways()
        aways_dict = [{'id': away[0], 'naam': away[1],'waarde': away[2]} for away in aways]
        return render_template('beheren_away.html', aways=aways_dict)
    except psycopg2.Error:
        return redirect(url_for("dashboard"))


@app.route('/add_away', methods=['GET', 'POST'])
@login_required
@admin_required
def add_away():
    if request.method == 'POST':
        naam = request.form.get('naam', '').strip().title()  # Zorg dat 'naam' altijd een string is
        waarde = request.form.get('waarde_away')

        if not naam or not waarde:
            return render_template('add_away.html', error="Vul alle velden in!", naam=naam, waarde=waarde)

        try:
            waarde = int(waarde)  # Zorg ervoor dat de waarde een integer is
        except ValueError:
            return render_template('add_away.html', error="Waarde moet een getal zijn!", naam=naam, waarde=waarde)

        if is_naam_in_database(naam):
            return render_template('add_away.html', error="Deze away bestaat al!", naam=naam, waarde=waarde)

        try:
            Query.addAway(naam, waarde)
            return redirect(url_for('beheren_away'))  # Redirect bij succes
        except psycopg2.Error as e:
            print(f"Databasefout: {e}")  # Debug-print
            return render_template('add_away.html', error=f"Databasefout: {e}", naam=naam, waarde=waarde)
    else:
        # Render het formulier voor GET-verzoeken
        return render_template('add_away.html', naam="", waarde="")
@app.route('/edit_away/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_away(id):
    try:

        if request.method == 'POST':
            # Haal de formuliergegevens op
            naam = request.form['naam'].title()
            waarde = request.form['waarde_away']

            # Valideer de waarde
            try:
                waarde = int(waarde)  # Zorg ervoor dat de waarde een integer is
            except ValueError:
                return render_template('edit_away.html', error="Waarde moet een getal zijn!", away={'id': id, 'naam': naam, 'waarde': waarde})

            Query.updateAway(naam, waarde, id)

            return redirect(url_for('beheren_away'))  # Redirect naar de beheerpagina na succes
        else:
            away = Query.getAway(id)

            if not away:
                return "Away niet gevonden", 404

            # Maak een dictionary van de opgehaalde gegevens
            away_dict = {'id': away[0], 'naam': away[1], 'waarde': away[2]}
            return render_template('edit_away.html', away=away_dict)
    except psycopg2.Error as e:
        print(f"Databasefout: {e}")  # Debug-print
        return render_template('edit_away.html', error=f"Databasefout: {e}", away={'id': id, 'naam': '', 'waarde': ''})
@app.route('/delete_away/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_away(id):
    try:
        Query.deleteAway(id)
        return redirect(url_for('beheren_away'))
    except psycopg2.Error:
        return redirect(url_for("dashboard"))

@app.route('/aanmaken_inschrijving_away', methods=['GET', 'POST'])
@login_required
@admin_required
def aanmaken_inschrijving_away():
    # Ophalen van alle available "aways"
    available_aways = Query.getAvailableAways()

    if request.method == 'POST':
        # Haal de data van het formulier op
        away_id = request.form['away_id']
        aantal_kaarten = request.form['aantal_kaarten']
        beschrijving = request.form['beschrijving']
        away_datum = request.form['away_datum']
        inschrijving_einde = request.form['inschrijving_einde']

        # Zet de datum om naar het formaat 'YYYY-MM-DD HH:MM:SS'
        away_datum = datetime.strptime(away_datum, '%Y-%m-%dT%H:%M')  # De ontvangen datum
        inschrijving_einde = datetime.strptime(inschrijving_einde, '%Y-%m-%dT%H:%M')  # De ontvangen inschrijving eind datum

        # Zet om naar ISO 8601 formaat
        formatted_away_datum = away_datum.strftime('%Y-%m-%dT%H:%M:%S')
        formatted_inschrijving_einde = inschrijving_einde.strftime('%Y-%m-%dT%H:%M:%S')

        # Voeg de inschrijving toe aan de database
        Query.addAwayDetails(away_id, aantal_kaarten, beschrijving, formatted_away_datum, formatted_inschrijving_einde)

        return redirect(url_for('inschrijven_away'))

    # Render de template en geef de beschikbare 'aways' door
    return render_template('aanmaken_inschrijving_away.html', available_aways=available_aways)


@app.route('/bewerken_away_details/<int:away_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def bewerken_away_details(away_id):
    try:
        page = request.args.get('page', 1, type=int)  # Haal het paginanummer op


        if request.method == 'POST':
            # Haal de form-gegevens op en werk de away inschrijving bij
            away_id_new = request.form['away_id']
            aantal_kaarten = int(request.form['aantal_kaarten'])
            beschrijving = request.form['beschrijving']
            away_datum = request.form['away_datum']
            inschrijving_einde = request.form['inschrijving_einde']

            # Zet de datum om naar het juiste formaat
            away_datum = datetime.strptime(away_datum, '%Y-%m-%dT%H:%M')
            inschrijving_einde = datetime.strptime(inschrijving_einde, '%Y-%m-%dT%H:%M')

            # Zet om naar ISO 8601 formaat
            formatted_away_datum = away_datum.strftime('%Y-%m-%dT%H:%M:%S')
            formatted_inschrijving_einde = inschrijving_einde.strftime('%Y-%m-%dT%H:%M:%S')

            # Voer de update uit, inclusief de nieuwe away_id
            Query.updateAwayDetails(away_id_new, aantal_kaarten, beschrijving, formatted_away_datum, formatted_inschrijving_einde, away_id)


            # Roep de functie aan om de geselecteerde gebruikers bij te werken
            Query.update_geselecteerde_gebruikers(away_id)

            return redirect(url_for('inschrijven_away', page=page))  # Redirect naar de juiste pagina
        else:
            # Haal de bestaande gegevens op
            away_details = Query.getAwayDetails(away_id)

            # Haal alle beschikbare aways op voor de dropdown
            available_aways = Query.getAvailableAways()

            if not away_details:
                return "Away inschrijving niet gevonden", 404

            # Zet de gegevens om naar een dictionary
            keys = ['id', 'away_id', 'beschrijving', 'aantal_kaarten', 'away_datum', 'inschrijving_einde', 'is_closed']
            away_details_dict = dict(zip(keys, away_details))

            # Stuur de gegevens naar de template
            return render_template('bewerken_away_details.html', away_details=away_details_dict, available_aways=available_aways, current_page=page)
    except psycopg2.Error:
        return redirect(url_for("dashboard"))


@app.route('/verwijder_away_details/<int:away_id>', methods=['POST'])
@login_required
@admin_required
def verwijder_away_details(away_id):
    try:
        # Extra controle of het bestaat
        away = Query.getAwayDetails(away_id)
        if not away:
            print(f"Away detail met id {away_id} bestaat niet.")
            return redirect(url_for("inschrijven_away"))

        # Eerst bijbehorende user_aways verwijderen, als die bestaan
        Query.removeUserAways(away_id)

        # Verwijder het away detail
        Query.removeAwayDetails(away_id)

        print(f"Away detail met id {away_id} succesvol verwijderd.")
        return redirect(url_for('inschrijven_away'))

    except psycopg2.Error as e:
        print(f"Fout bij verwijderen van away detail {away_id}: {e}")
        return redirect(url_for("dashboard"))



@app.route('/verwerk_inschrijving', methods=['POST'])
@login_required
def verwerk_inschrijving():
    try:
        user_email = session.get('user', {}).get('userinfo', {}).get('email')
        # current_page is no longer directly used for redirection, but you might keep it for other logic
        # current_page = request.form.get('current_page', 1, type=int)

        user_id = Query.getUserId(user_email)
        if not user_id:
            # Return JSON for error
            return jsonify({'success': False, 'message': 'Gebruiker niet gevonden.'}), 400

        away_details_id = request.form.get('away_details_id')
        # Crucial change: The JavaScript is now sending 'inschrijving_status' as the key
        inschrijving_waarde = request.form.get('inschrijving_status')

        if inschrijving_waarde == "ja":
            founded_user_id = Query.getSelectedUserAwayDetails(user_id, away_details_id)
            if founded_user_id is None:
                Query.addUserAwayDetails(user_id, away_details_id)
                Query.update_geselecteerde_gebruikers(away_details_id)
                return jsonify({'success': True, 'message': 'Je bent succesvol ingeschreven!'})
            else:
                # If already registered, perhaps a different message or just success
                return jsonify({'success': True, 'message': 'Je bent al ingeschreven voor deze away.'})
        elif inschrijving_waarde == "nee":
            # Check if there's an existing registration to remove
            selected_user_id_and_away_id = Query.getSelectedUserAwayDetails(user_id, away_details_id)
            if selected_user_id_and_away_id: # This should check if a record *exists*
                Query.removeUserAwayDetails(user_id, away_details_id)
                Query.update_geselecteerde_gebruikers(away_details_id)
                return jsonify({'success': True, 'message': 'Je bent succesvol uitgeschreven!'})
            else:
                # If not registered, perhaps a different message or just success
                return jsonify({'success': True, 'message': 'Je bent niet ingeschreven voor deze away.'})
        else:
            # Handle unexpected inschrijving_waarde
            return jsonify({'success': False, 'message': 'Ongeldige inschrijvingswaarde.'}), 400

    except Exception as e:
        print(f"Fout in verwerk_inschrijving: {e}") # Log the specific error
        return jsonify({'success': False, 'message': f"Er is een interne fout opgetreden: {e}"}), 500


@app.route('/away_lijsten')
@login_required
@admin_required
def away_lijsten():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 1


        # Roep de functie aan om de geselecteerde gebruikers bij te werken voor elke away

        away_details_id = Query.getAwayDetailsId()

        away_ids = [row[0] for row in away_details_id]
        for away_id in away_ids:
            Query.update_geselecteerde_gebruikers(away_id)

        amount_aways = Query.getAmountAwayDetails()

        total_aways = amount_aways[0]
        total_pages = (total_aways + per_page - 1) // per_page
        offset = (page - 1) * per_page

        resultaten = Query.getAllUserAwayDetails(per_page, offset)

        now = datetime.now(TIMEZONE)

        formatted_resultaten = []
        for rij in resultaten:
            naam, away_datum, aantal_kaarten, gebruikers, geselecteerde_gebruikers, away_id, inschrijving_einde = rij

            if isinstance(away_datum, str):
                away_datum = TIMEZONE.localize(datetime.strptime(away_datum, '%Y-%m-%d %H:%M:%S'))
            elif isinstance(away_datum, datetime) and away_datum.tzinfo is None:
                away_datum = TIMEZONE.localize(away_datum)

            if isinstance(inschrijving_einde, str):
                inschrijving_einde = TIMEZONE.localize(datetime.strptime(inschrijving_einde, '%Y-%m-%d %H:%M:%S'))
            elif isinstance(inschrijving_einde, datetime) and inschrijving_einde.tzinfo is None:
                inschrijving_einde = TIMEZONE.localize(inschrijving_einde)

            formatted_resultaten.append((
                naam,
                away_datum,
                aantal_kaarten,
                gebruikers,
                geselecteerde_gebruikers,
                away_id,
                inschrijving_einde
            ))

        return render_template(
            "lijst_away.html",
            resultaten=formatted_resultaten,
            format_datetime=format_datetime,
            current_page=page,
            total_pages=total_pages,
            now=now
        )
    except Exception as e:
        print("Fout bij het uitvoeren van de query:", e)
        return "Er is een fout opgetreden bij het ophalen van de gegevens.", 500


@app.route('/bewerk_lijst/<int:away_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def bewerk_lijst(away_id):
    try:
        page = request.args.get('page', 1, type=int)  # Haal het paginanummer op

        geselecteerde_leden = Query.getGeselecteerdeLeden(away_id)

        niet_geselecteerde_leden = Query.getNietGeselcteerdeLeden(away_id)

        aantal_kaarten = Query.getAantalKaarten(away_id)

        leden_in_wacht = Query.getLedenInWacht(away_id)

        aantal_geselecteerde_leden = Query.getAantalGeselcteerdeLeden(away_id)

        return render_template('bewerk_lijst.html',
                              geselecteerde_leden=geselecteerde_leden,
                              niet_geselecteerde_leden=niet_geselecteerde_leden,
                              aantal_kaarten=aantal_kaarten,
                              aantal_geselecteerde_leden = aantal_geselecteerde_leden,
                              away_id=away_id,
                              leden_in_wacht=leden_in_wacht,
                              current_page=page)  # Geef het paginanummer door aan de template
    except Exception as e:
        print(f"Fout bij het ophalen van de lijst: {e}")
        return redirect(url_for('away_lijsten'))


@app.route('/verwijder_lijst', methods=['POST'])
@login_required
@admin_required
def verwijder_lijst():
    # Verkrijg de away_id van het formulier
    away_id = request.form.get('away_id')

    if away_id:
        Query.removeUserAways(away_id)

        Query.removeAwayDetails(away_id)

    return redirect(url_for('away_lijsten'))


@app.route('/download_lijst/<int:away_id>')
@login_required
@admin_required
def download_lijst(away_id):
    try:
        geselecteerde_leden = Query.getGeselecteerdeLedenFinalInfo(away_id)

        away_naam = Query.getAwayNaam(away_id)

        # Maak een PDF-bestand in het geheugen
        buffer = BytesIO()
        pdf = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []

        # Definieer de stijl voor de titel
        styles = getSampleStyleSheet()
        title_style = styles['Title']
        title = Paragraph(away_naam + " away", title_style)
        elements.append(title)

        # Maak een lijst van rijen voor de tabel
        data = [["#", "Voornaam", "Achternaam", "OneID"]]
        for index, lid in enumerate(geselecteerde_leden, start=1):
            data.append([str(index), lid[0], lid[1], lid[2]])

        # Maak de tabel
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))

        elements.append(table)

        # Bouw het PDF-bestand
        pdf.build(elements)

        # Stel de buffer in om te lezen vanaf het begin
        buffer.seek(0)

        # Stuur het PDF-bestand terug als download
        return send_file(buffer, as_attachment=True, download_name="lijst "+ away_naam +".pdf", mimetype='application/pdf')

    except Exception as e:
        print(f"Fout bij het genereren van de PDF: {e}")
        return "Er is een fout opgetreden bij het genereren van de PDF.", 500

@app.route('/bevestig_lijst/<int:away_id>')
@login_required
@admin_required
def bevestig_lijst(away_id):
    try:
        away_waarde = Query.getAwayWaarde(away_id)

        geselecteerde_leden = Query.getGeselecteerdeLedenId(away_id)

        # Werk de punten van de geselecteerde leden bij
        for lid in geselecteerde_leden:
            user_id = lid[0]
            Query.updatePuntenGeselcteerdeLeden(away_waarde, user_id)

        Query.removeUserAways(away_id)

        Query.removeAwayDetails(away_id)

        return redirect(url_for('away_lijsten'))
    except Exception as e:
        print(f"Fout bij het bevestigen van de lijst: {e}")
        return "Er is een fout opgetreden bij het bevestigen van de lijst.", 500


@app.route('/vervang_gebruiker/<int:away_id>/<int:verwijderde_user_id>')
@login_required
@admin_required
def vervang_gebruiker(away_id, verwijderde_user_id):
    try:
        leden_in_wacht = Query.getAmountNietGeselecteerdeLeden(away_id)
        # Boolean: True als er leden in de wacht staan, anders False
        if not leden_in_wacht:
            # Als er geen leden in de wacht staan, stop de bewerking en geef een foutmelding terug
            return "Er zijn geen leden meer in de wachtlijst", 400

        # Stap 2: Verwijder de gebruiker helemaal uit de selectie
        Query.removeOldUser(away_id, verwijderde_user_id)

        # Stap 3: Zoek de gebruiker met de hoogste punten die nog niet geselecteerd is
        nieuwe_gebruiker = Query.getHoogsteNietgeselcteerdeLid(away_id)

        if nieuwe_gebruiker:
            nieuwe_user_id = nieuwe_gebruiker[0]

            # Stap 4: Zet deze nieuwe gebruiker in de selectie
            Query.addNieuwGeselecteerdLidAanLijst(away_id, nieuwe_user_id)


        return redirect(url_for('bewerk_lijst', away_id=away_id))

    except Exception as e:
        print(f"Fout bij vervangen gebruiker: {e}")
        return "Er is een fout opgetreden", 500


@app.route('/vervang_gebruiker_kies_vrevanger/<int:away_id>/<int:verwijderde_user_id>')
@login_required
@admin_required
def vervang_gebruiker_kies_vrevanger(away_id, verwijderde_user_id):
    try:
        oude_naam = Query.getOldnaam(verwijderde_user_id)

        lijst_mogelijke_leden = Query.getAlleMogelijkeLeden(away_id)

        return render_template('zelf_gekozen_vervanger.html', away_id=away_id,verwijderde_user_id = verwijderde_user_id,lijst_mogelijke_leden = lijst_mogelijke_leden,oude_naam = oude_naam)

    except Exception as e:
        print(f"Fout bij verwijderen gebruiker: {e}")
        return "Er is een fout opgetreden", 500


@app.route('/zelf_gekozen_vervanger', methods=['GET', 'POST'])
@login_required
@admin_required
def zelf_gekozen_vervanger():
    if request.method == 'POST':
        away_id = request.form.get('away_id')
        nieuwe_gebruiker_id = request.form.get('nieuwe_gebruiker')
        verwijderde_user_id = request.form.get('verwijderde_user_id')

        try:
            Query.removeOldUser(away_id, verwijderde_user_id)

            check = Query.getUserAndAwayIdFromUserAways(nieuwe_gebruiker_id, away_id)

            if check is None:
                Query.addLidAanList(nieuwe_gebruiker_id, away_id)
            else:
                Query.updateGeselecteerdStatus(nieuwe_gebruiker_id, away_id)

            return redirect(url_for('bewerk_lijst', away_id=away_id))

        except Exception as e:
            print(f"Fout bij vervangen gebruiker: {e}")
            return "Er is een fout opgetreden", 500

    # Als het een GET-verzoek is, render dan de template
    return render_template('zelf_gekozen_vervanger.html')



@app.route('/verwijder_gebruiker_zonder_vervangen/<int:away_id>/<int:verwijderde_user_id>')
@login_required
@admin_required
def verwijder_gebruiker_zonder_vervangen(away_id, verwijderde_user_id):
    try:
        # Stap 2: Verwijder de gebruiker helemaal uit de selectie
        Query.removeOldUser(away_id, verwijderde_user_id)

        Query.removeNietGeselecteerdeLeden(away_id)

        return redirect(url_for('bewerk_lijst', away_id=away_id))

    except Exception as e:
        print(f"Fout bij verwijderen gebruiker: {e}")
        return "Er is een fout opgetreden", 500



@app.route("/refresh_page", methods=["POST"])
def refresh_page():
    return redirect(url_for("inschrijven_away"))


@app.route('/check_closed_inschrijvingen', methods=['GET'])
def check_closed_inschrijvingen():
    try:


        # Haal alle inschrijvingen op die gesloten moeten worden

        closed_inschrijvingen = Query.getAwayDetailsIdFromGeslotenInschrijvingen()


        # Retourneer een lijst van IDs van gesloten inschrijvingen
        return {'closed_inschrijvingen': [row[0] for row in closed_inschrijvingen]}
    except Exception as e:
        print(f"Fout bij het controleren van gesloten inschrijvingen: {e}")
        return {'error': 'Er is een fout opgetreden'}, 500

@app.route('/toevoegen_lid_aan_lijst/<int:away_id>')
@login_required
@admin_required
def toevoegen_lid_aan_lijst(away_id):

    aantal_leden = Query.getAantalLedenInLijst(away_id)

    aantal_kaarten = Query.getAantalKaarten(away_id)


    if aantal_leden >= aantal_kaarten:
        return redirect(url_for('bewerk_lijst', away_id=away_id))

    lijst_mogelijke_leden = Query.getAlleMogelijkeLeden(away_id)

    return render_template('toevoegen_lid_lijst.html', away_id=away_id,
                           lijst_mogelijke_leden=lijst_mogelijke_leden)


@app.route('/verwerk_lid_toevoegen_lijst', methods=['GET', 'POST'])
@login_required
@admin_required
def verwerk_lid_toevoegen_lijst():
    if request.method == 'POST':

        away_id = request.form.get('away_id')
        nieuwe_gebruiker_id = request.form.get('nieuwe_gebruiker')

        aantal_leden = Query.getAantalLedenInLijst(away_id)

        aantal_kaarten = Query.getAantalKaarten(away_id)

        if aantal_leden >= aantal_kaarten:
            return redirect(url_for('bewerk_lijst', away_id=away_id))

        try:
            check = Query.getUserAndAwayIdFromUserAways(nieuwe_gebruiker_id, away_id)
            if check is None:
                Query.addLidAanList(nieuwe_gebruiker_id, away_id)
            else:
                Query.updateGeselecteerdStatus(away_id, nieuwe_gebruiker_id)

            return redirect(url_for('bewerk_lijst', away_id=away_id))

        except Exception as e:
            print(f"Fout bij vervangen gebruiker: {e}")
            return "Er is een fout opgetreden", 500
    return render_template('toevoegen_lid_lijst.html')



if __name__ == "__main__":
    t = threading.Thread(target=keep_alive)
    t.daemon = True
    t.start()
    app.run(host='0.0.0.0', port=10000)