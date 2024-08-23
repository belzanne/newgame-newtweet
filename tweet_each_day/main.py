import csv
import sqlite3
import requests
from bs4 import BeautifulSoup
import tweepy
import os
from dotenv import load_dotenv
import tempfile
from datetime import datetime
import pytz
from deep_translator import GoogleTranslator
from langdetect import detect, LangDetectException
import html
import pandas as pd
#from duckduckgo_search import DDGS
import re
#from Levenshtein import ratio
import logging
import time
from requests.exceptions import RequestException
import random
from time import sleep


# Configuration du logging
logging.basicConfig(filename='log_file.log', level=logging.INFO,
                    format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

def log_execution(total_games, published_games):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"Exécution du {timestamp}: {published_games} tweets envoyés sur {total_games} jeux traités."
    #logging.info(log_message)
    #logging.info(f"PAT_GITHUB_USERNAME: {os.getenv('PAT_GITHUB_USERNAME')}")
    #logging.info(f"GITHUB_REPO: {GITHUB_REPO}")
    #logging.info(f"CSV_FILE_PATH: {CSV_FILE_PATH}")
    #logging.info(f"URL complète : {csv_url}")
    logging.info(f"Nombre de jeux avec contenu mature (id=3): {MATURE_CONTENT_GAMES}")
    logging.info(f"Nombre de jeux avec contenu généré par IA: {AI_GENERATED_GAMES}")
    print(log_message)

# Charger les variables d'environnement
load_dotenv()

# Configuration
GITHUB_REPO = 'steampage-creation-date'
CSV_FILE_PATH = 'steam_games.csv'
TIMESTAMP_FILE = 'tweet_each_day/timestamp_last_tweet.txt'
PARIS_TZ = pytz.timezone('Europe/Paris')
MAX_TWEETS_PER_DAY = 50
AI_GENERATED_GAMES = 0
MATURE_CONTENT_GAMES = 0
AUTHORIZED_TYPES = ["game", "dlc", 'demo', 'beta', '']


# Initialiser le traducteur
translator = GoogleTranslator(source='auto', target='en')

def read_last_timestamp():
    try:
        with open(TIMESTAMP_FILE, 'r') as f:
            return int(f.read().strip())
    except FileNotFoundError:
        return 0

def write_last_timestamp(timestamp):
    with open(TIMESTAMP_FILE, 'w') as f:
        f.write(str(timestamp))

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

def check_new_entries(csv_data, last_timestamp):
    return [(int(row[1]), int(row[2])) for row in csv_data[1:] if int(row[2]) > last_timestamp]


def get_game_details(steam_game_id):
    url = f"https://store.steampowered.com/api/appdetails?appids={steam_game_id}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data[str(steam_game_id)]['success']:
            return data[str(steam_game_id)]['data']
    return None

def filter_game(game_data):
    global MATURE_CONTENT_GAMES
    if game_data['type'] != 'game' or game_data.get('dlc', False):
        return False
    
    content_descriptors = game_data.get('content_descriptors', {})
    if isinstance(content_descriptors, dict):
        descriptor_ids = content_descriptors.get('ids', [])
    elif isinstance(content_descriptors, list):
        descriptor_ids = content_descriptors
    else:
        descriptor_ids = []
    
    if 3 in descriptor_ids or 4 in descriptor_ids:
        MATURE_CONTENT_GAMES += 1
        return False
    
    supported_languages = game_data.get('supported_languages', '').lower()
    if 'english' not in supported_languages:
        return False
    
    if game_data.get('is_free', True):
        return False
    
    return True

# def get_twitter_client():
#     client = tweepy.Client(
#         consumer_key=os.getenv('TWITTER_CONSUMER_KEY'),
#         consumer_secret=os.getenv('TWITTER_CONSUMER_SECRET'),
#         access_token=os.getenv('TWITTER_ACCESS_TOKEN'),
#         access_token_secret=os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
#     )
#     return client

def get_twitter_client():
    client = tweepy.Client(
        consumer_key=os.getenv('TWITTER_CONSUMER_KEY'),
        consumer_secret=os.getenv('TWITTER_CONSUMER_SECRET'),
        access_token=os.getenv('TWITTER_ACCESS_TOKEN'),
        access_token_secret=os.getenv('TWITTER_ACCESS_TOKEN_SECRET'),
        wait_on_rate_limit=True
    )
    return client

#scrapping
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

def translate_to_english(text):
    try:
        lang = detect(text)
        if lang != 'en':
            translated = translator.translate(text)
            return translated
        return text
    except LangDetectException:
        print(f"Impossible de détecter la langue pour le texte: {text}")
        return text
    except Exception as e:
        print(f"Erreur lors de la traduction : {e}")
        return text

def clean_text(text):
    decoded_text = html.unescape(text)
    cleaned_text = ' '.join(decoded_text.split())
    return cleaned_text

def is_priority_game(game_data):
    publisher = game_data.get('publishers', [])
    developer = game_data.get('developers', [])
    return not publisher or (publisher == developer)

def retry_request(func, max_retries=3, delay=1):
    for attempt in range(max_retries):
        try:
            return func()
        except RequestException as e:
            if attempt == max_retries - 1:
                raise
            print(f"Tentative {attempt + 1} échouée. Nouvelle tentative dans {delay} secondes...")
            time.sleep(delay)
            delay *= 2

def search_brave(query, max_results=5):
    BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY")
    
    headers = {
        "X-Subscription-Token": BRAVE_API_KEY,
        "Accept": "application/json"
    }
    
    url = "https://api.search.brave.com/res/v1/web/search"
    params = {
        "q": query,
        "count": max_results
    }
    
    def make_request():
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    
    try:
        results = retry_request(make_request)
        web_results = results.get('web', {}).get('results', [])
        return pd.DataFrame([{
            'title': result.get('title', ''),
            'url': result.get('url', ''),
            'description': result.get('description', '')
        } for result in web_results])
    except RequestException as e:
        print(f"Erreur lors de la recherche Brave après plusieurs tentatives: {e}")
        return pd.DataFrame()

def is_twitter_link(url):
    url_lower = url.lower()
    return 'twitter.com' in url_lower or 'x.com' in url_lower

def extract_twitter_handle(url):
    match = re.search(r'twitter\.com/(\w+)', url)
    if match:
        return '@' + match.group(1)
    return None

from difflib import SequenceMatcher

def name_similarity(name1, name2):
    return SequenceMatcher(None, name1.lower(), name2.lower()).ratio()
#def name_similarity(name1, name2):
    #return ratio(name1.lower(), name2.lower()) #je reste la fonction juste au dessus

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
    )
    ''')

    conn.commit()
    return conn

def get_game_studio_twitter(studio_name):
    search_query = f"{studio_name} twitter"
    results_df = search_brave(search_query)
    
    if results_df.empty:
        logging.info(f"Aucun résultat trouvé pour {studio_name}")
        return None
    
    for index, row in results_df.iterrows():
        if is_twitter_link(row['url']):
            title = row['title']
            url = row['url']
            displayed_name, handle = extract_twitter_names(title)
            
            # Si le handle n'est pas trouvé dans le titre, essayez de l'extraire de l'URL
            if not handle:
                handle = extract_twitter_handle(url)
            
            if not handle:
                continue
            
            similarity_displayed = name_similarity(studio_name, displayed_name)
            similarity_handle = name_similarity(studio_name.replace(" ", "").lower(), handle.lower())
            
            logging.info(f"Comparaison pour {studio_name}: displayed '{displayed_name}' (score: {similarity_displayed}), handle '@{handle}' (score: {similarity_handle})")
            
            # Vérifiez si le handle correspond exactement au nom du studio (insensible à la casse)
            if studio_name.lower() == handle.lower():
                return handle
            
            # Sinon, utilisez les scores de similarité
            if (similarity_displayed >= 0.9 and similarity_handle >= 0.5) or (similarity_displayed >= 0.5 and similarity_handle >= 0.9):
                return handle
    
    logging.info(f"Aucun handle Twitter trouvé avec un score de similarité suffisant pour {studio_name}")
    return None

def extract_twitter_names(title):
    # Essayez d'abord le format standard
    match = re.search(r'(.*?)\s*\(@(\w+)\)', title)
    if match:
        return match.group(1).strip(), match.group(2)
    
    # Si ça ne marche pas, essayez d'extraire directement de l'URL
    match = re.search(r'twitter\.com/(\w+)', title)
    if match:
        return title, match.group(1)
    
    # Si toujours rien, retournez le titre comme nom affiché et essayez d'extraire un nom d'utilisateur
    possible_handle = re.search(r'@(\w+)', title)
    if possible_handle:
        return title, possible_handle.group(1)
    
    return title, None

def format_tweet_message(game_data, tags, first_seen, x_handle=None):
    try:
        name = clean_text(game_data['name'])
        developers = game_data.get('developers', [])
        developer_handles = []
        if x_handle:
            # Si on a un handle de la page Steam, on s'assure qu'il a un @
            developer_handles = '@' + x_handle.lstrip('@')
        
        else:
            for dev in developers:
                # Sinon, on cherche avec get_game_studio_twitter
                handle = get_game_studio_twitter(dev)
                if handle:
                    developer_handles.append('@' + handle.lstrip('@'))
                else:
                    # Si pas de handle trouvé, on utilise le nom du dev sans @
                    developer_handles.append(dev)
        
        developers_str = ", ".join(developer_handles) if isinstance(developer_handles, list) else developer_handles
        
        description = clean_text(translate_to_english(game_data.get('short_description', '')))
        app_id = game_data['steam_appid']
        release_date = game_data.get('release_date', {}).get('date', 'TBA')
        
        date = datetime.fromtimestamp(first_seen, PARIS_TZ).strftime("%m-%d-%y")
        # Limiter le nombre de tags à 4
        limited_tags = tags[:4] if tags else []
        tags_str = ", ".join(clean_text(tag) for tag in limited_tags) if limited_tags else "No tags available"
        steam_link = f"https://store.steampowered.com/app/{app_id}"
        
        tweet = f"{date} ⏵ {name}\n🏷️ {tags_str}\n🧑‍💻 {developers_str}\n⏳ {release_date}\n📜 {description}\n{steam_link}"
        
        if len(tweet) > 280:
            available_space = 280 - len(f"{date} ⏵ {name}\n🏷️ {tags_str}\n🧑‍💻 {developers_str}\n⏳ {release_date}\n📜 ...\n{steam_link}")
            truncated_description = description[:available_space] + "..."
            tweet = f"{date} ⏵ {name}\n🏷️ {tags_str}\n🧑‍💻 {developers_str}\n⏳ {release_date}\n📜 {truncated_description}\n{steam_link}"
        
        return tweet
    except KeyError as e:
        print(f"Erreur lors du formatage du tweet: Clé manquante - {e}")
        return None
    except Exception as e:
        print(f"Erreur inattendue lors du formatage du tweet: {e}")
        return None

# def send_tweet(message):
#     client = get_twitter_client()
#     try:
#         response = client.create_tweet(text=message)
#         return response.data['id']
#     except Exception as e:
#         print(f"Erreur lors de la création du tweet: {e}")
#         return None
    
def send_tweet(message):
    client = get_twitter_client()
    max_retries = 3
    retry_delay = 60  # 60 seconds

    for attempt in range(max_retries):
        try:
            response = client.create_tweet(text=message)
            return response.data['id']
        except tweepy.TweepError as e:
            if e.response.status_code == 429:
                print(f"Rate limit reached. Waiting for {retry_delay} seconds before retrying...")
                sleep(retry_delay)
            else:
                print(f"Erreur lors de la création du tweet: {e}")
                return None
        
    print(f"Échec de la création du tweet après {max_retries} tentatives.")
    return None

# Ajoutez cette fonction pour insérer les données dans la nouvelle base de données
def insert_developer_social_media(game_id, x_handle):
    if x_handle and x_handle.strip():  # Vérifier si le handle n'est pas vide
        try:
            conn = sqlite3.connect('socialmedia_dev/socialmedia-developer.db')
            cursor = conn.cursor()
            
            # Vérifier si la table existe et la créer si nécessaire
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
            
            # Vérifier si une entrée existe déjà pour ce game_id et x_handle
            cursor.execute('''
                SELECT id FROM socialmedia_dev
                WHERE game_id = ? AND x_handle = ?
            ''', (game_id, x_handle))
            
            existing_entry = cursor.fetchone()
            
            if existing_entry is None:
                # Si aucune entrée n'existe, insérer une nouvelle ligne
                current_timestamp = int(time.time())
                cursor.execute('''
                    INSERT INTO socialmedia_dev 
                    (add_date, game_id, x_handle)
                    VALUES (?, ?, ?)
                ''', (current_timestamp, game_id, x_handle))
                
                logging.info(f"Nouvelle entrée insérée pour game_id: {game_id}, x_handle: {x_handle}, add_date: {current_timestamp}")
            else:
                logging.info(f"Entrée existante trouvée pour game_id: {game_id}, x_handle: {x_handle}. Aucune insertion effectuée.")
            
            conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Erreur SQLite lors de l'insertion des données sociales du développeur: {e}")
        finally:
            if conn:
                conn.close()
    else:
        logging.info(f"Pas d'insertion pour game_id: {game_id} car le handle Twitter est vide ou None")



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


def main():
    logging.info("Début de l'exécution de main()")
    try:
        csv_url = f"https://raw.githubusercontent.com/{os.getenv('PAT_GITHUB_USERNAME')}/{GITHUB_REPO}/main/{CSV_FILE_PATH}"
        logging.info(f"URL de la base de données : {csv_url}")
        
        last_timestamp = read_last_timestamp()
        logging.info(f"Dernier timestamp lu : {last_timestamp}")
        
        new_last_timestamp = last_timestamp
        total_games = 0
        published_games = 0
        priority_tweets = []
        non_priority_tweets = []
        ultimate_db_conn = create_ultimate_database()

        BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY")
        if not BRAVE_API_KEY:
            logging.error("Erreur : La clé API Brave n'est pas définie dans les variables d'environnement.")
            return None

        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as temp_csv:
            if download_csv(csv_url, temp_csv.name):
                logging.info(f"Base de données téléchargée avec succès : {temp_csv.name}")
                csv_data = read_csv(temp_csv.name)
                new_entries = check_new_entries(csv_data, last_timestamp)
                logging.info(f"Nombre de nouvelles entrées trouvées : {len(new_entries)}")
                
                
                for steam_game_id, first_seen in new_entries:
                    total_games += 1
                    logging.info(f"Traitement du jeu : Steam ID: {steam_game_id}, First Seen: {first_seen}")
                    
                    # Met à jour new_last_timestamp ici, pour chaque jeu traité
                    new_last_timestamp = max(new_last_timestamp, first_seen)

                    id_data = get_game_details(steam_game_id)


                    if id_data:
                    
                        scrap_steam_data = scrap_steam_page_info(steam_game_id)

                        if filter_game(id_data):
                            if scrap_steam_data and not scrap_steam_data['ai_generated']:
                                tags = scrap_steam_data['tags']
                                x_handle = scrap_steam_data['x_handle']
                                logging.info(f"Handle trouvé sur la page steam : {x_handle}")

                                # Si aucun handle n'est trouvé sur la page Steam, on utilise get_game_studio_twitter
                                if not x_handle:
                                    developer = id_data.get('developers', [''])[0]  # Prend le premier développeur
                                    x_handle = get_game_studio_twitter(developer) #peut etre erreur ici
                                    logging.info(f"Handle trouvé via Brave : {x_handle}")

                                # Stockage du handle dans la base de données si un handle valide a été trouvé
                                if x_handle and x_handle.startswith('@'):
                                    insert_developer_social_media(steam_game_id, x_handle)

                                logging.info(f"X_handle: {x_handle}")
                                message = format_tweet_message(id_data, tags, first_seen, x_handle)
                                if message:
                                    if is_priority_game(id_data):
                                        priority_tweets.append((message, id_data, first_seen))
                                    else:
                                        non_priority_tweets.append((message, id_data, first_seen))
                                else:
                                    logging.warning(f"Échec du formatage du tweet pour {id_data['name']}")
                            else:
                                global AI_GENERATED_GAMES
                                AI_GENERATED_GAMES += 1
                                logging.info(f"Le jeu avec Steam ID {steam_game_id} utilise du contenu généré par IA ou n'a pas pu être scrapé.")
                        else:
                            logging.info(f"Le jeu avec Steam ID {steam_game_id} ne répond pas aux critères de tweet ou les détails n'ont pas pu être récupérés.")
                    else:
                        logging.info(f"No id_data for {steam_game_id}.Impossible de récupérer les détails pour le jeu avec Steam ID {steam_game_id}")
                    
                    # Ajouter un délai aléatoire entre les requêtes
                    time.sleep(random.uniform(1.1, 1.4))
            else:
                logging.error("Échec du téléchargement du fichier steam_games.csv")
                return None
        
        os.unlink(temp_csv.name)
        logging.info("Fichier temporaire de la base de données supprimé")

        # Publier les tweets prioritaires
        for message, id_data, first_seen in priority_tweets:
            if published_games >= MAX_TWEETS_PER_DAY:
                break
            tweet_id = send_tweet(message)
            if tweet_id:
                logging.info(f"Tweet prioritaire publié pour {id_data['name']} (ID: {tweet_id})")
                new_last_timestamp = max(new_last_timestamp, first_seen)
                published_games += 1
            else:
                logging.warning(f"Échec de la publication du tweet prioritaire pour {id_data['name']}")

        # Publier les tweets non prioritaires si la limite n'est pas atteinte
        for message, id_data, first_seen in non_priority_tweets:
            if published_games >= MAX_TWEETS_PER_DAY:
                break
            tweet_id = send_tweet(message)
            if tweet_id:
                logging.info(f"Tweet non prioritaire publié pour {id_data['name']} (ID: {tweet_id})")
                new_last_timestamp = max(new_last_timestamp, first_seen)
                published_games += 1
            else:
                logging.warning(f"Échec de la publication du tweet non prioritaire pour {id_data['name']}")

        if new_last_timestamp > last_timestamp:
            write_last_timestamp(new_last_timestamp)
            logging.info(f"Timestamp mis à jour : {new_last_timestamp}")

        logging.info(f"\nRésumé : {published_games} jeux publiés sur {total_games} jeux traités au total.")
        logging.info(f"Tweets prioritaires : {len(priority_tweets)}")
        logging.info(f"Tweets non prioritaires : {len(non_priority_tweets)}")
        
        ultimate_db_conn.close()
        return total_games, published_games, new_last_timestamp, last_timestamp, priority_tweets, non_priority_tweets, csv_url
    
    except Exception as e:
        logging.exception(f"Une erreur inattendue s'est produite dans main(): {str(e)}")
        return None


if __name__ == "__main__":
    try:
        result = main()
        if result is not None:
            total_games, published_games, new_last_timestamp, last_timestamp, priority_tweets, non_priority_tweets, csv_url = result

            print(f"\nRésumé : {published_games} jeux publiés sur {total_games} jeux traités au total.")
            print(f"Tweets prioritaires : {len(priority_tweets)}")
            print(f"Tweets non prioritaires : {len(non_priority_tweets)}")

            # Appel de la fonction de journalisation
            log_execution(total_games, published_games)
        else:
            logging.error("La fonction main() a retourné None")
            print("Une erreur s'est produite lors de l'exécution. Veuillez consulter le fichier de log pour plus de détails.")

    except Exception as e:
        logging.exception(f"Une erreur s'est produite lors de l'exécution : {str(e)}")
        print(f"Une erreur s'est produite. Veuillez consulter le fichier de log pour plus de détails.")