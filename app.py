from flask import Flask, redirect, session, url_for, render_template, request, send_file
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
import psycopg2
from urllib.parse import urlparse
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



# Laad omgevingsvariabelen uit .env-bestand
load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_EMAIL = "jonahaertssen05@gmail.com"


try:
    # Probeer verbinding te maken met de database
    conn = psycopg2.connect(DATABASE_URL)
    print("Database connected successfully")
except Exception as e:
    print(f"Database connection error: {e}")
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
        time.sleep(300)  # Wacht 5 minuten tussen elke ping


# Functie om verbinding te maken met de PostgreSQL-database
def get_db_connection():
    result = urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        host=result.hostname,
        port=result.port,
        database=result.path[1:],  # Verwijder de eerste '/'
        user=result.username,
        password=result.password
    )
    return conn

def get_naam():
    email = session.get('user', {}).get('userinfo', {}).get('email')
    if not email:
        return "Onbekende gebruiker"

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT concat(voornaam, ' ', naam) FROM users WHERE email = %s", (email,))
        result = cursor.fetchone()
        conn.close()

        return result[0] if result else "Onbekende gebruiker"
    except psycopg2.Error:
        return "Databasefout"

@app.context_processor
def inject_get_naam():
    return dict(get_naam=get_naam)

# Hulpfunctie om toegang te controleren
def is_email_in_database(email):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE email = %s", (email,))
        result = cursor.fetchone()
        conn.close()
        return result[0] > 0
    except psycopg2.Error:
        return False

def is_naam_in_database(naam):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM aways WHERE naam = %s", (naam,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

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


