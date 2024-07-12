import sqlite3

# Nom de la base de données SQLite
DATABASE_NAME = 'database.db'

# Fonction pour se connecter à la base de données
def connect_to_database():
    return sqlite3.connect(DATABASE_NAME)

# Création de la table 'reports' pour stocker les rapports des membres
def create_reports_table():
    connection = connect_to_database()
    cursor = connection.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        member_id INTEGER,
                        report_count INTEGER,
                        UNIQUE(member_id)
                    )''')
    connection.commit()
    connection.close()

# Fonction pour mettre à jour le nombre de rapports d'un membre
def update_report_count(member_id, new_count):
    connection = connect_to_database()
    cursor = connection.cursor()
    cursor.execute('''INSERT INTO reports (member_id, report_count) 
                      VALUES (?, ?) 
                      ON CONFLICT(member_id) 
                      DO UPDATE SET report_count = excluded.report_count''', 
                   (member_id, new_count))
    connection.commit()
    connection.close()

# Fonction pour obtenir le nombre de rapports d'un membre
def get_report_count(member_id):
    connection = connect_to_database()
    cursor = connection.cursor()
    cursor.execute("SELECT report_count FROM reports WHERE member_id = ?", (member_id,))
    result = cursor.fetchone()
    connection.close()
    if result:
        return result[0]
    else:
        return 0

# Création de la table 'snipes' pour enregistrer les messages supprimés
def create_snipes_table():
    connection = connect_to_database()
    cursor = connection.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS snipes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id INTEGER,
                        content TEXT,
                        author_id INTEGER,
                        channel_id INTEGER,
                        deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )''')
    connection.commit()
    connection.close()

# Création de la table 'config' pour stocker la configuration spécifique à chaque serveur Discord
def create_config_table():
    connection = connect_to_database()
    cursor = connection.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS config (
                        guild_id INTEGER PRIMARY KEY,
                        ban_logs_channel_id INTEGER
                    )''')
    connection.commit()
    connection.close()

# Appel des fonctions de création des tables au démarrage
create_reports_table()
create_snipes_table()
create_config_table()
