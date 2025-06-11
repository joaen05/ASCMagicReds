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
    def getFullname(email):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT concat(voornaam, ' ', naam) FROM users WHERE email = %s", (email,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else "Onbekende gebruiker"

    @staticmethod
    def is_email_in_db(email):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE email = %s", (email,))
        result = cursor.fetchone()
        conn.close()
        return result[0] > 0

    @staticmethod
    def is_name_in_db(name):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM aways WHERE naam = %s", (name,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    @staticmethod
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


    @staticmethod
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


    @staticmethod
    def getPointList():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT voornaam, naam, email, puntenaantal FROM users ORDER BY puntenaantal DESC")
        leden = cursor.fetchall()
        conn.close()
        return leden

    @staticmethod
    def getSortedListUsers():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, voornaam, naam FROM users ORDER BY naam, voornaam")
        leden = cursor.fetchall()
        conn.close()
        return leden

    @staticmethod
    def addUser(voornaam,naam,email, one_account_id, adres_straat, adres_nr, adres_postcode, adres_gemeente, rijksregisternummer, abo_ja_nee, telefoonnummer, puntenaantal):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO users (voornaam, naam, email, one_account_id, adres_straat, adres_nr, adres_postcode, adres_gemeente, rijksregisternummer, abo_ja_nee, telefoonnummer, puntenaantal)
                                      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                       (voornaam, naam, email, one_account_id, adres_straat,
                        adres_nr, adres_postcode, adres_gemeente,rijksregisternummer,
                        abo_ja_nee, telefoonnummer, puntenaantal))
        conn.commit()
        conn.close()

    @staticmethod
    def updateUser(voornaam, naam, email, one_account_id, adres_straat, adres_nr, adres_postcode,adres_gemeente, rijksregisternummer, abo_ja_nee, telefoonnummer, puntenaantal, id):
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''UPDATE users SET 
                                      voornaam = %s, naam = %s, email = %s, one_account_id = %s, adres_straat = %s, 
                                      adres_nr = %s, adres_postcode = %s, adres_gemeente = %s, rijksregisternummer = %s, 
                                      abo_ja_nee = %s, telefoonnummer = %s, puntenaantal = %s WHERE id = %s''',
                       (voornaam, naam, email, one_account_id, adres_straat, adres_nr, adres_postcode,
                        adres_gemeente, rijksregisternummer, abo_ja_nee, telefoonnummer, puntenaantal, id))
        conn.commit()
        conn.close()

    @staticmethod
    def getUser(id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = %s", (id,))
        member = cursor.fetchone()
        conn.close()
        return member

    @staticmethod
    def deleteUser(id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = %s", (id,))
        conn.commit()
        conn.close()

    @staticmethod
    def setTimezone():
        conn = get_db_connection()
        cursor = conn.cursor()

        # Stel de tijdzone in op 'Europe/Brussels'
        cursor.execute("SET TIMEZONE = 'Europe/Brussels';")
        conn.commit()
        conn.close()

    @staticmethod
    def getClosedInschrijvingen():
        conn = get_db_connection()
        cursor = conn.cursor()
        # Controleer en sluit inschrijvingen die verlopen zijn
        cursor.execute(''' 
                SELECT id, inschrijving_einde 
                FROM away_details 
                WHERE is_closed = FALSE AND inschrijving_einde < NOW()
            ''')
        expired_aways = cursor.fetchall()
        conn.commit()
        conn.close()
        return expired_aways


    @staticmethod
    def setAwayDetailIsClosed(now):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(''' 
                UPDATE away_details 
                SET is_closed = TRUE 
                WHERE is_closed = FALSE AND inschrijving_einde < %s
            ''', (now,))
        conn.commit()
        conn.close()


    @staticmethod
    def getOpenInschrijvingen():
        conn = get_db_connection()
        cursor = conn.cursor()
        # Haal alle away details op die nog niet gesloten zijn
        cursor.execute(''' 
                SELECT ad.id, a.naam, ad.aantal_kaarten, ad.beschrijving, ad.away_datum, ad.inschrijving_einde, ad.is_closed
                FROM away_details ad
                JOIN aways a ON ad.away_id = a.id
                WHERE ad.is_closed = FALSE
                ORDER BY ad.inschrijving_einde ASC
            ''')
        available_aways = cursor.fetchall()
        conn.commit()
        conn.close()
        return available_aways

    @staticmethod
    def getUserId(user_email):
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM users WHERE email = %s", (user_email,))
        user_id_tuple = cursor.fetchone()
        conn.commit()
        conn.close()
        user_id = user_id_tuple[0] if user_id_tuple else None
        return user_id

    @staticmethod
    def getAwayInschrijvingStatus(user_id, away_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM user_aways WHERE user_id = %s AND away_id = %s", (user_id, away_id))
        status = cursor.fetchone()
        conn.commit()
        conn.close()
        return status

    @staticmethod
    def getAways():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, naam,waarde FROM aways ORDER BY naam")
        aways = cursor.fetchall()
        conn.close()
        return aways

    @staticmethod
    def addAway(naam,waarde):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO aways (naam, waarde) VALUES (%s, %s)", (naam, waarde))
        conn.commit()
        conn.close()

    @staticmethod
    def updateAway(naam,waarde,id):
        conn = get_db_connection()
        cursor = conn.cursor()
        # Werk de away bij in de database
        cursor.execute("UPDATE aways SET naam = %s, waarde = %s WHERE id = %s", (naam, waarde, id))
        conn.commit()
        conn.close()

    @staticmethod
    def getAway(id):
        conn = get_db_connection()
        cursor = conn.cursor()
        # Haal de bestaande gegevens van de away op
        cursor.execute("SELECT id, naam, waarde FROM aways WHERE id = %s", (id,))
        away = cursor.fetchone()
        conn.close()
        return away

    @staticmethod
    def deleteAway(id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM aways WHERE id = %s", (id,))
        conn.commit()
        conn.close()

    @staticmethod
    def getAvailableAways():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, naam FROM aways")  # Haal de id en naam op van alle 'aways'
        available_aways = cursor.fetchall()
        conn.close()
        return available_aways

    @staticmethod
    def addAwayDetails(away_id, aantal_kaarten, beschrijving, formatted_away_datum,
                       formatted_inschrijving_einde):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO away_details (away_id, aantal_kaarten, beschrijving, away_datum, inschrijving_einde) 
                                  VALUES (%s, %s, %s, %s, %s)''',
                       (away_id, aantal_kaarten, beschrijving, formatted_away_datum, formatted_inschrijving_einde))
        conn.commit()
        conn.close()

    @staticmethod
    def updateAwayDetails(away_id_new, aantal_kaarten, beschrijving, formatted_away_datum, formatted_inschrijving_einde, away_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
                        UPDATE away_details 
                        SET away_id = %s, aantal_kaarten = %s, beschrijving = %s, away_datum = %s, inschrijving_einde = %s 
                        WHERE id = %s
                    ''', (
        away_id_new, aantal_kaarten, beschrijving, formatted_away_datum, formatted_inschrijving_einde, away_id))

        conn.commit()
        conn.close()

    @staticmethod
    def getAwayDetails(away_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM away_details WHERE id = %s", (away_id,))
        away_details = cursor.fetchone()
        conn.close()
        return away_details

    @staticmethod
    def removeAwayDetails(away_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM away_details WHERE id = %s", (away_id,))
        conn.commit()
        conn.close()


    @staticmethod
    def getSelectedUserAwayDetails(user_id,away_details_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''SELECT user_id, away_id FROM user_aways WHERE user_id = %s AND away_id = %s''',
                       (user_id, away_details_id))
        founded_user_id = cursor.fetchone()
        conn.close()
        return founded_user_id

    @staticmethod
    def addUserAwayDetails(user_id, away_details_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
                            INSERT INTO user_aways (user_id, away_id)
                            VALUES (%s, %s)
                        ''', (user_id, away_details_id))
        conn.commit()
        conn.close()

    @staticmethod
    def removeUserAwayDetails(user_id, away_details_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
                            DELETE FROM user_aways WHERE user_id = %s AND away_id = %s
                        ''', (user_id, away_details_id))

        conn.commit()
        conn.close()

    @staticmethod
    def getAwayDetailsId():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM away_details")
        away_details_id = cursor.fetchall()
        conn.close()
        return away_details_id


    @staticmethod
    def getAmountAwayDetails():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM away_details")
        amount_aways = cursor.fetchone()
        conn.close()
        return amount_aways

    @staticmethod
    def getAllUserAwayDetails(per_page, offset):
        conn = get_db_connection()
        cursor = conn.cursor()
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
        return resultaten

    @staticmethod
    def getGeselecteerdeLeden(away_id):
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
        conn.close()
        return geselecteerde_leden


    @staticmethod
    def getNietGeselcteerdeLeden(away_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
                    SELECT u.id, u.voornaam, u.naam, u.one_account_id
                    FROM users u
                    LEFT JOIN user_aways ua ON u.id = ua.user_id AND ua.away_id = %s
                    WHERE ua.geselecteerd IS NULL OR ua.geselecteerd = FALSE
                ''', (away_id,))
        niet_geselecteerde_leden = cursor.fetchall()
        conn.close()
        return niet_geselecteerde_leden

    @staticmethod
    def getAantalKaarten(away_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT aantal_kaarten FROM away_details WHERE id = %s", (away_id,))
        aantal_kaarten = cursor.fetchone()[0]
        conn.close()
        return aantal_kaarten

    @staticmethod
    def getLedenInWacht(away_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
                   SELECT COUNT(*)
                   FROM users u
                   JOIN user_aways ua ON u.id = ua.user_id
                   WHERE ua.away_id = %s AND ua.geselecteerd = FALSE
               """, (away_id,))
        leden_in_wacht = cursor.fetchone()[0]
        conn.close()
        return leden_in_wacht

    @staticmethod
    def getAantalGeselcteerdeLeden(away_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT count(user_id) FROM user_aways WHERE away_id = %s AND geselecteerd = TRUE", (away_id,))
        aantal_geselecteerde_leden = cursor.fetchone()[0]
        conn.close()
        return aantal_geselecteerde_leden

    @staticmethod
    def removeUserAways(away_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        # Verwijder eerst alle rijen uit de tabel user_aways waar away_id overeenkomt
        cursor.execute("DELETE FROM user_aways WHERE away_id = %s", (away_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def getGeselecteerdeLedenFinalInfo(away_id):
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
        conn.close()
        return geselecteerde_leden

    @staticmethod
    def getAwayNaam(away_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
               SELECT a.naam
               FROM aways a
               join away_details ad on ad.away_id = a.id
               WHERE ad.id = %s
               """, (away_id,))
        away_naam = cursor.fetchone()[0]
        conn.close()
        return away_naam

    @staticmethod
    def getAwayWaarde(away_id):
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
        conn.close()
        return away_waarde

    @staticmethod
    def getGeselecteerdeLedenId(away_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        # Haal de geselecteerde leden op
        cursor.execute("""
                    SELECT u.id 
                    FROM users u
                    JOIN user_aways ua ON u.id = ua.user_id
                    WHERE ua.away_id = %s AND ua.geselecteerd = TRUE
                """, (away_id,))
        geselecteerde_leden = cursor.fetchall()
        conn.close()
        return geselecteerde_leden

    @staticmethod
    def updatePuntenGeselcteerdeLeden(away_waarde, user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
                        UPDATE users 
                        SET puntenaantal = puntenaantal + %s 
                        WHERE id = %s
                    """, (away_waarde, user_id))
        conn.commit()
        conn.close()

    @staticmethod
    def getAmountNietGeselecteerdeLeden(away_id):
        conn = get_db_connection()
        cursor = conn.cursor()

        # Stap 1: Controleer of er nog leden in de wacht staan
        cursor.execute("""
                    SELECT COUNT(*)
                    FROM users u
                    JOIN user_aways ua ON u.id = ua.user_id
                    WHERE ua.away_id = %s AND ua.geselecteerd = FALSE
                """, (away_id,))

        leden_in_wacht = cursor.fetchone()[0] > 0
        conn.close()
        return leden_in_wacht

    @staticmethod
    def removeOldUser(away_id, verwijderde_user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
                    DELETE FROM user_aways
                    WHERE away_id = %s AND user_id = %s
                """, (away_id, verwijderde_user_id))
        conn.commit()
        conn.close()


    @staticmethod
    def getHoogsteNietgeselcteerdeLid(away_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
                    SELECT u.id 
                    FROM users u
                    JOIN user_aways ua ON u.id = ua.user_id
                    WHERE ua.away_id = %s AND ua.geselecteerd = FALSE
                    ORDER BY u.puntenaantal DESC
                    LIMIT 1
                """, (away_id,))
        nieuwe_gebruiker = cursor.fetchone()
        conn.close()
        return nieuwe_gebruiker

    @staticmethod
    def addNieuwGeselecteerdLidAanLijst(away_id, nieuwe_user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
                        UPDATE user_aways 
                        SET geselecteerd = TRUE 
                        WHERE away_id = %s AND user_id = %s
                    """, (away_id, nieuwe_user_id))
        conn.commit()
        conn.close()

    @staticmethod
    def getOldnaam(verwijderde_user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
                           SELECT u.voornaam, u.naam
                            FROM users u
                            WHERE u.id = %s

                        """, (verwijderde_user_id,))

        oude_naam = cursor.fetchone()
        conn.close()
        return oude_naam


    @staticmethod
    def getAlleMogelijkeLeden(away_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
                   SELECT u.id, u.voornaam, u.naam
                    FROM users u
                    LEFT JOIN user_aways ua ON ua.user_id = u.id AND ua.away_id = %s
                    WHERE (ua.away_id = %s AND ua.geselecteerd = false)
                       OR ua.away_id IS NULL
                    ORDER BY u.naam;

                """, (away_id, away_id))


        lijst_mogelijke_leden = cursor.fetchall()
        conn.close()
        return lijst_mogelijke_leden



    @staticmethod
    def getUserAndAwayIdFromUserAways(nieuwe_gebruiker_id, away_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
                        SELECT * FROM user_aways
                        WHERE user_id = %s AND away_id = %s
                    """, (nieuwe_gebruiker_id, away_id,))

        check = cursor.fetchone()
        conn.close()
        return check

    @staticmethod
    def addLidAanList(nieuwe_gebruiker_id, away_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
                            INSERT INTO user_aways (user_id, away_id, geselecteerd)
                            VALUES (%s, %s, TRUE)
                        """, (nieuwe_gebruiker_id, away_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def updateGeselecteerdStatus(away_id, nieuwe_gebruiker_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
                            UPDATE user_aways 
                            SET geselecteerd = TRUE 
                            WHERE away_id = %s AND user_id = %s
                        """, (away_id, nieuwe_gebruiker_id))
        conn.commit()
        conn.close()

    @staticmethod
    def removeNietGeselecteerdeLeden(away_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
                   DELETE FROM user_aways
                    WHERE away_id = %s AND geselecteerd = FALSE
                """, (away_id,))

        conn.commit()
        conn.close()

    @staticmethod
    def getAwayDetailsIdFromGeslotenInschrijvingen():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(''' 
            SELECT id 
            FROM away_details 
            WHERE is_closed = FALSE AND inschrijving_einde < NOW()
        ''')
        closed_inschrijvingen = cursor.fetchall()
        conn.close()
        return closed_inschrijvingen


    @staticmethod
    def getAantalLedenInLijst(away_id):
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
                SELECT COUNT(*) FROM user_aways
                WHERE away_id = %s
                """, (away_id,))

        aantal_leden = cursor.fetchone()[0]
        conn.close()
        return aantal_leden


