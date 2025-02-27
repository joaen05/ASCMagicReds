import psycopg2

# Verbind met de PostgreSQL-database
conn = psycopg2.connect(
    host="dpg-cv06lnvnoe9s73d0fbgg-a",  # Hostnaam van je Render database
    port="5432",                       # Standaard poort voor PostgreSQL
    dbname="ascmagicreds",              # Naam van je database
    user="ascmagicreds_user",           # Gebruikersnaam
    password="cuR0KIuofAMAQoPFSsbXDQ6NrZyviMim"   # Wachtwoord van je database
)

cursor = conn.cursor()

# Maak de tabellen aan (gebruik dezelfde SQL-queries als je voor SQLite hebt)

cursor.execute(''' 
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,  -- Gebruik SERIAL voor auto-increment in PostgreSQL
    voornaam TEXT NOT NULL,
    naam TEXT NOT NULL,
    email TEXT NOT NULL,
    one_account_id INTEGER NOT NULL,
    adres_straat TEXT NOT NULL,
    adres_nr TEXT NOT NULL,
    adres_postcode INTEGER NOT NULL,
    adres_gemeente TEXT NOT NULL,
    rijksregisternummer TEXT NOT NULL,
    abo_ja_nee TEXT CHECK(abo_ja_nee IN ('ja', 'nee')) NOT NULL,
    telefoonnummer TEXT NOT NULL,
    puntenaantal INTEGER DEFAULT 0
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS aways (
    id SERIAL PRIMARY KEY,
    naam TEXT NOT NULL
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS user_aways (
    user_id INTEGER,
    away_id INTEGER,
    inschrijvingsdatum DATE NOT NULL,
    PRIMARY KEY (user_id, away_id),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (away_id) REFERENCES aways (id) ON DELETE CASCADE
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS away_details (
    id SERIAL PRIMARY KEY,
    away_id INTEGER,
    beschrijving TEXT,
    aantal_kaarten INTEGER,
    away_datum TIMESTAMP,  -- Gebruik TIMESTAMP voor datum en tijd in PostgreSQL
    inschrijving_einde TIMESTAMP,
    is_closed BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (away_id) REFERENCES aways (id) ON DELETE CASCADE
)
''')

print("Database en tabellen succesvol aangemaakt en bijgewerkt!")

# Sluit de verbinding
conn.commit()
conn.close()