def update_geselecteerde_gebruikers(away_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Haal het aantal beschikbare kaarten op voor deze away
        cursor.execute("SELECT aantal_kaarten FROM away_details WHERE id = %s", (away_id,))
        aantal_kaarten = cursor.fetchone()[0]

        # Selecteer alle ingeschreven gebruikers voor deze away, gesorteerd op punten (hoogste eerst)
        cursor.execute('''
            SELECT ua.user_id, u.puntenaantal
            FROM user_aways ua
            JOIN users u ON ua.user_id = u.id
            WHERE ua.away_id = %s
            ORDER BY u.puntenaantal DESC
        ''', (away_id,))

        ingeschreven_gebruikers = cursor.fetchall()

        # Bepaal de top X gebruikers op basis van het aantal kaarten
        top_gebruikers = [row[0] for row in ingeschreven_gebruikers[:aantal_kaarten]]

        # Als er geen gebruikers zijn, gebruik dan een lege tuple om SQL-syntaxfouten te voorkomen
        top_gebruikers_tuple = tuple(top_gebruikers) if top_gebruikers else (None,)

        # Update de `geselecteerd` kolom voor de top X gebruikers
        cursor.execute('''
            UPDATE user_aways
            SET geselecteerd = TRUE
            WHERE away_id = %s AND user_id IN %s
        ''', (away_id, top_gebruikers_tuple))

        # Zet `geselecteerd` op FALSE voor de rest van de gebruikers
        cursor.execute('''
            UPDATE user_aways
            SET geselecteerd = FALSE
            WHERE away_id = %s AND user_id NOT IN %s
        ''', (away_id, top_gebruikers_tuple))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Fout bij het bijwerken van geselecteerde gebruikers: {e}")


def vervang_geselecteerde_gebruiker(away_id, verwijderde_user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Haal de gebruiker op die de meeste punten heeft en nog niet geselecteerd is
        cursor.execute('''
            SELECT ua.user_id
            FROM user_aways ua
            JOIN users u ON ua.user_id = u.id
            WHERE ua.away_id = %s AND ua.geselecteerd = FALSE
            ORDER BY u.puntenaantal DESC
            LIMIT 1
        ''', (away_id,))

        nieuwe_gebruiker = cursor.fetchone()

        if nieuwe_gebruiker:
            nieuwe_user_id = nieuwe_gebruiker[0]

            # Update de database: verwijder oude gebruiker en voeg de nieuwe toe
            cursor.execute('''
                UPDATE user_aways
                SET geselecteerd = FALSE
                WHERE away_id = %s AND user_id = %s
            ''', (away_id, verwijderde_user_id))

            cursor.execute('''
                UPDATE user_aways
                SET geselecteerd = TRUE
                WHERE away_id = %s AND user_id = %s
            ''', (away_id, nieuwe_user_id))

            conn.commit()

        conn.close()

    except Exception as e:
        print(f"Fout bij het vervangen van een gebruiker: {e}")


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
    if user_email == ADMIN_EMAIL:
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
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT voornaam, naam, email, puntenaantal FROM users ORDER BY puntenaantal DESC")
        leden = cursor.fetchall()
        conn.close()
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
        return render_template('points_list.html', leden=leden_dict)
    except psycopg2.Error:
        return redirect(url_for("dashboard"))

@app.route('/beheer_leden')
@login_required
@admin_required
def beheer_leden():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, voornaam, naam FROM users ORDER BY naam, voornaam")
        leden = cursor.fetchall()
        conn.close()
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
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO users (voornaam, naam, email, one_account_id, adres_straat, adres_nr, adres_postcode, adres_gemeente, rijksregisternummer, abo_ja_nee, telefoonnummer, puntenaantal)
                              VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                           (data['voornaam'], data['naam'], data['email'], data['one_account_id'], data['adres_straat'], data['adres_nr'], data['adres_postcode'], data['adres_gemeente'], data['rijksregisternummer'], data['abo_ja_nee'], data['telefoonnummer'], data['puntenaantal']))
            conn.commit()
            conn.close()
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
        conn = get_db_connection()
        cursor = conn.cursor()

        if request.method == 'POST':
            # Haal de form-gegevens op en werk het lid bij
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

            cursor.execute('''UPDATE users SET 
                              voornaam = %s, naam = %s, email = %s, one_account_id = %s, adres_straat = %s, 
                              adres_nr = %s, adres_postcode = %s, adres_gemeente = %s, rijksregisternummer = %s, 
                              abo_ja_nee = %s, telefoonnummer = %s, puntenaantal = %s WHERE id = %s''',
                           (voornaam, naam, email, one_account_id, adres_straat, adres_nr, adres_postcode,
                            adres_gemeente, rijksregisternummer, abo_ja_nee, telefoonnummer, puntenaantal, id))
            conn.commit()
            conn.close()
            return redirect(url_for('beheer_leden'))
        else:
            cursor.execute("SELECT * FROM users WHERE id = %s", (id,))
            member = cursor.fetchone()
            conn.close()

            if not member:
                return "Lid niet gevonden", 404

            # Zet de member gegevens om naar een dictionary
            keys = ['id', 'voornaam', 'naam', 'email', 'one_account_id', 'adres_straat', 'adres_nr',
                    'adres_postcode', 'adres_gemeente', 'rijksregisternummer', 'abo_ja_nee', 'telefoonnummer',
                    'puntenaantal']
            member_dict = dict(zip(keys, member))

            # Stuur de gegevens naar de template
            return render_template('edit_member.html', member=member_dict)
    except psycopg2.Error:
        return redirect(url_for("dashboard"))

@app.route('/delete_member/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_member(id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = %s", (id,))
        conn.commit()
        conn.close()
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

    # Maak verbinding met de database
    conn = get_db_connection()
    cursor = conn.cursor()

    # Stel de tijdzone in op 'Europe/Brussels'
    cursor.execute("SET TIMEZONE = 'Europe/Brussels';")
    conn.commit()

    # Controleer en sluit inschrijvingen die verlopen zijn
    cursor.execute(''' 
        SELECT id, inschrijving_einde 
        FROM away_details 
        WHERE is_closed = FALSE AND inschrijving_einde < NOW()
    ''')
    expired_aways = cursor.fetchall()
    print(f"Verlopen inschrijvingen: {expired_aways}")  # Debug-informatie

    cursor.execute(''' 
        UPDATE away_details 
        SET is_closed = TRUE 
        WHERE is_closed = FALSE AND inschrijving_einde < NOW()
    ''')
    conn.commit()
    print(f"Aantal gesloten inschrijvingen: {cursor.rowcount}")  # Debug-informatie

    # Haal alle away details op die nog niet gesloten zijn
    cursor.execute(''' 
        SELECT ad.id, a.naam, ad.aantal_kaarten, ad.beschrijving, ad.away_datum, ad.inschrijving_einde, ad.is_closed
        FROM away_details ad
        JOIN aways a ON ad.away_id = a.id
        WHERE ad.is_closed = FALSE
        ORDER BY ad.inschrijving_einde ASC
    ''')
    available_aways = cursor.fetchall()
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
    cursor.execute("SELECT id FROM users WHERE email = %s", (user_email,))
    user_id_tuple = cursor.fetchone()
    user_id = user_id_tuple[0] if user_id_tuple else None
    print(f"User ID: {user_id}")  # Debug-informatie

    # Controleer voor elke away of de gebruiker al heeft ingeschreven
    away_inschrijving_status = {}
    if user_id:
        for away in formatted_aways:
            away_id = away[0]
            cursor.execute("SELECT 1 FROM user_aways WHERE user_id = %s AND away_id = %s", (user_id, away_id))
            if cursor.fetchone():
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

    conn.close()

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
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, naam,waarde FROM aways ORDER BY naam")
        aways = cursor.fetchall()
        conn.close()
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
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO aways (naam, waarde) VALUES (%s, %s)", (naam, waarde))
            conn.commit()
            conn.close()
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
        conn = get_db_connection()
        cursor = conn.cursor()

        if request.method == 'POST':
            # Haal de formuliergegevens op
            naam = request.form['naam'].title()
            waarde = request.form['waarde_away']

            # Valideer de waarde
            try:
                waarde = int(waarde)  # Zorg ervoor dat de waarde een integer is
            except ValueError:
                return render_template('edit_away.html', error="Waarde moet een getal zijn!", away={'id': id, 'naam': naam, 'waarde': waarde})

            # Werk de away bij in de database
            cursor.execute("UPDATE aways SET naam = %s, waarde = %s WHERE id = %s", (naam, waarde, id))
            conn.commit()
            conn.close()
            return redirect(url_for('beheren_away'))  # Redirect naar de beheerpagina na succes
        else:
            # Haal de bestaande gegevens van de away op
            cursor.execute("SELECT id, naam, waarde FROM aways WHERE id = %s", (id,))
            away = cursor.fetchone()
            conn.close()

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
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM aways WHERE id = %s", (id,))
        conn.commit()
        conn.close()
        return redirect(url_for('beheren_away'))
    except psycopg2.Error:
        return redirect(url_for("dashboard"))

@app.route('/aanmaken_inschrijving_away', methods=['GET', 'POST'])
@login_required
@admin_required
def aanmaken_inschrijving_away():
    # Ophalen van alle available "aways"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, naam FROM aways")  # Haal de id en naam op van alle 'aways'
    available_aways = cursor.fetchall()
    conn.close()

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
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO away_details (away_id, aantal_kaarten, beschrijving, away_datum, inschrijving_einde) 
                          VALUES (%s, %s, %s, %s, %s)''',
                       (away_id, aantal_kaarten, beschrijving, formatted_away_datum, formatted_inschrijving_einde))
        conn.commit()
        conn.close()

        return redirect(url_for('inschrijven_away'))

    # Render de template en geef de beschikbare 'aways' door
    return render_template('aanmaken_inschrijving_away.html', available_aways=available_aways)





@app.route('/bewerken_away_details/<int:away_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def bewerken_away_details(away_id):
    try:
        page = request.args.get('page', 1, type=int)  # Haal het paginanummer op
        conn = get_db_connection()
        cursor = conn.cursor()

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
            cursor.execute('''
                UPDATE away_details 
                SET away_id = %s, aantal_kaarten = %s, beschrijving = %s, away_datum = %s, inschrijving_einde = %s 
                WHERE id = %s
            ''', (away_id_new, aantal_kaarten, beschrijving, formatted_away_datum, formatted_inschrijving_einde, away_id))

            conn.commit()

            # Roep de functie aan om de geselecteerde gebruikers bij te werken
            update_geselecteerde_gebruikers(away_id)

            conn.close()
            return redirect(url_for('inschrijven_away', page=page))  # Redirect naar de juiste pagina
        else:
            # Haal de bestaande gegevens op
            cursor.execute("SELECT * FROM away_details WHERE id = %s", (away_id,))
            away_details = cursor.fetchone()

            # Haal alle beschikbare aways op voor de dropdown
            cursor.execute("SELECT id, naam FROM aways")
            available_aways = cursor.fetchall()

            conn.close()

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
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM away_details WHERE id = %s", (away_id,))
        conn.commit()
        conn.close()
        return redirect(url_for('inschrijven_away'))
    except psycopg2.Error:
        return redirect(url_for("dashboard"))



@app.route('/verwerk_inschrijving', methods=['POST'])
@login_required
def verwerk_inschrijving():
    try:
        user_email = session.get('user', {}).get('userinfo', {}).get('email')
        current_page = request.form.get('current_page', 1, type=int)  # Haal de huidige pagina op

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM users WHERE email = %s", (user_email,))
        user_id_tuple = cursor.fetchone()

        if user_id_tuple:
            user_id = user_id_tuple[0]  # Haal het id uit de tuple
        else:
            user_id = None  # Geen resultaat gevonden

        away_details_id = request.form.get('away_details_id')
        inschrijving_waarde = request.form.get(f'inschrijven_{away_details_id}')

        if inschrijving_waarde == "ja":
            cursor.execute('''SELECT user_id, away_id FROM user_aways WHERE user_id = %s AND away_id = %s''',
                           (user_id, away_details_id))

            if cursor.fetchone() is None:
                cursor.execute('''
                    INSERT INTO user_aways (user_id, away_id)
                    VALUES (%s, %s)
                ''', (user_id, away_details_id))

                conn.commit()

                # Roep de functie aan om de geselecteerde gebruikers bij te werken
                update_geselecteerde_gebruikers(away_details_id)

            conn.close()
            return redirect(url_for('inschrijven_away', page=current_page))  # Terug naar de huidige pagina
        else:
            cursor.execute('''SELECT user_id, away_id FROM user_aways WHERE user_id = %s AND away_id = %s''',
                           (user_id, away_details_id))

            if cursor.fetchone():
                cursor.execute('''
                    DELETE FROM user_aways WHERE user_id = %s AND away_id = %s
                ''', (user_id, away_details_id))

                conn.commit()

                # Roep de functie aan om de geselecteerde gebruikers bij te werken
                update_geselecteerde_gebruikers(away_details_id)

            conn.close()
            return redirect(url_for('inschrijven_away', page=current_page))  # Terug naar de huidige pagina
    except Exception as e:
        print(f"Fout: {e}")
        return f"Er is een fout opgetreden: {e}", 500



# Tijdzone instellen (bijvoorbeeld 'Europe/Brussels')
TIMEZONE = pytz.timezone('Europe/Brussels')

@app.route('/away_lijsten')
@login_required
@admin_required
def away_lijsten():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 1

        conn = get_db_connection()
        cursor = conn.cursor()

        # Roep de functie aan om de geselecteerde gebruikers bij te werken voor elke away
        cursor.execute("SELECT id FROM away_details")
        away_ids = [row[0] for row in cursor.fetchall()]
        for away_id in away_ids:
            update_geselecteerde_gebruikers(away_id)

        cursor.execute("SELECT COUNT(*) FROM away_details")
        total_aways = cursor.fetchone()[0]
        total_pages = (total_aways + per_page - 1) // per_page
        offset = (page - 1) * per_page

        cursor.execute("""
            SELECT 
                a.naam, 
                ad.away_datum, 
                ad.aantal_kaarten,
                CASE 
                    WHEN COUNT(u.id) = 0 THEN 'Nog geen inschrijvingen'
                    ELSE STRING_AGG(CONCAT(u.voornaam, ' ', u.naam, ' '), E'\n' ORDER BY u.naam, u.voornaam)
                END AS gebruikers,
                COALESCE(
                    STRING_AGG(
                        CASE 
                            WHEN ua.geselecteerd = TRUE THEN CONCAT(u.voornaam, ' ', u.naam, ' ')
                            ELSE NULL
                        END, 
                        E'\n' ORDER BY u.naam, u.voornaam
                    ), 
                    'Nog geen geselecteerde gebruikers'
                ) AS geselecteerde_gebruikers,
                ad.id,
                ad.inschrijving_einde
            FROM away_details ad
            JOIN aways a ON ad.away_id = a.id
            LEFT JOIN user_aways ua ON ad.id = ua.away_id
            LEFT JOIN users u ON ua.user_id = u.id
            GROUP BY a.naam, ad.away_datum, ad.aantal_kaarten, ad.id, ad.inschrijving_einde
            ORDER BY ad.away_datum
            LIMIT %s OFFSET %s
        """, (per_page, offset))

        resultaten = cursor.fetchall()
        conn.close()

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

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT u.id, u.voornaam, u.naam, u.one_account_id
            FROM users u
            JOIN user_aways ua ON u.id = ua.user_id
            WHERE ua.away_id = %s AND ua.geselecteerd = TRUE
            ORDER BY u.naam,u.voornaam
        ''', (away_id,))
        geselecteerde_leden = cursor.fetchall()

        cursor.execute('''
            SELECT u.id, u.voornaam, u.naam, u.one_account_id
            FROM users u
            LEFT JOIN user_aways ua ON u.id = ua.user_id AND ua.away_id = %s
            WHERE ua.geselecteerd IS NULL OR ua.geselecteerd = FALSE
        ''', (away_id,))
        niet_geselecteerde_leden = cursor.fetchall()

        cursor.execute("SELECT aantal_kaarten FROM away_details WHERE id = %s", (away_id,))
        aantal_kaarten = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*)
            FROM users u
            JOIN user_aways ua ON u.id = ua.user_id
            WHERE ua.away_id = %s AND ua.geselecteerd = FALSE
        """, (away_id,))
        leden_in_wacht = cursor.fetchone()[0]

        cursor.execute("SELECT count(user_id) FROM user_aways WHERE away_id = %s AND geselecteerd = TRUE", (away_id,))
        aantal_geselecteerde_leden = cursor.fetchone()[0]

        conn.close()

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
        # Maak verbinding met de database
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Verwijder eerst alle rijen uit de tabel user_aways waar away_id overeenkomt
            cursor.execute("DELETE FROM user_aways WHERE away_id = %s", (away_id,))

            # Verwijder de record uit de away_details tabel
            cursor.execute("DELETE FROM away_details WHERE id = %s", (away_id,))

            # Commit de veranderingen naar de database
            conn.commit()

        except Exception as e:
            # Als er iets misgaat, rollback de transactie
            conn.rollback()
        finally:
            # Sluit de cursor en de verbinding
            cursor.close()
            conn.close()

    return redirect(url_for('away_lijsten'))




@app.route('/download_lijst/<int:away_id>')
@login_required
@admin_required
def download_lijst(away_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Haal de geselecteerde leden op uit de database
        cursor.execute("""
            SELECT u.voornaam, u.naam, u.one_account_id
            FROM users u
            JOIN user_aways ua ON u.id = ua.user_id
            WHERE ua.away_id = %s AND ua.geselecteerd = TRUE
            ORDER BY u.naam, u.voornaam
        """, (away_id,))
        geselecteerde_leden = cursor.fetchall()


        cursor.execute("""
        SELECT a.naam
        FROM aways a
        join away_details ad on ad.away_id = a.id
        WHERE ad.id = %s
        """,(away_id,))
        away_naam = cursor.fetchone()[0]
        conn.close()

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
        conn = get_db_connection()
        cursor = conn.cursor()

        # Haal de waarde van de away op
        cursor.execute("""
            SELECT a.waarde 
            FROM aways a
            JOIN away_details ad ON a.id = ad.away_id
            WHERE ad.id = %s
        """, (away_id,))
        away_waarde = cursor.fetchone()[0]

        # Haal de geselecteerde leden op
        cursor.execute("""
            SELECT u.id 
            FROM users u
            JOIN user_aways ua ON u.id = ua.user_id
            WHERE ua.away_id = %s AND ua.geselecteerd = TRUE
        """, (away_id,))
        geselecteerde_leden = cursor.fetchall()

        # Werk de punten van de geselecteerde leden bij
        for lid in geselecteerde_leden:
            user_id = lid[0]
            cursor.execute("""
                UPDATE users 
                SET puntenaantal = puntenaantal + %s 
                WHERE id = %s
            """, (away_waarde, user_id))

        cursor.execute("DELETE FROM user_aways WHERE away_id = %s", (away_id,))

        # Verwijder de lijst uit de database
        cursor.execute("DELETE FROM away_details WHERE id = %s", (away_id,))

        conn.commit()
        conn.close()

        return redirect(url_for('away_lijsten'))
    except Exception as e:
        print(f"Fout bij het bevestigen van de lijst: {e}")
        return "Er is een fout opgetreden bij het bevestigen van de lijst.", 500


@app.route('/vervang_gebruiker/<int:away_id>/<int:verwijderde_user_id>')
@login_required
@admin_required
def vervang_gebruiker(away_id, verwijderde_user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Stap 1: Controleer of er nog leden in de wacht staan
        cursor.execute("""
            SELECT COUNT(*)
            FROM users u
            JOIN user_aways ua ON u.id = ua.user_id
            WHERE ua.away_id = %s AND ua.geselecteerd = FALSE
        """, (away_id,))

        leden_in_wacht = cursor.fetchone()[0] > 0  # Boolean: True als er leden in de wacht staan, anders False

        if not leden_in_wacht:
            # Als er geen leden in de wacht staan, stop de bewerking en geef een foutmelding terug
            return "Er zijn geen leden meer in de wachtlijst", 400

        # Stap 2: Verwijder de gebruiker helemaal uit de selectie
        cursor.execute("""
            DELETE FROM user_aways
            WHERE away_id = %s AND user_id = %s
        """, (away_id, verwijderde_user_id))

        # Stap 3: Zoek de gebruiker met de hoogste punten die nog niet geselecteerd is
        cursor.execute("""
            SELECT u.id 
            FROM users u
            JOIN user_aways ua ON u.id = ua.user_id
            WHERE ua.away_id = %s AND ua.geselecteerd = FALSE
            ORDER BY u.puntenaantal DESC
            LIMIT 1
        """, (away_id,))

        nieuwe_gebruiker = cursor.fetchone()

        if nieuwe_gebruiker:
            nieuwe_user_id = nieuwe_gebruiker[0]

            # Stap 4: Zet deze nieuwe gebruiker in de selectie
            cursor.execute("""
                UPDATE user_aways 
                SET geselecteerd = TRUE 
                WHERE away_id = %s AND user_id = %s
            """, (away_id, nieuwe_user_id))

        conn.commit()
        conn.close()

        return redirect(url_for('bewerk_lijst', away_id=away_id))

    except Exception as e:
        print(f"Fout bij vervangen gebruiker: {e}")
        return "Er is een fout opgetreden", 500


@app.route('/vervang_gebruiker_kies_vrevanger/<int:away_id>/<int:verwijderde_user_id>')
@login_required
@admin_required
def vervang_gebruiker_kies_vrevanger(away_id, verwijderde_user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()


        cursor.execute("""
                   SELECT u.voornaam, u.naam
                    FROM users u
                    WHERE u.id = %s

                """, (verwijderde_user_id,))

        oude_naam = cursor.fetchone()

        cursor.execute("""
           SELECT u.id, u.voornaam, u.naam
            FROM users u
            LEFT JOIN user_aways ua ON ua.user_id = u.id AND ua.away_id = %s
            WHERE (ua.away_id = %s AND ua.geselecteerd = false)
               OR ua.away_id IS NULL
            ORDER BY u.naam;

        """, (away_id,away_id))

        lijst_mogelijke_leden = cursor.fetchall()

        conn.commit()
        conn.close()

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
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                DELETE FROM user_aways
                WHERE away_id = %s AND user_id = %s
            """, (away_id, verwijderde_user_id))

            cursor.execute("""
                SELECT * FROM user_aways
                WHERE user_id = %s AND away_id = %s
            """, (nieuwe_gebruiker_id, away_id,))

            check = cursor.fetchone()
            if check is None:
                cursor.execute("""
                    INSERT INTO user_aways (user_id, away_id, geselecteerd)
                    VALUES (%s, %s, TRUE)
                """, (nieuwe_gebruiker_id, away_id,))
            else:
                cursor.execute("""
                    UPDATE user_aways 
                    SET geselecteerd = TRUE 
                    WHERE away_id = %s AND user_id = %s
                """, (away_id, nieuwe_gebruiker_id))

            conn.commit()
            conn.close()

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
        conn = get_db_connection()
        cursor = conn.cursor()


        # Stap 2: Verwijder de gebruiker helemaal uit de selectie
        cursor.execute("""
            DELETE FROM user_aways
            WHERE away_id = %s AND user_id = %s
        """, (away_id, verwijderde_user_id))

        # Stap 3: Zoek de gebruiker met de hoogste punten die nog niet geselecteerd is
        cursor.execute("""
           DELETE FROM user_aways
            WHERE away_id = %s AND geselecteerd = FALSE
        """, (away_id,))

        conn.commit()
        conn.close()

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
        conn = get_db_connection()
        cursor = conn.cursor()

        # Haal alle inschrijvingen op die gesloten moeten worden
        cursor.execute(''' 
            SELECT id 
            FROM away_details 
            WHERE is_closed = FALSE AND inschrijving_einde < NOW()
        ''')
        closed_inschrijvingen = cursor.fetchall()

        conn.close()

        # Retourneer een lijst van IDs van gesloten inschrijvingen
        return {'closed_inschrijvingen': [row[0] for row in closed_inschrijvingen]}
    except Exception as e:
        print(f"Fout bij het controleren van gesloten inschrijvingen: {e}")
        return {'error': 'Er is een fout opgetreden'}, 500

