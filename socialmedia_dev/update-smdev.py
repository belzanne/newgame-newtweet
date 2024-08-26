#!/usr/local/bin/python3

import sqlite3
import requests
from bs4 import BeautifulSoup
import re
import time
import logging
from datetime import datetime
import os
import subprocess

# Configuration du logging
logging.basicConfig(filename='smdev_update_log.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def scrape_x(handle):
    """
    Scrape les données de SocialBlade pour un handle Twitter donné.
    
    Args:
    handle (str): Le handle Twitter à scraper.

    Returns:
    dict: Un dictionnaire contenant les données scrapées, ou None en cas d'échec.
    """
    url = f"https://socialblade.com/twitter/user/{handle}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=30)
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
            
            logging.info(f"Données scrapées pour {handle}: {data}")
            return data
        except Exception as e:
            logging.warning(f"Tentative {attempt + 1} échouée pour {handle}: {str(e)}")
            if attempt == max_retries - 1:
                logging.error(f"Toutes les tentatives ont échoué pour {handle}")
                return None
            time.sleep(40)  # Attendre avant de réessayer

def scrape_youtube(handle):
    url = f"https://socialblade.com/youtube/channel/{handle}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        data = {}
        
        # Extraire le nombre de vues
        yt_views = soup.select_one('div.YouTubeUserTopInfo:-soup-contains("Video Views") span[style="font-weight: bold;"]')
        data['yt_views'] = int(yt_views.text.strip().replace(',', '')) if yt_views else None

        # Extraire la date de création
        yt_creation_date = soup.select_one('div.YouTubeUserTopInfo:-soup-contains("User Created") span[style="font-weight: bold;"]')
        if yt_creation_date:
            data['yt_creation_date'] = parse_date(yt_creation_date.text.strip())
        else:
            data['yt_creation_date'] = None
        
        # Extraire le nombre d'uploads
        uploads_element = soup.find('span', id='youtube-stats-header-uploads')
        data['yt_uploads'] = int(uploads_element.text.strip()) if uploads_element else None

        # Extraire le nombre d'abonnés
        subscribers_element = soup.find('span', id='youtube-stats-header-subs')
        data['yt_subscribers'] = int(subscribers_element.text.strip()) if subscribers_element else None

        logging.info(f"Données YouTube scrapées pour {handle}: {data}")
        return data
    except Exception as e:
        logging.warning(f"Échec du scraping YouTube pour {handle}: {str(e)}")
        return None

def parse_date(date_string):
    """
    Parse une date au format "Mois Jour, Année" en timestamp Unix.
    """
    months = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
        'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
    }
    match = re.match(r'(\w{3})\s(\d{1,2})(?:st|nd|rd|th)?,\s(\d{4})', date_string)
    if match:
        month, day, year = match.groups()
        date_obj = datetime.strptime(f"{year}-{months[month]}-{day.zfill(2)}", "%Y-%m-%d")
        return int(date_obj.timestamp())
    return None

def git_pull():
    try:
        subprocess.run(["git", "pull"], check=True)
        logging.info("Git pull réussi")
    except subprocess.CalledProcessError as e:
        logging.error(f"Erreur lors du git pull: {str(e)}")
        raise

def git_push():
    try:
        subprocess.run(["git", "add", "socialmedia-developer.db"], check=True)
        subprocess.run(["git", "commit", "-m", "Mise à jour de la base de données"], check=True)
        subprocess.run(["git", "push"], check=True)
        logging.info("Git push réussi")
    except subprocess.CalledProcessError as e:
        logging.error(f"Erreur lors du git push: {str(e)}")
        raise

