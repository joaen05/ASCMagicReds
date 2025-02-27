import sqlite3

# Verbind met de database (maakt het bestand aan als het niet bestaat)
conn = sqlite3.connect('users.db')
cursor = conn.cursor()

# Maak de tabel 'users' als deze nog niet bestaat
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    voornaam TEXT NOT NULL,
    naam TEXT NOT NULL,
    email TEXT NOT NULL,
    one_account_id INTEGER NOT NULL,  -- Toevoegen van one_account_id
    adres_straat TEXT NOT NULL,  -- Adres straat
    adres_nr TEXT NOT NULL,  -- Adres nummer
    adres_postcode INTEGER NOT NULL,  -- Adres postcode
    adres_gemeente TEXT NOT NULL,  -- Adres gemeente
    rijksregisternummer TEXT NOT NULL,  -- Rijksregisternummer
    abo_ja_nee TEXT CHECK(abo_ja_nee IN ('ja', 'nee')) NOT NULL,  -- Abonnement ja/nee
    telefoonnummer TEXT NOT NULL,  -- Telefoonnummer
    puntenaantal INTEGER DEFAULT 0  -- Puntenaantal
)
''')

# Maak de tabel 'aways' als deze nog niet bestaat
cursor.execute('''
CREATE TABLE IF NOT EXISTS aways (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    naam TEXT NOT NULL  -- Naam van de activiteit
)
''')

# Maak de linktabel 'user_aways' voor de veel-op-veel relatie
cursor.execute('''
CREATE TABLE IF NOT EXISTS user_aways (
    user_id INTEGER,
    away_id INTEGER,
    inschrijvingsdatum DATE NOT NULL,  -- Datum van inschrijving
    PRIMARY KEY (user_id, away_id),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (away_id) REFERENCES aways (id) ON DELETE CASCADE
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS away_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    away_id INTEGER,
    beschrijving TEXT,  -- Beschrijving van de activiteit
    aantal_kaarten INTEGER,  -- Aantal beschikbare kaarten
    away_datum DATETIME,  -- Datum van de activiteit
    inschrijving_einde DATETIME,  -- Datum tot wanneer mensen zich kunnen inschrijven
    is_closed BOOLEAN DEFAULT 0,
    FOREIGN KEY (away_id) REFERENCES aways (id) ON DELETE CASCADE
)
''')


print("Database en tabellen succesvol aangemaakt en bijgewerkt!")

# Sluit de verbinding
conn.close()
