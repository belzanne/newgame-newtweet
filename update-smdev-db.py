import sqlite3
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
import time
import logging

# Configuration du logging
logging.basicConfig(filename='smdev_update_log.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

def scrape_social_blade(handle):
    url = f"https://socialblade.com/twitter/user/{handle}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        data = {}
        for item in ['followers', 'following', 'tweets']:
            element = soup.find('span', string=re.compile(item, re.IGNORECASE))
            if element:
                value = element.find_next('span').text.strip()
                data[item] = int(value.replace(',', ''))
            else:
                data[item] = None
        
        created_element = soup.find('span', string=re.compile("User Created", re.IGNORECASE))
        if created_element:
            created_date = created_element.find_next('span').text.strip()
            data['created_date'] = parse_date(created_date)
        else:
            data['created_date'] = None
        
        logging.info(f"Data scraped for {handle}: {data}")
        return data
    except Exception as e:
        logging.error(f"Error scraping data for {handle}: {str(e)}")
        return None

def parse_date(date_string):
    months = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
        'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
    }
    match = re.match(r'(\w{3})\s(\d{1,2})(?:st|nd|rd|th)?,\s(\d{4})', date_string)
    if match:
        month, day, year = match.groups()
        return f"{year}-{months[month]}-{day.zfill(2)}"
    return None

def update_database():
    conn = sqlite3.connect('socialmedia-developer.db')
    cursor = conn.cursor()

    logging.info("Connected to database")

    try:
        # Assurez-vous que la table existe
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS socialmedia_dev (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            add_date INTEGER,
            game_id INTEGER,
            twitter_handle TEXT,
            scrap_date INTEGER,
            followers_count INTEGER,
            following_count INTEGER,
            tweets_count INTEGER,
            creation_date TEXT
        )
        ''')

        current_timestamp = int(time.time())
        three_months_ago = current_timestamp - (90 * 24 * 60 * 60)  # 90 jours en secondes

        # Récupérer les handles qui n'ont jamais été scrapés ou qui n'ont pas été scrapés depuis plus de 3 mois
        cursor.execute('''
        SELECT id, game_id, twitter_handle, add_date, scrap_date
        FROM socialmedia_dev
        WHERE scrap_date IS NULL
           OR (scrap_date < ? AND id IN (
               SELECT MAX(id)
               FROM socialmedia_dev
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
            
            if data:
                scrap_timestamp = current_timestamp
                
                # Insérer une nouvelle ligne avec les données mises à jour
                cursor.execute('''
                INSERT INTO socialmedia_dev 
                (game_id, twitter_handle, add_date, scrap_date, followers_count, following_count, tweets_count, creation_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (game_id, '@' + handle, add_date, scrap_timestamp, data.get('followers'), 
                      data.get('following'), data.get('tweets'), data.get('created_date')))

                conn.commit()
                logging.info(f"Data committed for {handle}")
            else:
                logging.warning(f"No data scraped for {handle}, skipping update")

            time.sleep(5)  # Pause de 5 secondes entre chaque requête

        # Vérifier les données après mise à jour
        cursor.execute("SELECT * FROM socialmedia_dev ORDER BY scrap_date DESC LIMIT 5")
        rows = cursor.fetchall()
        logging.info("After update, displaying the 5 most recent entries:")
        for row in rows:
            logging.info(row)

    except sqlite3.Error as e:
        logging.error(f"SQLite error: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
    finally:
        conn.close()
        logging.info("Database connection closed.")

if __name__ == "__main__":
    update_database()