def update_database():
    """
    Fonction principale pour mettre à jour la base de données avec les données scrapées.
    """

    # Assurez-vous d'être dans le bon répertoire
    repo_dir = "/Users/juliebelzanne/Documents/Hush_Crasher/steam_data/newgame-newtweet"
    os.chdir(repo_dir)
   
   # Pull les dernières modifications
    try:
        git_pull()
        logging.info("Git pulled")
    except Exception as e:
        logging.error(f"Erreur lors du git pull: {str(e)}")
        
    db_path = os.path.join(repo_dir, "socialmedia_dev", "socialmedia-developer.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    logging.info("Connecté à la base de données")

    try:
        # Assurez-vous que la table existe
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS socialmedia_dev (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            add_date INTEGER,
            game_id INTEGER,
            x_handle TEXT,
            scrap_date INTEGER,
            x_followers INTEGER,
            x_following INTEGER,
            tweets_count INTEGER,
            x_creation_date INTEGER,
            yt_views INTEGER,
            yt_creation_date INTEGER,
            yt_uploads INTEGER,
            yt_subscribers INTEGER
        )
        ''')

        current_timestamp = int(time.time())
        three_months_ago = current_timestamp - (90 * 24 * 60 * 60)  # 90 jours en secondes

        # Récupérer les handles à scraper
        cursor.execute('''
        SELECT id, game_id, x_handle, add_date, scrap_date
        FROM socialmedia_dev
        WHERE scrap_date IS NULL
           OR (scrap_date < ? AND id IN (
               SELECT MAX(id)
               FROM socialmedia_dev
               GROUP BY game_id, x_handle
           ))
        ''', (three_months_ago,))

        handles_to_scrape = cursor.fetchall()

        logging.info(f"Trouvé {len(handles_to_scrape)} handles Twitter à traiter")

        for row in handles_to_scrape:
            id, game_id, handle, add_date, last_scrap_date = row
            if handle.startswith('@'):
                handle = handle[1:]  # Enlever le @ si présent
            
            logging.info(f"Traitement de {handle}...")
            twitter_data = scrape_x(handle)
            
            # Tentative de scraping YouTube
            youtube_data = scrape_youtube(handle)
            
            if twitter_data or youtube_data:
                scrap_timestamp = current_timestamp
                
                if last_scrap_date is None:
                    # Premier scraping : mettre à jour la ligne existante
                    cursor.execute('''
                    UPDATE socialmedia_dev 
                    SET scrap_date = ?, x_followers = ?, x_following = ?, tweets_count = ?, x_creation_date = ?,
                        yt_views = ?, yt_creation_date = ?, yt_uploads = ?, yt_subscribers = ?
                    WHERE id = ?
                    ''', (scrap_timestamp, 
                          twitter_data.get('followers') if twitter_data else None, 
                          twitter_data.get('following') if twitter_data else None, 
                          twitter_data.get('tweets') if twitter_data else None, 
                          twitter_data.get('created_date') if twitter_data else None,
                          youtube_data.get('yt_views') if youtube_data else None,
                          youtube_data.get('yt_creation_date') if youtube_data else None,
                          youtube_data.get('yt_uploads') if youtube_data else None,
                          youtube_data.get('yt_subscribers') if youtube_data else None,
                          id))
                else:
                    # Scraping ultérieur : insérer une nouvelle ligne
                    cursor.execute('''
                    INSERT INTO socialmedia_dev 
                    (game_id, x_handle, add_date, scrap_date, x_followers, x_following, tweets_count, x_creation_date,
                     yt_views, yt_creation_date, yt_uploads, yt_subscribers)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (game_id, '@' + handle, add_date, scrap_timestamp, 
                          twitter_data.get('followers') if twitter_data else None, 
                          twitter_data.get('following') if twitter_data else None, 
                          twitter_data.get('tweets') if twitter_data else None, 
                          twitter_data.get('created_date') if twitter_data else None,
                          youtube_data.get('yt_views') if youtube_data else None,
                          youtube_data.get('yt_creation_date') if youtube_data else None,
                          youtube_data.get('yt_uploads') if youtube_data else None,
                          youtube_data.get('yt_subscribers') if youtube_data else None))

                conn.commit()
                logging.info(f"Données enregistrées pour {handle}")
            else:
                logging.warning(f"Aucune donnée scrapée pour {handle}, mise à jour ignorée")

            time.sleep(40)  # Pause de 40 secondes entre chaque requête

    except sqlite3.Error as e:
        logging.error(f"Erreur SQLite: {str(e)}")
    except Exception as e:
        logging.error(f"Erreur inattendue: {str(e)}")
    finally:
        conn.close()
        logging.info("Connexion à la base de données fermée.")

        # Push les modifications
        try:
            git_push()
            logging.info("Git pushed")
        except Exception as e:
            logging.error(f"Erreur lors du git push: {str(e)}")

if __name__ == "__main__":
    update_database()