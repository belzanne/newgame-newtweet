import sqlite3
import requests
from bs4 import BeautifulSoup
import re
import time
import logging
from datetime import datetime

# Configuration du logging
logging.basicConfig(filename='smdev_update_log.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def get_proxy():
    """
    Obtient une liste de proxies depuis un service en ligne.
    Retourne: Un dictionnaire contenant un proxy à utiliser.
    """
    proxy_url = "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all"
    try:
        response = requests.get(proxy_url)
        proxies = response.text.strip().split('\r\n')
        return {'http': f'http://{proxies[0]}', 'https': f'https://{proxies[0]}'}
    except Exception as e:
        logging.error(f"Erreur lors de l'obtention du proxy : {str(e)}")
        return None

def scrape_social_blade(handle):
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
            proxy = get_proxy()
            response = requests.get(url, headers=headers, proxies=proxy, timeout=30)
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
            time.sleep(5)  # Attendre avant de réessayer

def parse_date(date_string):
    """
    Parse une date au format "Mois Jour, Année" en format "YYYY-MM-DD".
    """
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
    """
    Fonction principale pour mettre à jour la base de données avec les données scrapées.
    """
    conn = sqlite3.connect('socialmedia-developer.db')
    cursor = conn.cursor()

    logging.info("Connecté à la base de données")

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

        # Récupérer les handles à scraper
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

        logging.info(f"Trouvé {len(handles_to_scrape)} handles Twitter à traiter")

        for row in handles_to_scrape:
            id, game_id, handle, add_date, last_scrap_date = row
            if handle.startswith('@'):
                handle = handle[1:]  # Enlever le @ si présent
            
            logging.info(f"Traitement de {handle}...")
            data = scrape_social_blade(handle)
            
            if data:
                scrap_timestamp = current_timestamp
                
                if last_scrap_date is None:
                    # Premier scraping : mettre à jour la ligne existante
                    cursor.execute('''
                    UPDATE socialmedia_dev 
                    SET scrap_date = ?, followers_count = ?, following_count = ?, tweets_count = ?, creation_date = ?
                    WHERE id = ?
                    ''', (scrap_timestamp, data.get('followers'), data.get('following'), 
                          data.get('tweets'), data.get('created_date'), id))
                else:
                    # Scraping ultérieur : insérer une nouvelle ligne
                    cursor.execute('''
                    INSERT INTO socialmedia_dev 
                    (game_id, twitter_handle, add_date, scrap_date, followers_count, following_count, tweets_count, creation_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (game_id, '@' + handle, add_date, scrap_timestamp, data.get('followers'), 
                          data.get('following'), data.get('tweets'), data.get('created_date')))

                conn.commit()
                logging.info(f"Données enregistrées pour {handle}")
            else:
                logging.warning(f"Aucune donnée scrapée pour {handle}, mise à jour ignorée")

            time.sleep(5)  # Pause de 5 secondes entre chaque requête

        # Vérifier les données après mise à jour
        cursor.execute("SELECT * FROM socialmedia_dev ORDER BY scrap_date DESC LIMIT 5")
        rows = cursor.fetchall()
        logging.info("Après la mise à jour, affichage des 5 entrées les plus récentes:")
        for row in rows:
            logging.info(row)

    except sqlite3.Error as e:
        logging.error(f"Erreur SQLite: {str(e)}")
    except Exception as e:
        logging.error(f"Erreur inattendue: {str(e)}")
    finally:
        conn.close()
        logging.info("Connexion à la base de données fermée.")

if __name__ == "__main__":
    update_database()