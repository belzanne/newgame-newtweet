#!/usr/bin/env python3

import csv
import sqlite3
import requests
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv
import tempfile
from datetime import datetime
import pandas as pd
import re
import logging
import time
import random
from requests.exceptions import RequestException
import pytz



# Charger les variables d'environnement
load_dotenv()

# Configuration du logging
logging.basicConfig(filename='test_populate.log',level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration
GITHUB_REPO = 'steampage-creation-date'
CSV_FILE_PATH = 'steam_games.csv'
TIMESTAMP_FILE = 'tweet_each_day/timestamp_last_tweet.txt'
PARIS_TZ = pytz.timezone('Europe/Paris')
AUTHORIZED_TYPES = ["game", "dlc", 'demo', 'beta', '']



def csv_to_sqlite_temp(csv_url):
    # Télécharger le CSV
    df = pd.read_csv(csv_url)
    
    # Créer une base de données SQLite temporaire
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    conn = sqlite3.connect(temp_db.name)
    
    # Écrire le DataFrame dans la base de données SQLite
    df.to_sql('games', conn, if_exists='replace', index=False)
    
    conn.close()
    return temp_db.name

def get_game_ids_to_process(cursor: sqlite3.Cursor) -> list[int]:
    """Get the list of game ids to process"""
    res = cursor.execute(
        """
        SELECT steam_game_id FROM games
        WHERE steam_game_id NOT IN (
            SELECT game_id FROM steam_games
        )
        AND steam_game_id NOT IN (
            SELECT game_id FROM excluded_games
        )
        ORDER BY steam_game_id ASC
        """
    ).fetchall()
    games_id = [row[0] for row in res]
    return games_id


def create_ultimate_database():
    conn = sqlite3.connect('all-steampages-data.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS steam_games (
        game_id INTEGER PRIMARY KEY,
        add_date INTEGER,
        type TEXT,
        dev TEXT,
        publisher TEXT,
        release_date INTEGER,
        description TEXT,
        nb_reviews INTEGER,
        free INTEGER,
        dlc INTEGER,
        dlc_list TEXT,
        price TEXT,
        metacritic INTEGER,
        genres TEXT,
        singleplayer INTEGER,
        multiplayer INTEGER,
        coop INTEGER,
        online_coop INTEGER,
        lan_coop INTEGER,
        shared_split_screen_coop INTEGER,
        shared_split_screen INTEGER,
        pvp INTEGER,
        lan_pvp INTEGER,
        shared_split_screen_pvp INTEGER,
        achievements INTEGER,
        full_controller_support INTEGER,
        trading_cards INTEGER,
        steam_cloud INTEGER,
        remote_play_phone INTEGER,
        remote_play_tablet INTEGER,
        remote_play_together INTEGER,
        remote_play_tv INTEGER,
        family_sharing INTEGER,
        captions_available INTEGER,
        inapp_purchases INTEGER,
        early_access INTEGER,
        vr_only INTEGER,
        vr_supported INTEGER,
        online_pvp INTEGER,
        required_age INTEGER,
        controller_support TEXT,
        categories TEXT,
        website TEXT,
        support_mail TEXT,
        support_url TEXT,
        cd_some_nudity_or_sexual_content INTEGER,
        cd_frequent_violence_gore INTEGER,
        cd_adult_only_sexual_content INTEGER,
        cd_frequent_nudity_or_sexual_content INTEGER,
        cd_general_mature_content INTEGER,
        lg_en INTEGER,
        lg_ger INTEGER,
        lg_spa INTEGER,
        lg_jap INTEGER,
        lg_portuguese INTEGER,
        lg_russian INTEGER,
        lg_simp_chin INTEGER,
        lg_trad_chin INTEGER,
        lg_fr INTEGER,
        lg_it INTEGER,
        lg_hung INTEGER,
        lg_kor INTEGER,
        lg_turk INTEGER,
        lg_arabic INTEGER,
        lg_polish INTEGER,
        lg_thai INTEGER,
        lg_viet INTEGER
        ai_generated INTEGER,
        ai_content TEXT,
        tags TEXT, 
        steam_x_handle TEXT
    )
    ''')

    conn.commit()
    return conn

def create_excluded_database():
    conn = sqlite3.connect('excluded_games.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS excluded_games (
        game_id INTEGER PRIMARY KEY
    )
    ''')

    conn.commit()
    return conn


def insert_excluded_games(cursor: sqlite3.Cursor, game_data):
    game_id = game_data['steam_appid']
    
    cursor.execute('''
    INSERT INTO excluded_games (
        game_id
    ) VALUES (?)
    ''', (game_id,))

    return True


