import psycopg2

# Verbind met de PostgreSQL-database van Supabase
conn = psycopg2.connect(
    host="db.wnbuhmfqnfbyhpelbygq.supabase.co",  # Hostnaam van je Supabase database
    port=5432,  # Standaard poort voor PostgreSQL
    dbname="postgres",  # Naam van je database
    user="postgres",  # Gebruikersnaam
    password="a!G3N9a$bEJ_4Xk"  # Wachtwoord van je Supabase-database
)

cursor = conn.cursor()
# Vergeet niet de verbinding te sluiten wanneer je klaar bent
cursor.close()
conn.close()
