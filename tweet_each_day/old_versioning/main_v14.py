#version qui cherche les comptes twitter avec Brave Search API
#avantage : trouve plus facilement les comptes twitter
#inconvénient : ne ramène pas le body -> pas possible de vérifier lien avec jeux vidéo -> possibilité de faux positifs

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
from duckduckgo_search import DDGS
import re
from Levenshtein import ratio
import logging
import time
from requests.exceptions import RequestException
import sqlite3

# Configuration du logging
logging.basicConfig(filename='log_file.log', level=logging.INFO,
                    format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

def log_execution(total_games, published_games):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"Exécution du {timestamp}: {published_games} tweets envoyés sur {total_games} jeux traités."
    logging.info(log_message)
    logging.info(f"PAT_GITHUB_USERNAME: {os.getenv('PAT_GITHUB_USERNAME')}")
    logging.info(f"GITHUB_REPO: {GITHUB_REPO}")
    logging.info(f"DB_FILE_PATH: {DB_FILE_PATH}")
    logging.info(f"URL complète : {db_url}")
    logging.info("Utilisation de l'API Brave Search")
    print(log_message)

# Charger les variables d'environnement
load_dotenv()

# Configuration
GITHUB_REPO = 'steampage-creation-date'
DB_FILE_PATH = 'steam_games.db'
TIMESTAMP_FILE = 'timestamp_last_tweet.txt'
PARIS_TZ = pytz.timezone('Europe/Paris')
MAX_TWEETS_PER_DAY = 50

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

def download_db(url, local_path):
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    print(f"Échec du téléchargement de la base de données. Code de statut: {response.status_code}")
    return False

def connect_to_db(db_path):
    return sqlite3.connect(db_path)

def check_new_entries(conn, last_timestamp):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT steam_game_id, first_seen
        FROM games 
        WHERE first_seen > ?
        ORDER BY first_seen ASC
    """, (last_timestamp,))
    return cursor.fetchall()

def get_game_details(steam_game_id):
    url = f"https://store.steampowered.com/api/appdetails?appids={steam_game_id}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data[str(steam_game_id)]['success']:
            return data[str(steam_game_id)]['data']
    return None

def filter_game(game_data):
    if game_data['type'] != 'game' or game_data.get('dlc', False):
        return False
    
    content_descriptors = game_data.get('content_descriptors', {})
    if isinstance(content_descriptors, dict):
        descriptor_ids = content_descriptors.get('ids', [])
    elif isinstance(content_descriptors, list):
        descriptor_ids = content_descriptors
    else:
        descriptor_ids = []
    
    if 3 in descriptor_ids:
        return False
    
    supported_languages = game_data.get('supported_languages', '').lower()
    if 'english' not in supported_languages:
        return False
    
    if game_data.get('is_free', True):
        return False
    
    return True

def get_twitter_client():
    client = tweepy.Client(
        consumer_key=os.getenv('TWITTER_CONSUMER_KEY'),
        consumer_secret=os.getenv('TWITTER_CONSUMER_SECRET'),
        access_token=os.getenv('TWITTER_ACCESS_TOKEN'),
        access_token_secret=os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
    )
    return client

def get_steam_page_info(app_id):
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
        
        # Récupérer les tags
        tag_elements = soup.find_all('a', class_='app_tag')
        tags = [tag.text.strip() for tag in tag_elements][:4]  # Limiter à 4 tags
        
        # Récupérer le lien Twitter s'il existe
        twitter_link = soup.find('a', class_="ttip", attrs={'data-tooltip-text': lambda x: x and 'x.com/' in x})
        twitter_handle = None
        if twitter_link:
            twitter_url = twitter_link['data-tooltip-text']
            twitter_handle = '@' + twitter_url.split('/')[-1]
        
        return {
            'ai_generated': bool(ai_disclosure),
            'tags': tags,
            'twitter_handle': twitter_handle
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

def get_game_studio_twitter(studio_name):
    search_query = f"{studio_name} twitter"
    results_df = search_brave(search_query)
    
    if results_df.empty:
        print(f"Aucun résultat trouvé pour {studio_name}")
        return studio_name
    
    for index, row in results_df.iterrows():
        if is_twitter_link(row['url']):
            title = row['title']
            displayed_name, handle = extract_twitter_names(title)
            
            if displayed_name is None or handle is None:
                continue
            
            similarity_displayed = name_similarity(studio_name, displayed_name)
            similarity_handle = name_similarity(studio_name.replace(" ", "").lower(), handle.lower())
            
            logging.info(f"Comparaison pour {studio_name}: displayed '{displayed_name}' (score: {similarity_displayed}), handle '@{handle}' (score: {similarity_handle})")
            
            # Être plus strict : exiger une similarité élevée pour le nom affiché
            if similarity_displayed >= 0.9 and similarity_handle >= 0.8:
                return f"@{handle}"
    
    logging.info(f"Aucun handle Twitter trouvé avec un score de similarité suffisant pour {studio_name}")
    return studio_name

def extract_twitter_names(title):
    match = re.search(r'(.*?)\s*\(@(\w+)\)', title)
    if match:
        return match.group(1).strip(), match.group(2)
    return title, title

def format_tweet_message(game_data, tags, first_seen, twitter_handle=None):
    try:
        name = clean_text(game_data['name'])
        developers = game_data.get('developers', [])
        developer_handles = []
        
        for dev in developers:
            if twitter_handle:
                # Si on a un handle de la page Steam, on l'utilise
                developer_handles.append(twitter_handle)
            else:
                # Sinon, on cherche avec get_game_studio_twitter
                handle = get_game_studio_twitter(dev)
                if handle and handle.startswith('@'):
                    developer_handles.append(handle)
                else:
                    # Si pas de handle trouvé, on utilise le nom du dev sans @
                    developer_handles.append(dev)
        
        developers_str = ", ".join(developer_handles)
        
        description = clean_text(translate_to_english(game_data.get('short_description', '')))
        app_id = game_data['steam_appid']
        release_date = game_data.get('release_date', {}).get('date', 'TBA')
        
        date = datetime.fromtimestamp(first_seen, PARIS_TZ).strftime("%m-%d-%y")
        tags_str = ", ".join(clean_text(tag) for tag in tags) if tags else "No tags available"
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

def send_tweet(message):
    client = get_twitter_client()
    try:
        response = client.create_tweet(text=message)
        return response.data['id']
    except Exception as e:
        print(f"Erreur lors de la création du tweet: {e}")
        return None

# Ajoutez cette fonction pour insérer les données dans la nouvelle base de données
def insert_developer_social_media(game_id, twitter_handle):
    try:
        conn = sqlite3.connect('socialmedia-developer.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO developer_social_media (game_id, twitter_handle)
            VALUES (?, ?)
        ''', (game_id, twitter_handle))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Erreur SQLite lors de l'insertion des données sociales du développeur: {e}")
    finally:
        if conn:
            conn.close() 
            
def main():
    logging.info("Début de l'exécution de main()")
    try:
        db_url = f"https://raw.githubusercontent.com/{os.getenv('PAT_GITHUB_USERNAME')}/{GITHUB_REPO}/main/{DB_FILE_PATH}"
        logging.info(f"URL de la base de données : {db_url}")
        
        last_timestamp = read_last_timestamp()
        logging.info(f"Dernier timestamp lu : {last_timestamp}")
        
        new_last_timestamp = last_timestamp
        total_games = 0
        published_games = 0
        priority_tweets = []
        non_priority_tweets = []

        BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY")
        if not BRAVE_API_KEY:
            logging.error("Erreur : La clé API Brave n'est pas définie dans les variables d'environnement.")
            return None

        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as temp_db:
            if download_db(db_url, temp_db.name):
                logging.info(f"Base de données téléchargée avec succès : {temp_db.name}")
                conn = connect_to_db(temp_db.name)
                new_entries = check_new_entries(conn, last_timestamp)
                logging.info(f"Nombre de nouvelles entrées trouvées : {len(new_entries)}")
                
                for steam_game_id, first_seen in new_entries:
                    total_games += 1
                    logging.info(f"Traitement du jeu : Steam ID: {steam_game_id}, First Seen: {first_seen}")
                    game_data = get_game_details(steam_game_id)
                    if game_data and filter_game(game_data):
                        steam_page_info = get_steam_page_info(steam_game_id)
                        if steam_page_info and not steam_page_info['ai_generated']:
                            tags = steam_page_info['tags']
                            twitter_handle = steam_page_info['twitter_handle']
                            logging.info(f"Handle trouvé sur la page steam : {twitter_handle}")

                            # Si aucun handle n'est trouvé sur la page Steam, on utilise get_game_studio_twitter
                            if not twitter_handle:
                                developer = game_data.get('developers', [''])[0]  # Prend le premier développeur
                                twitter_handle = get_game_studio_twitter(developer)
                                logging.info(f"Handle trouvé via Brave : {twitter_handle}")

                            # Stockage du handle dans la base de données si un handle valide a été trouvé
                            if twitter_handle and twitter_handle.startswith('@'):
                                insert_developer_social_media(steam_game_id, twitter_handle)

                            logging.info(f"X_handle: {twitter_handle}")
                            message = format_tweet_message(game_data, tags, first_seen, twitter_handle)
                            if message:
                                if is_priority_game(game_data):
                                    priority_tweets.append((message, game_data, first_seen))
                                else:
                                    non_priority_tweets.append((message, game_data, first_seen))
                            else:
                                logging.warning(f"Échec du formatage du tweet pour {game_data['name']}")
                        else:
                            logging.info(f"Le jeu avec Steam ID {steam_game_id} utilise du contenu généré par IA ou n'a pas pu être scrapé.")
                    else:
                        logging.info(f"Le jeu avec Steam ID {steam_game_id} ne répond pas aux critères de tweet ou les détails n'ont pas pu être récupérés.")
                conn.close()
            else:
                logging.error("Échec du téléchargement de la base de données")
                return None
        
        os.unlink(temp_db.name)
        logging.info("Fichier temporaire de la base de données supprimé")

        # Publier les tweets prioritaires
        for message, game_data, first_seen in priority_tweets:
            if published_games >= MAX_TWEETS_PER_DAY:
                break
            tweet_id = send_tweet(message)
            if tweet_id:
                logging.info(f"Tweet prioritaire publié pour {game_data['name']} (ID: {tweet_id})")
                new_last_timestamp = max(new_last_timestamp, first_seen)
                published_games += 1
            else:
                logging.warning(f"Échec de la publication du tweet prioritaire pour {game_data['name']}")

        # Publier les tweets non prioritaires si la limite n'est pas atteinte
        for message, game_data, first_seen in non_priority_tweets:
            if published_games >= MAX_TWEETS_PER_DAY:
                break
            tweet_id = send_tweet(message)
            if tweet_id:
                logging.info(f"Tweet non prioritaire publié pour {game_data['name']} (ID: {tweet_id})")
                new_last_timestamp = max(new_last_timestamp, first_seen)
                published_games += 1
            else:
                logging.warning(f"Échec de la publication du tweet non prioritaire pour {game_data['name']}")

        if new_last_timestamp > last_timestamp:
            write_last_timestamp(new_last_timestamp)
            logging.info(f"Timestamp mis à jour : {new_last_timestamp}")

        logging.info(f"\nRésumé : {published_games} jeux publiés sur {total_games} jeux traités au total.")
        logging.info(f"Tweets prioritaires : {len(priority_tweets)}")
        logging.info(f"Tweets non prioritaires : {len(non_priority_tweets)}")
        
        return total_games, published_games, new_last_timestamp, last_timestamp, priority_tweets, non_priority_tweets, db_url
    
    except Exception as e:
        logging.exception(f"Une erreur inattendue s'est produite dans main(): {str(e)}")
        return None


if __name__ == "__main__":
    try:
        result = main()
        if result is not None:
            total_games, published_games, new_last_timestamp, last_timestamp, priority_tweets, non_priority_tweets, db_url = result
            
            if new_last_timestamp > last_timestamp:
                write_last_timestamp(new_last_timestamp)
                print(f"Timestamp mis à jour : {new_last_timestamp}")

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