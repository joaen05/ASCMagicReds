import certifi
from flask import Flask, redirect, session, url_for, render_template, request
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from pymongo import MongoClient
import os
from functools import wraps
from datetime import datetime

# Laad omgevingsvariabelen uit .env-bestand
load_dotenv()

# MongoDB configuratie
MONGODB_URI = os.getenv('MONGODB_URI')
client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where())
db = client['ASCMagicReds']  # Vervang 'ASCMagicReds' door de naam van je database

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

# Functie om toegang te controleren
def is_email_in_database(email):
    user = db.users.find_one({"email": email})
    return user is not None

def is_naam_in_database(naam):
    away = db.aways.find_one({"naam": naam})
    return away is not None

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
        leden = list(db.users.find({}, {"_id": 0, "voornaam": 1, "naam": 1, "email": 1, "puntenaantal": 1}).sort("puntenaantal", -1))
        leden_dict = [
            {
                'voornaam': lid['voornaam'],
                'naam': lid['naam'],
                'email': lid['email'],
                'puntenaantal': lid['puntenaantal'],
                'is_logged_in': (lid['email'] == logged_in_email)
            }
            for lid in leden
        ]
        return render_template('points_list.html', leden=leden_dict)
    except Exception as e:
        print(f"Error: {e}")
        return redirect(url_for("dashboard"))

@app.route('/beheer_leden')
@login_required
@admin_required
def beheer_leden():
    try:
        leden = list(db.users.find({}, {"_id": 0, "id": 1, "voornaam": 1, "naam": 1}).sort("naam", 1))
        leden_dict = [{'id': lid['id'], 'voornaam': lid['voornaam'], 'naam': lid['naam']} for lid in leden]
        return render_template('beheer_leden.html', leden=leden_dict)
    except Exception as e:
        print(f"Error: {e}")
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
            db.users.insert_one(data)
            return redirect(url_for('beheer_leden'))
        except Exception as e:
            print(f"Error: {e}")
            return render_template('add_user.html', error="Fout bij het toevoegen van de gebruiker.")
    return render_template('add_user.html')

@app.route('/edit_member/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_member(id):
    try:
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
            db.users.update_one({"id": id}, {"$set": data})
            return redirect(url_for('beheer_leden'))
        else:
            member = db.users.find_one({"id": id})
            if not member:
                return "Lid niet gevonden", 404
            return render_template('edit_member.html', member=member)
    except Exception as e:
        print(f"Error: {e}")
        return redirect(url_for("dashboard"))

@app.route('/delete_member/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_member(id):
    try:
        db.users.delete_one({"id": id})
        return redirect(url_for('beheer_leden'))
    except Exception as e:
        print(f"Error: {e}")
        return redirect(url_for("dashboard"))

@app.route('/inschrijven_away', methods=['GET', 'POST'])
@login_required
def inschrijven_away():
    page = request.args.get('page', 1, type=int)
    try:
        available_aways = list(db.away_details.find({"is_closed": False}).sort("inschrijving_einde", 1))
        current_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

        for away in available_aways:
            if datetime.strptime(away['inschrijving_einde'], '%Y-%m-%dT%H:%M:%S') < datetime.now():
                db.away_details.update_one({"_id": away['_id']}, {"$set": {"is_closed": True}})

        per_page = 1
        total_aways = len(available_aways)
        total_pages = (total_aways + per_page - 1) // per_page
        start_index = (page - 1) * per_page
        end_index = min(page * per_page, total_aways)
        paginated_aways = available_aways[start_index:end_index]

        if request.method == 'POST':
            for away in available_aways:
                if datetime.strptime(away['inschrijving_einde'], '%Y-%m-%dT%H:%M:%S') > datetime.now():
                    inschrijving_waarde = request.form.get(f'inschrijven_{away["_id"]}')
                    # Verwerk de inschrijving
                    # Bijvoorbeeld, sla de inschrijving op in de database
                    # ...

        return render_template('inschrijven_away.html', available_aways=paginated_aways, current_page=page, total_pages=total_pages, current_time=current_time)
    except Exception as e:
        print(f"Error: {e}")
        return redirect(url_for("dashboard"))

@app.route('/beheren_away')
@login_required
@admin_required
def beheren_away():
    try:
        aways = list(db.aways.find({}, {"_id": 0, "id": 1, "naam": 1}).sort("naam", 1))
        aways_dict = [{'id': away['id'], 'naam': away['naam']} for away in aways]
        return render_template('beheren_away.html', aways=aways_dict)
    except Exception as e:
        print(f"Error: {e}")
        return redirect(url_for("dashboard"))

@app.route('/add_away', methods=['GET', 'POST'])
@login_required
@admin_required
def add_away():
    if request.method == 'POST':
        naam = request.form.get('naam', '').strip().title()
        if not naam:
            return render_template('add_away.html', error="awaynaam mag niet leeg zijn!", naam="")
        if is_naam_in_database(naam):
            return render_template('add_away.html', error="Deze away bestaat al!", naam=naam)
        try:
            db.aways.insert_one({"naam": naam})
            return redirect(url_for('beheren_away'))
        except Exception as e:
            return render_template('add_away.html', error=f"Fout bij het toevoegen: {e}", naam=naam)
    return render_template('add_away.html', naam="")

@app.route('/edit_away/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_away(id):
    try:
        if request.method == 'POST':
            naam = request.form['naam'].title()
            db.aways.update_one({"id": id}, {"$set": {"naam": naam}})
            return redirect(url_for('beheren_away'))
        else:
            away = db.aways.find_one({"id": id})
            if not away:
                return "Away niet gevonden", 404
            return render_template('edit_away.html', away=away)
    except Exception as e:
        return f"Databasefout: {e}", 500

@app.route('/delete_away/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_away(id):
    try:
        db.aways.delete_one({"id": id})
        return redirect(url_for('beheren_away'))
    except Exception as e:
        return redirect(url_for("dashboard"))

@app.route('/aanmaken_inschrijving_away', methods=['GET', 'POST'])
@login_required
@admin_required
def aanmaken_inschrijving_away():
    try:
        available_aways = list(db.aways.find({}, {"_id": 0, "id": 1, "naam": 1}))
        if request.method == 'POST':
            away_id = request.form['away_id']
            aantal_kaarten = request.form['aantal_kaarten']
            beschrijving = request.form['beschrijving']
            away_datum = request.form['away_datum']
            inschrijving_einde = request.form['inschrijving_einde']

            away_datum = datetime.strptime(away_datum, '%Y-%m-%dT%H:%M')
            inschrijving_einde = datetime.strptime(inschrijving_einde, '%Y-%m-%dT%H:%M')

            formatted_away_datum = away_datum.strftime('%d/%m/%Y %H:%M')
            formatted_inschrijving_einde = inschrijving_einde.strftime('%Y-%m-%dT%H:%M:%S')

            db.away_details.insert_one({
                "away_id": away_id,
                "aantal_kaarten": aantal_kaarten,
                "beschrijving": beschrijving,
                "away_datum": formatted_away_datum,
                "inschrijving_einde": formatted_inschrijving_einde
            })
            return redirect(url_for('inschrijven_away'))
        return render_template('aanmaken_inschrijving_away.html', available_aways=available_aways)
    except Exception as e:
        print(f"Error: {e}")
        return redirect(url_for("dashboard"))

app.config['DEBUG'] = True
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)