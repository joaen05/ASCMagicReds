import locale
import sys

from flask import Flask, redirect, session, url_for, render_template, request
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
import psycopg2
from urllib.parse import urlparse
import os
from functools import wraps
from babel.dates import format_datetime
import datetime


# Laad omgevingsvariabelen uit .env-bestand
load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')


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

        # Update de `geselecteerd` kolom voor de top X gebruikers
        cursor.execute('''
            UPDATE user_aways
            SET geselecteerd = TRUE
            WHERE away_id = %s AND user_id IN %s
        ''', (away_id, tuple(top_gebruikers) if top_gebruikers else (away_id, ())))  # Vermijd SQL-syntaxfout bij lege lijst

        # Zet `geselecteerd` op FALSE voor de rest van de gebruikers
        cursor.execute('''
            UPDATE user_aways
            SET geselecteerd = FALSE
            WHERE away_id = %s AND user_id NOT IN %s
        ''', (away_id, tuple(top_gebruikers) if top_gebruikers else (away_id, ())))  # Vermijd SQL-syntaxfout bij lege lijst

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Fout bij het bijwerken van geselecteerde gebruikers: {e}")
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
    if user_email == "jonahaertssen05@gmail.com":
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
            'adres_straat': request.form['adres_straat'].title(),
            'adres_nr': request.form['adres_nr'],
            'adres_postcode': int(request.form['adres_postcode']),
            'adres_gemeente': request.form['adres_gemeente'].title(),
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
            adres_straat = request.form['adres_straat'].title()
            adres_nr = request.form['adres_nr']
            adres_postcode = int(request.form['adres_postcode'])
            adres_gemeente = request.form['adres_gemeente'].title()
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

from datetime import datetime


@app.route('/inschrijven_away', methods=['GET', 'POST'])
@login_required
def inschrijven_away():
    # Haal de pagina parameter uit de URL (standaard naar 1 als deze niet bestaat)
    page = request.args.get('page', 1, type=int)

    # Ophalen van alle available 'aways' met details zoals datum en inschrijvingen
    conn = get_db_connection()
    cursor = conn.cursor()

    # Haal alle away details op
    cursor.execute(''' 
        SELECT ad.id, a.naam, ad.aantal_kaarten, ad.beschrijving, ad.away_datum, ad.inschrijving_einde, ad.is_closed
        FROM away_details ad
        JOIN aways a ON ad.away_id = a.id
        WHERE ad.is_closed = FALSE  -- Gebruik FALSE in plaats van 0
        ORDER BY ad.inschrijving_einde ASC
    ''')
    available_aways = cursor.fetchall()

    # Verkrijg de huidige tijd voor de server-side logica
    current_time = datetime.now()

    # Converteer de 'away_datum' naar een datetime object
    for i in range(len(available_aways)):
        away = available_aways[i]
        away_date_str = away[4]  # 'away_datum' is op index 4
        if isinstance(away_date_str, str):  # Controleer of het een string is
            away_date = datetime.strptime(away_date_str, '%Y-%m-%d %H:%M:%S')  # Pas dit formaat aan als het anders is
            available_aways[i] = away[:4] + (away_date,) + away[5:]  # Vervang de oude string door een datetime object

    # Controleer of de inschrijving is verlopen en zet is_closed op -1
    for away in available_aways:
        away_id = away[0]
        inschrijving_einde = away[5]  # inschrijving einde tijd uit de database
        now = datetime.now()

        if inschrijving_einde < now:
            # Als de inschrijvingstijd is verstreken, update de 'is_closed' status naar TRUE
            cursor.execute(''' 
                UPDATE away_details
                SET is_closed = TRUE
                WHERE id = %s
            ''', (away_id,))
            conn.commit()

    # Haal de huidige gebruiker op
    user_email = session.get('user', {}).get('userinfo', {}).get('email')
    cursor.execute("SELECT id FROM users WHERE email = %s", (user_email,))
    user_id_tuple = cursor.fetchone()
    user_id = user_id_tuple[0] if user_id_tuple else None

    # Controleer voor elke away of de gebruiker al heeft ingeschreven
    away_inschrijving_status = {}
    if user_id:
        for away in available_aways:
            away_id = away[0]
            cursor.execute("SELECT 1 FROM user_aways WHERE user_id = %s AND away_id = %s", (user_id, away_id))
            if cursor.fetchone():
                away_inschrijving_status[away_id] = "ja"
            else:
                away_inschrijving_status[away_id] = "nee"

    # Bereken het aantal pagina's van inschrijvingen
    per_page = 1  # We kunnen dit later variëren voor je paginering
    total_aways = len(available_aways)
    total_pages = (total_aways + per_page - 1) // per_page  # Berekent het totaal aantal pagina's

    # Bepaal welke inschrijvingen we moeten weergeven voor de huidige pagina
    start_index = (page - 1) * per_page
    end_index = min(page * per_page, total_aways)

    # Toon alleen de activiteiten voor de huidige pagina
    paginated_aways = available_aways[start_index:end_index]

    conn.close()

    return render_template('inschrijven_away.html', available_aways=paginated_aways, current_page=page,
                           total_pages=total_pages, current_time=current_time, format_datetime=format_datetime,
                           away_inschrijving_status=away_inschrijving_status)
