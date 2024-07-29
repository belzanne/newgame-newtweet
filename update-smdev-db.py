import sqlite3
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import time

def scrape_social_blade(handle):
    url = f"https://socialblade.com/twitter/user/{handle}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    print(f"Requesting data for {handle} from {url}")
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    data = {}
    
    for item in ['followers', 'following', 'tweets']:
        element = soup.find('span', string=re.compile(item, re.IGNORECASE))
        if element:
            value = element.find_next('span').text.strip()
            data[item] = value
        else:
            data[item] = "N/A"
    
    created_element = soup.find('span', string=re.compile("User Created", re.IGNORECASE))
    if created_element:
        created_date = created_element.find_next('span').text.strip()
        try:
            data['created_date'] = datetime.strptime(created_date, "%b %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            data['created_date'] = created_date
    else:
        data['created_date'] = "N/A"
    
    print(f"Data scraped for {handle}: {data}")
    return data

def update_database():
    conn = sqlite3.connect('socialmedia-developer.db')
    cursor = conn.cursor()

    print("Connected to database")

    # Vérifier si la table existe
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='developer_social_media'")
    if not cursor.fetchone():
        print("Table 'developer_social_media' does not exist. Creating it.")
        cursor.execute('''
        CREATE TABLE developer_social_media (
            game_id INTEGER,
            twitter_handle TEXT,
            execution_date TEXT,
            followers_count TEXT,
            following_count TEXT,
            tweets_count TEXT,
            creation_date TEXT
        )
        ''')
    else:
        print("Table 'socialmedia-developer' already exists.")

    # Récupérer tous les twitter_handles
    cursor.execute("SELECT DISTINCT game_id, twitter_handle FROM developer_social_media WHERE twitter_handle IS NOT NULL")
    handles = cursor.fetchall()

    print(f"Found {len(handles)} Twitter handles to process")

    for game_id, handle in handles:
        if handle.startswith('@'):
            handle = handle[1:]  # Enlever le @ si présent
        
        print(f"Processing {handle}...")
        data = scrape_social_blade(handle)
        execution_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print(f"Inserting/Updating data for {handle}")
        cursor.execute('''
        INSERT OR REPLACE INTO social_media_data 
        (game_id, twitter_handle, execution_date, followers_count, following_count, tweets_count, creation_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (game_id, '@' + handle, execution_date, data.get('followers', 'N/A'), 
              data.get('following', 'N/A'), data.get('tweets', 'N/A'), data.get('created_date', 'N/A')))

        conn.commit()
        print(f"Data committed for {handle}")
        time.sleep(5)  # Pause de 5 secondes entre chaque requête

    # Vérifier les données après mise à jour
    cursor.execute("SELECT * FROM social_media_data")
    rows = cursor.fetchall()
    print(f"After update, found {len(rows)} rows in the database")
    for row in rows[:5]:  # Afficher les 5 premières lignes pour vérification
        print(row)

    conn.close()
    print("Database update completed and connection closed.")

if __name__ == "__main__":
    update_database()

#todo : pour ne pas qu'il récupère tous les handle tous les jours, stocker derniere date d'execution et faire scrapping que pour ceux avec une date d'exeuction veille ou il y a 3 mois pour actualisation
#faire que main.py ajoute une date quand stocke handle ? Pour tracer date rapatriement et faire les actualisationn t+3mois, +6mois etc