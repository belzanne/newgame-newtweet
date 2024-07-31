import sqlite3
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import time
import logging

# Configuration du logging
logging.basicConfig(filename='log_file.log', level=logging.INFO,
                    format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')


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

    logging.info("Connected to database")

    # Vérifier si la table existe et la créer si nécessaire
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS developer_social_media (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        add_date INTEGER,
        game_id INTEGER,
        twitter_handle TEXT,
        scrap_date INTEGER,
        followers_count TEXT,
        following_count TEXT,
        tweets_count TEXT,
        creation_date TEXT
    )
    ''')

    current_timestamp = int(time.time())
    three_months_ago = current_timestamp - (90 * 24 * 60 * 60)  # 90 jours en secondes

    # Récupérer les handles qui n'ont jamais été scrapés ou qui n'ont pas été scrapés depuis plus de 3 mois
    cursor.execute('''
    SELECT id, game_id, twitter_handle, add_date, scrap_date
    FROM developer_social_media
    WHERE scrap_date IS NULL
       OR (scrap_date < ? AND id IN (
           SELECT MAX(id)
           FROM developer_social_media
           GROUP BY game_id, twitter_handle
       ))
    ''', (three_months_ago,))

    handles_to_scrape = cursor.fetchall()

    logging.info(f"Found {len(handles_to_scrape)} Twitter handles to process")

    for row in handles_to_scrape:
        id, game_id, handle, add_date, last_scrap_date = row
        if handle.startswith('@'):
            handle = handle[1:]  # Enlever le @ si présent
        
        logging.info(f"Processing {handle}...")
        data = scrape_social_blade(handle)
        scrap_timestamp = current_timestamp

        if last_scrap_date is None:
            # Premier scraping : mettre à jour la ligne existante
            logging.info(f"Updating existing entry for {handle}")
            cursor.execute('''
            UPDATE developer_social_media 
            SET scrap_date = ?, followers_count = ?, following_count = ?, tweets_count = ?, creation_date = ?
            WHERE id = ?
            ''', (scrap_timestamp, data.get('followers', 'N/A'), data.get('following', 'N/A'), 
                  data.get('tweets', 'N/A'), data.get('created_date', 'N/A'), id))
        else:
            # Scraping ultérieur : insérer une nouvelle ligne
            logging.info(f"Inserting new data for {handle}")
            cursor.execute('''
            INSERT INTO developer_social_media 
            (game_id, twitter_handle, add_date, scrap_date, followers_count, following_count, tweets_count, creation_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (game_id, '@' + handle, add_date, scrap_timestamp, data.get('followers', 'N/A'), 
                  data.get('following', 'N/A'), data.get('tweets', 'N/A'), data.get('created_date', 'N/A')))

        conn.commit()
        logging.info(f"Data committed for {handle}")
        time.sleep(5)  # Pause de 5 secondes entre chaque requête

    # Vérifier les données après mise à jour
    cursor.execute("SELECT * FROM developer_social_media ORDER BY scrap_date DESC LIMIT 5")
    rows = cursor.fetchall()
    logging.info("After update, displaying the 5 most recent entries:")
    for row in rows:
        logging.info(row)

    conn.close()
    logging.info("Database update completed and connection closed.")

if __name__ == "__main__":
    update_database()

#todo : pour ne pas qu'il récupère tous les handle tous les jours, stocker derniere date d'execution et faire scrapping que pour ceux avec une date d'exeuction veille ou il y a 3 mois pour actualisation
#faire que main.py ajoute une date quand stocke handle ? Pour tracer date rapatriement et faire les actualisationn t+3mois, +6mois etc