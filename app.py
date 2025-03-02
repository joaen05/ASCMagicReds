import locale

from flask import Flask, redirect, session, url_for, render_template, request
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
import psycopg2
from urllib.parse import urlparse
import os
from functools import wraps
from datetime import datetime

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

locale.setlocale(locale.LC_TIME, 'nld_NLD')

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

    # Bereken het aantal pagina's van inschrijvingen
    per_page = 1  # We kunnen dit later variëren voor je paginering
    total_aways = len(available_aways)
    total_pages = (total_aways + per_page - 1) // per_page  # Berekent het totaal aantal pagina's

    # Bepaal welke inschrijvingen we moeten weergeven voor de huidige pagina
    start_index = (page - 1) * per_page
    end_index = min(page * per_page, total_aways)

    # Toon alleen de activiteiten voor de huidige pagina
    paginated_aways = available_aways[start_index:end_index]

    # Verwerk de inschrijvingen
    if request.method == 'POST':
        for away in available_aways:
            away_id = away[0]
            inschrijving_einde = away[5]  # inschrijving einde tijd uit de database
            now = datetime.now()

            if datetime.strptime(inschrijving_einde, '%Y-%m-%dT%H:%M:%S') > now:
                # Hier kun je inschrijving verwerken als de tijd nog niet is verstreken
                inschrijving_waarde = request.form.get(f'inschrijven_{away_id}')
                # Verwerk de inschrijving
                # Bijvoorbeeld, sla de inschrijving op in de database
                # ...

    conn.close()

    return render_template('inschrijven_away.html', available_aways=paginated_aways, current_page=page, total_pages=total_pages, current_time=current_time)
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

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)