@app.route('/beheren_away')
@login_required
@admin_required
def beheren_away():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, naam FROM aways ORDER BY naam")
        aways = cursor.fetchall()
        conn.close()
        aways_dict = [{'id': away[0], 'naam': away[1]} for away in aways]
        return render_template('beheren_away.html', aways=aways_dict)
    except psycopg2.Error:
        return redirect(url_for("dashboard"))

@app.route('/add_away', methods=['GET', 'POST'])
@login_required
@admin_required
def add_away():
    if request.method == 'POST':
        naam = request.form.get('naam', '').strip().title()  # Zorg dat 'naam' altijd een string is

        if not naam:  # Controleer of naam niet leeg is
            return render_template('add_away.html', error="awaynaam mag niet leeg zijn!", naam="")

        if is_naam_in_database(naam):
            return render_template('add_away.html', error="Deze away bestaat al!", naam=naam)

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO aways (naam) VALUES (%s)", (naam,))
            conn.commit()
            conn.close()
            return redirect(url_for('beheren_away'))  # Redirect bij succes
        except psycopg2.Error as e:
            return render_template('add_away.html', error=f"Fout bij het toevoegen: {e}", naam=naam)

    return render_template('add_away.html', naam="")

@app.route('/edit_away/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_away(id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if request.method == 'POST':
            naam = request.form['naam'].title()
            cursor.execute("UPDATE aways SET naam = %s WHERE id = %s", (naam, id))
            conn.commit()
            conn.close()
            return redirect(url_for('beheren_away'))
        else:
            cursor.execute("SELECT id, naam FROM aways WHERE id = %s", (id,))
            away = cursor.fetchone()
            conn.close()

            if not away:
                return "Away niet gevonden", 404

            away_dict = {'id': away[0], 'naam': away[1]}
            return render_template('edit_away.html', away=away_dict)
    except psycopg2.Error as e:
        return f"Databasefout: {e}", 500

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
        conn = get_db_connection()
        cursor = conn.cursor()

        if request.method == 'POST':
            # Haal de form-gegevens op en werk de away inschrijving bij
            away_id_new = request.form['away_id']  # Nieuwe away_id uit de dropdown
            aantal_kaarten = int(request.form['aantal_kaarten'])  # Aantal kaarten
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
            return redirect(url_for('inschrijven_away'))
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
            return render_template('bewerken_away_details.html', away_details=away_details_dict, available_aways=available_aways)
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
@app.route('/away_lijsten')
@login_required
@admin_required
def away_lijsten():
    try:
        # Haal de pagina parameter uit de URL (standaard naar 1 als deze niet bestaat)
        page = request.args.get('page', 1, type=int)
        per_page = 1  # Aantal aways per pagina (kan je aanpassen naar wens)

        conn = get_db_connection()
        cursor = conn.cursor()

        # Roep de functie aan om de geselecteerde gebruikers bij te werken voor elke away
        cursor.execute("SELECT id FROM away_details")
        away_ids = [row[0] for row in cursor.fetchall()]
        for away_id in away_ids:
            update_geselecteerde_gebruikers(away_id)

        # Haal het totaal aantal aways op
        cursor.execute("SELECT COUNT(*) FROM away_details")
        total_aways = cursor.fetchone()[0]

        # Bereken het totale aantal pagina's
        total_pages = (total_aways + per_page - 1) // per_page

        # Bepaal de offset voor de huidige pagina
        offset = (page - 1) * per_page

        # Haal de lijsten op voor de aways van de huidige pagina
        cursor.execute("""
            SELECT 
                a.naam, 
                ad.away_datum, 
                ad.aantal_kaarten, 
                STRING_AGG(CONCAT(u.voornaam, ' ', u.naam, ' (', u.one_account_id, ')'), E'\n' ORDER BY u.naam, u.voornaam) AS gebruikers,
                STRING_AGG(
                    CASE 
                        WHEN ua.geselecteerd = TRUE THEN CONCAT(u.voornaam, ' ', u.naam, ' (', u.one_account_id, ')')
                        ELSE NULL
                    END, 
                    E'\n' ORDER BY u.naam, u.voornaam
                ) AS geselecteerde_gebruikers
            FROM user_aways ua
            JOIN away_details ad ON ua.away_id = ad.id
            JOIN aways a ON ad.away_id = a.id
            JOIN users u ON ua.user_id = u.id
            GROUP BY a.naam, ad.away_datum, ad.aantal_kaarten
            ORDER BY ad.away_datum
            LIMIT %s OFFSET %s
        """, (per_page, offset))

        resultaten = cursor.fetchall()
        conn.close()

        return render_template("lijst_away.html", resultaten=resultaten, format_datetime=format_datetime, current_page=page, total_pages=total_pages)
    except Exception as e:
        print("Fout bij het uitvoeren van de query:", e)
        return "Er is een fout opgetreden bij het ophalen van de gegevens.", 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)