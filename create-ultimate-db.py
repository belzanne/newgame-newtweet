import sqlite3
import csv
import requests
import time
from bs4 import BeautifulSoup
from datetime import datetime
import os
import logging
import tempfile
import random
from tqdm import tqdm

# Configuration du logging
logging.basicConfig(
    filename="ultimate-db.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

BATCH_SIZE = 100
LOG_FREQ = 1000

def create_database():
    conn = sqlite3.connect('all-steampages-data.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS steam_games (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER,
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
    )
    ''')
    
    conn.commit()
    return conn

def get_steam_data(app_id):
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data[str(app_id)]['success']:
            return data[str(app_id)]['data']
    return None

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

def insert_game_data(cursor, game_data):
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
    
    # Insertion des données dans la base de données
    cursor.execute('''
    INSERT INTO steam_games (
        id, game_id, add_date, type, dev, publisher, release_date, description, nb_reviews,
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
        lg_polish, lg_thai, lg_viet
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (None,
        game_id, add_date, game_type, dev, publisher, release_date, description, nb_reviews,
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
        lg_polish, lg_thai, lg_viet
    ))
    
def download_steam_games_csv():
    """Download the CSV file of Steam games"""
    csv_url = f"https://raw.githubusercontent.com/belzanne/steampage-creation-date/main/steam_games.csv"
    response = requests.get(csv_url)
    if response.status_code == 200:
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.csv', newline='') as temp_file:
            temp_file.write(response.text)
            return temp_file.name
    else:
        logging.error(f"Échec du téléchargement de steam_games.csv. Status code: {response.status_code}")
        return None

def get_game_ids_to_process(csv_path, conn):
    """Get the list of game ids to process from the CSV file"""
    cursor = conn.cursor()
    cursor.execute("SELECT game_id FROM steam_games")
    processed_games = set(row[0] for row in cursor.fetchall())

    game_ids = []
    with open(csv_path, 'r', newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            steam_game_id = int(row['steam_game_id'])
            if steam_game_id not in processed_games:
                game_ids.append(steam_game_id)
    
    return game_ids

def log_last_update(cursor: sqlite3.Cursor, game_id: int) -> bool:
    timestamp = int(time.time())
    try:
        cursor.execute(
            """ 
            INSERT OR REPLACE INTO last_gameid_for_ultimate (
                game_id, timestamp_last_gameid)
                VALUES (?, ?)
            """,
            (game_id, timestamp),
        )
        return True
    except Exception as e:
        logging.error(
            f"Unexpected error when logging last update for game_id {game_id}: {e}"
        )

    return False

def main():
    # Créer ou se connecter à la base de données ultime
    ultimate_conn = create_database()
    
    # Télécharger le fichier CSV des jeux Steam
    steam_games_csv_path = download_steam_games_csv()

    # Attach the Steam games database to the game_reviews.db
    ultimate_conn.execute(f"ATTACH '{steam_games_csv_path}' AS games")
    
    if not steam_games_csv_path:
        logging.error("Impossible de télécharger le fichier CSV. Arrêt du script.")
        return
    
    # Obtenir tous les game_id à traiter
    all_game_ids = get_game_ids_to_process(steam_games_csv_path, ultimate_conn)
    total_games = len(all_game_ids)
    logging.info(f"Total des jeux à traiter : {total_games}")
    
    cursor = ultimate_conn.cursor()  # Créez un curseur ici
    
    # Traiter les jeux par lots
    for start_idx in range(0, total_games, BATCH_SIZE):
        end_idx = min(start_idx + BATCH_SIZE, total_games)
        batch_game_ids = all_game_ids[start_idx:end_idx]
        
        logging.info(f"Traitement du lot {start_idx//BATCH_SIZE + 1}, jeux {start_idx+1} à {end_idx}")
        
        for i, game_id in enumerate(tqdm(batch_game_ids)):
            game_data = get_steam_data(game_id)
            log_last_update(ultimate_conn, game_id, n_reviews > 0)
            if game_data:
                if insert_game_data(cursor, game_data):
                    if (i + 1) % LOG_FREQ == 0:
                        ultimate_conn.commit()
                        logging.info(f"{i + 1} jeux traités dans ce lot. Dernier game_id : {game_id}")
            
            # Ajouter un délai aléatoire entre les requêtes
            time.sleep(random.uniform(0.3, 1.2))
        
        ultimate_conn.commit()
        logging.info(f"Lot terminé. {end_idx} jeux traités au total.")
    
    ultimate_conn.close()
    os.unlink(steam_games_csv_path)
    logging.info("Traitement terminé. Connexion à la base de données fermée.")

if __name__ == "__main__":
    main()