def parse_release_date(date_str):
    if date_str in ["Coming soon", "To be announced"]:
        return None
    try:
        if "Q" in date_str:
            year = int(date_str.split()[-1])
            quarter = int(date_str[1])
            month = (quarter - 1) * 3 + 1
            return int(datetime(year, month, 1).timestamp())
        elif len(date_str.split()) == 2:
            return int(datetime.strptime(f"1 {date_str}", "%d %B %Y").timestamp())
        else:
            return int(datetime.strptime(date_str, "%d %b, %Y").timestamp())
    except:
        return None


def insert_game_data(cursor: sqlite3.Cursor, game_data: dict, scrap_data: dict):
    # Extraction et transformation des données
    game_id = game_data['steam_appid']
    add_date = int(time.time())
    game_type = game_data.get('type', '')
    dev = ', '.join(game_data.get('developers', []))
    publisher = ', '.join(game_data.get('publishers', []))
    release_date = parse_release_date(game_data.get('release_date', {}).get('date', ''))
    description = game_data.get('short_description', '')
    nb_reviews = game_data.get('recommendations', {}).get('total', 0)
    free = 1 if game_data.get('is_free', False) else 0
    dlc = 1 if game_type == 'dlc' else 0
    dlc_list = ','.join(map(str, game_data.get('dlc', [])))
    price = game_data.get('price_overview', {}).get('final_formatted', '')
    metacritic = game_data.get('metacritic', {}).get('score', None)
    genres = ','.join([genre['description'] for genre in game_data.get('genres', [])])
    
    categories = game_data.get('categories', [])
    category_ids = [cat['id'] for cat in categories]
    
    singleplayer = 1 if 2 in category_ids else 0
    multiplayer = 1 if 1 in category_ids else 0
    coop = 1 if 9 in category_ids else 0
    online_coop = 1 if 38 in category_ids else 0
    lan_coop = 1 if 48 in category_ids else 0
    shared_split_screen_coop = 1 if 39 in category_ids else 0
    shared_split_screen = 1 if 24 in category_ids else 0
    pvp = 1 if 49 in category_ids else 0
    lan_pvp = 1 if 47 in category_ids else 0
    shared_split_screen_pvp = 1 if 37 in category_ids else 0
    achievements = 1 if 22 in category_ids else 0
    full_controller_support = 1 if 28 in category_ids else 0
    trading_cards = 1 if 29 in category_ids else 0
    steam_cloud = 1 if 23 in category_ids else 0
    remote_play_phone = 1 if 41 in category_ids else 0
    remote_play_tablet = 1 if 42 in category_ids else 0
    remote_play_together = 1 if 44 in category_ids else 0
    remote_play_tv = 1 if 43 in category_ids else 0
    family_sharing = 1 if 62 in category_ids else 0
    captions_available = 1 if 13 in category_ids else 0
    inapp_purchases = 1 if 35 in category_ids else 0
    
    early_access = 1 if '70' in [genre['id'] for genre in game_data.get('genres', [])] else 0
    vr_only = 1 if 54 in category_ids else 0
    vr_supported = 1 if 53 in category_ids else 0
    online_pvp = 1 if 36 in category_ids else 0
    
    required_age = game_data.get('required_age', 0)
    controller_support = game_data.get('controller_support', '')
    website = game_data.get('website', '')
    categories_str = ','.join([cat['description'] for cat in categories])
    support_info = game_data.get('support_info', {})
    support_mail = support_info.get('email', '')
    support_url = support_info.get('url', '')
    
    content_descriptors = game_data.get('content_descriptors', {}).get('ids', [])
    cd_some_nudity_or_sexual_content = 1 if 1 in content_descriptors else 0
    cd_frequent_violence_gore = 1 if 2 in content_descriptors else 0
    cd_adult_only_sexual_content = 1 if 3 in content_descriptors else 0
    cd_frequent_nudity_or_sexual_content = 1 if 4 in content_descriptors else 0
    cd_general_mature_content = 1 if 5 in content_descriptors else 0
    
    supported_languages = game_data.get('supported_languages', '')
    lg_en = 1 if 'English' in supported_languages else 0
    lg_ger = 1 if 'German' in supported_languages else 0
    lg_spa = 1 if 'Spanish - Spain' in supported_languages else 0
    lg_jap = 1 if 'Japanese' in supported_languages else 0
    lg_portuguese = 1 if 'Portuguese - Brazil' in supported_languages else 0
    lg_russian = 1 if 'Russian' in supported_languages else 0
    lg_simp_chin = 1 if 'Simplified Chinese' in supported_languages else 0
    lg_trad_chin = 1 if 'Traditional Chinese' in supported_languages else 0
    lg_fr = 1 if 'French' in supported_languages else 0
    lg_it = 1 if 'Italian' in supported_languages else 0
    lg_hung = 1 if 'Hungarian' in supported_languages else 0
    lg_kor = 1 if 'Korean' in supported_languages else 0
    lg_turk = 1 if 'Turkish' in supported_languages else 0
    lg_arabic = 1 if 'Arabic' in supported_languages else 0
    lg_polish = 1 if 'Polish' in supported_languages else 0
    lg_thai = 1 if 'Thai' in supported_languages else 0
    lg_viet = 1 if 'Vietnamese' in supported_languages else 0

    ai_generated = scrap_data['ai_generated']
    ai_content = scrap_data['ai_content']
    tags = ','.join(scrap_data['tags']) 
    steam_x_handle = scrap_data['x_handle']

    
    # Insertion des données dans la base de données
    cursor.execute('''
    INSERT INTO steam_games (
        game_id, add_date, type, dev, publisher, release_date, description, nb_reviews,
        free, dlc, dlc_list, price, metacritic, genres, singleplayer, multiplayer,
        coop, online_coop, lan_coop, shared_split_screen_coop, shared_split_screen,
        pvp, lan_pvp, shared_split_screen_pvp, achievements, full_controller_support,
        trading_cards, steam_cloud, remote_play_phone, remote_play_tablet,
        remote_play_together, remote_play_tv, family_sharing, captions_available,
        inapp_purchases, early_access, vr_only, vr_supported, online_pvp,
        required_age, controller_support, categories, website, support_mail,
        support_url, cd_some_nudity_or_sexual_content,
        cd_frequent_violence_gore, cd_adult_only_sexual_content,
        cd_frequent_nudity_or_sexual_content, cd_general_mature_content,
        lg_en, lg_ger, lg_spa, lg_jap, lg_portuguese, lg_russian, lg_simp_chin,
        lg_trad_chin, lg_fr, lg_it, lg_hung, lg_kor, lg_turk, lg_arabic,
        lg_polish, lg_thai, lg_viet, ai_generated, ai_content, tags, steam_x_handle
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (game_id, add_date, game_type, dev, publisher, release_date, description, nb_reviews,
        free, dlc, dlc_list, price, metacritic, genres, singleplayer, multiplayer,
        coop, online_coop, lan_coop, shared_split_screen_coop, shared_split_screen,
        pvp, lan_pvp, shared_split_screen_pvp, achievements, full_controller_support,
        trading_cards, steam_cloud, remote_play_phone, remote_play_tablet,
        remote_play_together, remote_play_tv, family_sharing, captions_available,
        inapp_purchases, early_access, vr_only, vr_supported, online_pvp,
        required_age, controller_support, categories_str, website, support_mail,
        support_url, cd_some_nudity_or_sexual_content,
        cd_frequent_violence_gore, cd_adult_only_sexual_content,
        cd_frequent_nudity_or_sexual_content, cd_general_mature_content,
        lg_en, lg_ger, lg_spa, lg_jap, lg_portuguese, lg_russian, lg_simp_chin,
        lg_trad_chin, lg_fr, lg_it, lg_hung, lg_kor, lg_turk, lg_arabic,
        lg_polish, lg_thai, lg_viet, ai_generated, ai_content, tags, steam_x_handle
    ))

    return True


def download_csv(url, local_path):
    response = requests.get(url)
    if response.status_code == 200:
        with open(local_path, 'wb') as f:
            f.write(response.content)
        return True
    print(f"Échec du téléchargement du fichier CSV. Code de statut: {response.status_code}")
    return False

def read_csv(csv_path):
    with open(csv_path, 'r', newline='') as f:
        return list(csv.reader(f))


def get_game_details(steam_game_id):
    url = f"https://store.steampowered.com/api/appdetails?appids={steam_game_id}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data[str(steam_game_id)]['success']:
            return data[str(steam_game_id)]['data']
    return None


def scrap_steam_page_info(app_id):
    url = f"https://store.steampowered.com/app/{app_id}/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Vérifier la présence de contenu généré par IA
        ai_disclosure = soup.find(string=re.compile("AI GENERATED CONTENT DISCLOSURE", re.IGNORECASE))
        
        # Recherche de la section "AI Generated Content Disclosure"
        ai_section = soup.find('h2', string='AI Generated Content Disclosure')
        ai_generated = bool(ai_section)
        ai_content = None
        if ai_generated:
            ai_paragraph = ai_section.find_next('i')
            if ai_paragraph:
                ai_content = ai_paragraph.text.strip()


        # Récupérer les tags
        tag_elements = soup.find_all('a', class_='app_tag')
        tags = [tag.text.strip() for tag in tag_elements]
        
        # Récupérer le lien Twitter s'il existe
        twitter_link = soup.find('a', class_="ttip", attrs={'data-tooltip-text': lambda x: x and 'x.com/' in x})
        x_handle = None
        if twitter_link:
            twitter_url = twitter_link['data-tooltip-text']
            x_handle = '@' + twitter_url.split('/')[-1]
        
        return {
            'ai_generated': bool(ai_disclosure),
            'ai_content': ai_content,
            'tags': tags,
            'x_handle': x_handle
        }
    except Exception as e:
        logging.error(f"Erreur lors du scraping pour le jeu {app_id}: {e}")
        return None


def main():
    logging.info("Début de l'exécution de main()")
    try:
        csv_url = f"https://raw.githubusercontent.com/belzanne/{GITHUB_REPO}/main/{CSV_FILE_PATH}"
        logging.info(f"URL de la base de données : {csv_url}")

        # Créer la base de données temporaire à partir du CSV
        temp_db_path = csv_to_sqlite_temp(csv_url)
        logging.info(f"Base de données temporaire créée à : {temp_db_path}")

        ultimate_conn = create_ultimate_database()
        excluded_conn = create_excluded_database()

        # Attacher les bases de données
        ultimate_conn.execute(f"ATTACH '{temp_db_path}' AS games")
        ultimate_conn.execute(f"ATTACH 'excluded_games.db' AS excluded_games")

        cursor = ultimate_conn.cursor()

        # Obtenir la liste des jeux à traiter
        games_to_process = get_game_ids_to_process(cursor)
        logging.info(f"Nombre de jeux à traiter : {len(games_to_process)}")

        total_games = len(games_to_process)
        processed_games = 0

        for steam_game_id in games_to_process:
            #logging.info(f"Traitement du jeu : Steam ID: {steam_game_id}")
            
            id_data = get_game_details(steam_game_id)

            if id_data:
                scrap_data = scrap_steam_page_info(steam_game_id)
                
                if id_data['type'] in AUTHORIZED_TYPES:
                    try:
                        insert_game_data(cursor, id_data, scrap_data)
                        ultimate_conn.commit()
                        logging.info(f'Jeu {steam_game_id} ajouté à la base de données ultimate')
                        processed_games += 1
                    except Exception as e:
                        logging.error(f"Erreur lors de l'insertion de l'id_data {steam_game_id} dans ultimate db: {str(e)}")
                        insert_excluded_games(excluded_conn.cursor(), id_data)
                        excluded_conn.commit()
                else:
                    logging.info(f'Type non autorisé pour {steam_game_id}. Ajout à la base de données excluded')
                    insert_excluded_games(excluded_conn.cursor(), id_data)
                    excluded_conn.commit()
            else:
                logging.info(f"Impossible de récupérer les détails pour le jeu avec Steam ID {steam_game_id}")
            
            time.sleep(random.uniform(1.1, 1.4))

        # Nettoyage
        ultimate_conn.execute("DETACH games")
        ultimate_conn.execute("DETACH excluded_games")
        ultimate_conn.close()
        excluded_conn.close()
        os.unlink(temp_db_path)
        logging.info("Fichier temporaire de la base de données supprimé")

        logging.info(f"\nRésumé : {processed_games} jeux ajoutés sur {total_games} jeux à traiter.")
        
        return total_games, processed_games, csv_url

    except Exception as e:
        logging.exception(f"Une erreur inattendue s'est produite dans main(): {str(e)}")
        return None
    


if __name__ == "__main__":
    try:
        result = main()
        if result is not None:
            total_games, processed_games, csv_url = result
            print(f"\nRésumé : {processed_games} jeux ajoutés sur {total_games} nouveaux jeux repérés.")
        else:
            logging.error("La fonction main() a retourné None")
            print("Une erreur s'est produite lors de l'exécution. Veuillez consulter le fichier de log pour plus de détails.")

    except Exception as e:
        logging.exception(f"Une erreur s'est produite lors de l'exécution : {str(e)}")
        print(f"Une erreur s'est produite. Veuillez consulter le fichier de log pour plus de détails.")