@app.route('/toevoegen_lid_aan_lijst/<int:away_id>')
@login_required
@admin_required
def toevoegen_lid_aan_lijst(away_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) FROM user_aways
        WHERE away_id = %s
        """, (away_id,))

    aantal_leden = cursor.fetchone()[0]

    cursor.execute("""
            SELECT aantal_kaarten FROM away_details
            WHERE id = %s
            """, (away_id,))
    aantal_kaarten = cursor.fetchone()[0]


    if aantal_leden >= aantal_kaarten:
        return redirect(url_for('bewerk_lijst', away_id=away_id))

    cursor.execute("""
              SELECT u.id, u.voornaam, u.naam
               FROM users u
               LEFT JOIN user_aways ua ON ua.user_id = u.id AND ua.away_id = %s
               WHERE (ua.away_id = %s AND ua.geselecteerd = false)
                  OR ua.away_id IS NULL
               ORDER BY u.naam;

           """, (away_id, away_id))

    lijst_mogelijke_leden = cursor.fetchall()

    return render_template('toevoegen_lid_lijst.html', away_id=away_id,
                           lijst_mogelijke_leden=lijst_mogelijke_leden)


@app.route('/verwerk_lid_toevoegen_lijst', methods=['GET', 'POST'])
@login_required
@admin_required
def verwerk_lid_toevoegen_lijst():
    if request.method == 'POST':

        away_id = request.form.get('away_id')
        nieuwe_gebruiker_id = request.form.get('nieuwe_gebruiker')
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
                SELECT COUNT(*) FROM user_aways
                WHERE away_id = %s
                """, (away_id,))

        aantal_leden = cursor.fetchone()[0]

        cursor.execute("""
                    SELECT aantal_kaarten FROM away_details
                    WHERE id = %s
                    """, (away_id,))
        aantal_kaarten = cursor.fetchone()[0]

        if aantal_leden >= aantal_kaarten:
            return redirect(url_for('bewerk_lijst', away_id=away_id))

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                        SELECT * FROM user_aways
                        WHERE user_id = %s AND away_id = %s
                    """, (nieuwe_gebruiker_id, away_id,))

            check = cursor.fetchone()
            if check is None:
                cursor.execute("""
                            INSERT INTO user_aways (user_id, away_id, geselecteerd)
                            VALUES (%s, %s, TRUE)
                        """, (nieuwe_gebruiker_id, away_id,))
            else:
                cursor.execute("""
                            UPDATE user_aways 
                            SET geselecteerd = TRUE 
                            WHERE away_id = %s AND user_id = %s
                        """, (away_id, nieuwe_gebruiker_id))

            conn.commit()
            conn.close()

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