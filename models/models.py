from contextlib import contextmanager
import psycopg2
from urllib.parse import urlparse
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')

def get_db_connection():
    result = urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        host=result.hostname,
        port=result.port,
        database=result.path[1:],
        user=result.username,
        password=result.password
    )
    return conn

class Query:
    @staticmethod
    @contextmanager
    def _get_cursor():
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            yield cursor
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                conn.close()

    @staticmethod
    def getFullname(email):
        with Query._get_cursor() as cursor:
            cursor.execute("SELECT concat(voornaam, ' ', naam) FROM users WHERE email = %s", (email,))
            result = cursor.fetchone()
            return result[0] if result else "Onbekende gebruiker"

    @staticmethod
    def is_email_in_db(email):
        with Query._get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM users WHERE email = %s", (email,))
            result = cursor.fetchone()
            return result[0] > 0

    @staticmethod
    def is_name_in_db(name):
        with Query._get_cursor() as cursor:
            cursor.execute("SELECT 1 FROM aways WHERE naam = %s", (name,))
            result = cursor.fetchone()
            return result is not None

    @staticmethod
    def update_geselecteerde_gebruikers(away_id):
        try:
            with Query._get_cursor() as cursor:
                cursor.execute("SELECT aantal_kaarten FROM away_details WHERE id = %s", (away_id,))
                aantal_kaarten = cursor.fetchone()[0]

                cursor.execute('''
                    SELECT ua.user_id, u.puntenaantal
                    FROM user_aways ua
                    JOIN users u ON ua.user_id = u.id
                    WHERE ua.away_id = %s
                    ORDER BY u.puntenaantal DESC
                ''', (away_id,))
                ingeschreven_gebruikers = cursor.fetchall()

                top_gebruikers = [row[0] for row in ingeschreven_gebruikers[:aantal_kaarten]]
                top_gebruikers_tuple = tuple(top_gebruikers) if top_gebruikers else (None,)

                cursor.execute('''
                    UPDATE user_aways
                    SET geselecteerd = TRUE
                    WHERE away_id = %s AND user_id IN %s
                ''', (away_id, top_gebruikers_tuple))

                cursor.execute('''
                    UPDATE user_aways
                    SET geselecteerd = FALSE
                    WHERE away_id = %s AND user_id NOT IN %s
                ''', (away_id, top_gebruikers_tuple))
        except Exception as e:
            print(f"Fout bij het bijwerken van geselecteerde gebruikers: {e}")

    @staticmethod
    def vervang_geselecteerde_gebruiker(away_id, verwijderde_user_id):
        try:
            with Query._get_cursor() as cursor:
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
        except Exception as e:
            print(f"Fout bij het vervangen van een gebruiker: {e}")

    @staticmethod
    def getPointList():
        with Query._get_cursor() as cursor:
            cursor.execute("SELECT voornaam, naam, email, puntenaantal FROM users ORDER BY puntenaantal DESC")
            return cursor.fetchall()

    @staticmethod
    def getSortedListUsers():
        with Query._get_cursor() as cursor:
            cursor.execute("SELECT id, voornaam, naam FROM users ORDER BY naam, voornaam")
            return cursor.fetchall()

    @staticmethod
    def addUser(voornaam, naam, email, one_account_id, adres_straat, adres_nr, adres_postcode, adres_gemeente, rijksregisternummer, abo_ja_nee, telefoonnummer, puntenaantal):
        with Query._get_cursor() as cursor:
            cursor.execute('''INSERT INTO users (voornaam, naam, email, one_account_id, adres_straat, adres_nr, adres_postcode, adres_gemeente, rijksregisternummer, abo_ja_nee, telefoonnummer, puntenaantal)
                          VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                       (voornaam, naam, email, one_account_id, adres_straat, adres_nr, adres_postcode, adres_gemeente, rijksregisternummer, abo_ja_nee, telefoonnummer, puntenaantal))

    @staticmethod
    def updateUser(voornaam, naam, email, one_account_id, adres_straat, adres_nr, adres_postcode, adres_gemeente, rijksregisternummer, abo_ja_nee, telefoonnummer, puntenaantal, id):
        with Query._get_cursor() as cursor:
            cursor.execute('''UPDATE users SET 
                          voornaam = %s, naam = %s, email = %s, one_account_id = %s, adres_straat = %s, 
                          adres_nr = %s, adres_postcode = %s, adres_gemeente = %s, rijksregisternummer = %s, 
                          abo_ja_nee = %s, telefoonnummer = %s, puntenaantal = %s WHERE id = %s''',
                       (voornaam, naam, email, one_account_id, adres_straat, adres_nr, adres_postcode,
                        adres_gemeente, rijksregisternummer, abo_ja_nee, telefoonnummer, puntenaantal, id))

    @staticmethod
    def getUser(id):
        with Query._get_cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE id = %s", (id,))
            return cursor.fetchone()

    @staticmethod
    def deleteUser(id):
        with Query._get_cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE id = %s", (id,))

    @staticmethod
    def setTimezone():
        with Query._get_cursor() as cursor:
            cursor.execute("SET TIMEZONE = 'Europe/Brussels';")

    @staticmethod
    def getClosedInschrijvingen():
        with Query._get_cursor() as cursor:
            cursor.execute(''' 
                SELECT id, inschrijving_einde 
                FROM away_details 
                WHERE is_closed = FALSE AND inschrijving_einde < NOW()
            ''')
            return cursor.fetchall()

    @staticmethod
    def setAwayDetailIsClosed(now):
        with Query._get_cursor() as cursor:
            cursor.execute(''' 
                UPDATE away_details 
                SET is_closed = TRUE 
                WHERE is_closed = FALSE AND inschrijving_einde < %s
            ''', (now,))

    @staticmethod
    def getOpenInschrijvingen():
        with Query._get_cursor() as cursor:
            cursor.execute(''' 
                SELECT ad.id, a.naam, ad.aantal_kaarten, ad.beschrijving, ad.away_datum, ad.inschrijving_einde, ad.is_closed
                FROM away_details ad
                JOIN aways a ON ad.away_id = a.id
                WHERE ad.is_closed = FALSE
                ORDER BY ad.inschrijving_einde ASC
            ''')
            return cursor.fetchall()

    @staticmethod
    def getUserId(user_email):
        with Query._get_cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE email = %s", (user_email,))
            result = cursor.fetchone()
            return result[0] if result else None

    @staticmethod
    def getAwayInschrijvingStatus(user_id, away_id):
        with Query._get_cursor() as cursor:
            cursor.execute("SELECT 1 FROM user_aways WHERE user_id = %s AND away_id = %s", (user_id, away_id))
            return cursor.fetchone()

    @staticmethod
    def getAways():
        with Query._get_cursor() as cursor:
            cursor.execute("SELECT id, naam, waarde FROM aways ORDER BY naam")
            return cursor.fetchall()

    @staticmethod
    def addAway(naam, waarde):
        with Query._get_cursor() as cursor:
            cursor.execute("INSERT INTO aways (naam, waarde) VALUES (%s, %s)", (naam, waarde))

    @staticmethod
    def updateAway(naam, waarde, id):
        with Query._get_cursor() as cursor:
            cursor.execute("UPDATE aways SET naam = %s, waarde = %s WHERE id = %s", (naam, waarde, id))

    @staticmethod
    def getAway(id):
        with Query._get_cursor() as cursor:
            cursor.execute("SELECT id, naam, waarde FROM aways WHERE id = %s", (id,))
            return cursor.fetchone()

    @staticmethod
    def deleteAway(id):
        with Query._get_cursor() as cursor:
            cursor.execute("DELETE FROM aways WHERE id = %s", (id,))

    @staticmethod
    def getAvailableAways():
        with Query._get_cursor() as cursor:
            cursor.execute("SELECT id, naam FROM aways")
            return cursor.fetchall()

    @staticmethod
    def addAwayDetails(away_id, aantal_kaarten, beschrijving, formatted_away_datum, formatted_inschrijving_einde):
        with Query._get_cursor() as cursor:
            cursor.execute('''INSERT INTO away_details (away_id, aantal_kaarten, beschrijving, away_datum, inschrijving_einde) 
                          VALUES (%s, %s, %s, %s, %s)''',
                       (away_id, aantal_kaarten, beschrijving, formatted_away_datum, formatted_inschrijving_einde))

    @staticmethod
    def updateAwayDetails(away_id_new, aantal_kaarten, beschrijving, formatted_away_datum, formatted_inschrijving_einde, away_id):
        with Query._get_cursor() as cursor:
            cursor.execute('''
                UPDATE away_details 
                SET away_id = %s, aantal_kaarten = %s, beschrijving = %s, away_datum = %s, inschrijving_einde = %s 
                WHERE id = %s
            ''', (away_id_new, aantal_kaarten, beschrijving, formatted_away_datum, formatted_inschrijving_einde, away_id))

    @staticmethod
    def getAwayDetails(away_id):
        with Query._get_cursor() as cursor:
            cursor.execute("SELECT * FROM away_details WHERE id = %s", (away_id,))
            return cursor.fetchone()

    @staticmethod
    def removeAwayDetails(away_id):
        with Query._get_cursor() as cursor:
            cursor.execute("DELETE FROM away_details WHERE id = %s", (away_id,))

    @staticmethod
    def getSelectedUserAwayDetails(user_id, away_details_id):
        with Query._get_cursor() as cursor:
            cursor.execute('''SELECT user_id, away_id FROM user_aways WHERE user_id = %s AND away_id = %s''',
                       (user_id, away_details_id))
            return cursor.fetchone()

    @staticmethod
    def addUserAwayDetails(user_id, away_details_id):
        with Query._get_cursor() as cursor:
            cursor.execute('''
                INSERT INTO user_aways (user_id, away_id)
                VALUES (%s, %s)
            ''', (user_id, away_details_id))

    @staticmethod
    def removeUserAwayDetails(user_id, away_details_id):
        with Query._get_cursor() as cursor:
            cursor.execute('''
                DELETE FROM user_aways WHERE user_id = %s AND away_id = %s
            ''', (user_id, away_details_id))

    @staticmethod
    def getAwayDetailsId():
        with Query._get_cursor() as cursor:
            cursor.execute("SELECT id FROM away_details")
            return cursor.fetchall()

    @staticmethod
    def getAmountAwayDetails():
        with Query._get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM away_details")
            return cursor.fetchone()

    @staticmethod
    def getAllUserAwayDetails(per_page, offset):
        with Query._get_cursor() as cursor:
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
            return cursor.fetchall()

    @staticmethod
    def getGeselecteerdeLeden(away_id):
        with Query._get_cursor() as cursor:
            cursor.execute('''
                SELECT u.id, u.voornaam, u.naam, u.one_account_id
                FROM users u
                JOIN user_aways ua ON u.id = ua.user_id
                WHERE ua.away_id = %s AND ua.geselecteerd = TRUE
                ORDER BY u.naam,u.voornaam
            ''', (away_id,))
            return cursor.fetchall()

    @staticmethod
    def getNietGeselcteerdeLeden(away_id):
        with Query._get_cursor() as cursor:
            cursor.execute('''
                SELECT u.id, u.voornaam, u.naam, u.one_account_id
                FROM users u
                LEFT JOIN user_aways ua ON u.id = ua.user_id AND ua.away_id = %s
                WHERE ua.geselecteerd IS NULL OR ua.geselecteerd = FALSE
            ''', (away_id,))
            return cursor.fetchall()

    @staticmethod
    def getAantalKaarten(away_id):
        with Query._get_cursor() as cursor:
            cursor.execute("SELECT aantal_kaarten FROM away_details WHERE id = %s", (away_id,))
            return cursor.fetchone()[0]

    @staticmethod
    def getLedenInWacht(away_id):
        with Query._get_cursor() as cursor:
            cursor.execute("""
               SELECT COUNT(*)
               FROM users u
               JOIN user_aways ua ON u.id = ua.user_id
               WHERE ua.away_id = %s AND ua.geselecteerd = FALSE
           """, (away_id,))
            return cursor.fetchone()[0]

    @staticmethod
    def getAantalGeselcteerdeLeden(away_id):
        with Query._get_cursor() as cursor:
            cursor.execute("SELECT count(user_id) FROM user_aways WHERE away_id = %s AND geselecteerd = TRUE", (away_id,))
            return cursor.fetchone()[0]

    @staticmethod
    def removeUserAways(away_id):
        with Query._get_cursor() as cursor:
            cursor.execute("DELETE FROM user_aways WHERE away_id = %s", (away_id,))

    @staticmethod
    def getGeselecteerdeLedenFinalInfo(away_id):
        with Query._get_cursor() as cursor:
            cursor.execute("""
                SELECT u.voornaam, u.naam, u.one_account_id
                FROM users u
                JOIN user_aways ua ON u.id = ua.user_id
                WHERE ua.away_id = %s AND ua.geselecteerd = TRUE
                ORDER BY u.naam, u.voornaam
            """, (away_id,))
            return cursor.fetchall()

    @staticmethod
    def getAwayNaam(away_id):
        with Query._get_cursor() as cursor:
            cursor.execute("""
               SELECT a.naam
               FROM aways a
               join away_details ad on ad.away_id = a.id
               WHERE ad.id = %s
               """, (away_id,))
            return cursor.fetchone()[0]

    @staticmethod
    def getAwayWaarde(away_id):
        with Query._get_cursor() as cursor:
            cursor.execute("""
                SELECT a.waarde 
                FROM aways a
                JOIN away_details ad ON a.id = ad.away_id
                WHERE ad.id = %s
            """, (away_id,))
            return cursor.fetchone()[0]

    @staticmethod
    def getGeselecteerdeLedenId(away_id):
        with Query._get_cursor() as cursor:
            cursor.execute("""
                SELECT u.id 
                FROM users u
                JOIN user_aways ua ON u.id = ua.user_id
                WHERE ua.away_id = %s AND ua.geselecteerd = TRUE
            """, (away_id,))
            return cursor.fetchall()

    @staticmethod
    def updatePuntenGeselcteerdeLeden(away_waarde, user_id):
        with Query._get_cursor() as cursor:
            cursor.execute("""
                UPDATE users 
                SET puntenaantal = puntenaantal + %s 
                WHERE id = %s
            """, (away_waarde, user_id))

    @staticmethod
    def getAmountNietGeselecteerdeLeden(away_id):
        with Query._get_cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*)
                FROM users u
                JOIN user_aways ua ON u.id = ua.user_id
                WHERE ua.away_id = %s AND ua.geselecteerd = FALSE
            """, (away_id,))
            return cursor.fetchone()[0] > 0

    @staticmethod
    def removeOldUser(away_id, verwijderde_user_id):
        with Query._get_cursor() as cursor:
            cursor.execute("""
                DELETE FROM user_aways
                WHERE away_id = %s AND user_id = %s
            """, (away_id, verwijderde_user_id))

    @staticmethod
    def getHoogsteNietgeselcteerdeLid(away_id):
        with Query._get_cursor() as cursor:
            cursor.execute("""
                SELECT u.id 
                FROM users u
                JOIN user_aways ua ON u.id = ua.user_id
                WHERE ua.away_id = %s AND ua.geselecteerd = FALSE
                ORDER BY u.puntenaantal DESC
                LIMIT 1
            """, (away_id,))
            return cursor.fetchone()

    @staticmethod
    def addNieuwGeselecteerdLidAanLijst(away_id, nieuwe_user_id):
        with Query._get_cursor() as cursor:
            cursor.execute("""
                UPDATE user_aways 
                SET geselecteerd = TRUE 
                WHERE away_id = %s AND user_id = %s
            """, (away_id, nieuwe_user_id))

    @staticmethod
    def getOldnaam(verwijderde_user_id):
        with Query._get_cursor() as cursor:
            cursor.execute("""
                SELECT u.voornaam, u.naam
                FROM users u
                WHERE u.id = %s
            """, (verwijderde_user_id,))
            return cursor.fetchone()

    @staticmethod
    def getAlleMogelijkeLeden(away_id):
        with Query._get_cursor() as cursor:
            cursor.execute("""
               SELECT u.id, u.voornaam, u.naam
                FROM users u
                LEFT JOIN user_aways ua ON ua.user_id = u.id AND ua.away_id = %s
                WHERE (ua.away_id = %s AND ua.geselecteerd = false)
                   OR ua.away_id IS NULL
                ORDER BY u.naam;
            """, (away_id, away_id))
            return cursor.fetchall()

    @staticmethod
    def getUserAndAwayIdFromUserAways(nieuwe_gebruiker_id, away_id):
        with Query._get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM user_aways
                WHERE user_id = %s AND away_id = %s
            """, (nieuwe_gebruiker_id, away_id,))
            return cursor.fetchone()

    @staticmethod
    def addLidAanList(nieuwe_gebruiker_id, away_id):
        with Query._get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO user_aways (user_id, away_id, geselecteerd)
                VALUES (%s, %s, TRUE)
            """, (nieuwe_gebruiker_id, away_id,))

    @staticmethod
    def updateGeselecteerdStatus(away_id, nieuwe_gebruiker_id):
        with Query._get_cursor() as cursor:
            cursor.execute("""
                UPDATE user_aways 
                SET geselecteerd = TRUE 
                WHERE away_id = %s AND user_id = %s
            """, (away_id, nieuwe_gebruiker_id))

    @staticmethod
    def removeNietGeselecteerdeLeden(away_id):
        with Query._get_cursor() as cursor:
            cursor.execute("""
               DELETE FROM user_aways
                WHERE away_id = %s AND geselecteerd = FALSE
            """, (away_id,))

    @staticmethod
    def getAwayDetailsIdFromGeslotenInschrijvingen():
        with Query._get_cursor() as cursor:
            cursor.execute(''' 
                SELECT id 
                FROM away_details 
                WHERE is_closed = FALSE AND inschrijving_einde < NOW()
            ''')
            return cursor.fetchall()

    @staticmethod
    def getAantalLedenInLijst(away_id):
        with Query._get_cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM user_aways
                WHERE away_id = %s
                """, (away_id,))
            return cursor.fetchone()[0]