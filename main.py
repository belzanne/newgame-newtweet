##test priorisation jeux sans éditeurs 

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
    content_descriptors = game_data.get('content_descriptors', {}).get('ids', [])
    if 3 in content_descriptors:
        return False
    
    # Vérifier si l'anglais est supporté
    supported_languages = game_data.get('supported_languages', '').lower()
    if 'english' not in supported_languages:
        return False
    
    # Vérifier si le jeu est payant
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

def get_game_tags_and_check_ai(app_id):
    try:
        url = f"https://store.steampowered.com/app/{app_id}/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Vérifier la présence de contenu généré par IA
            ai_disclosure = soup.find(string=re.compile("AI GENERATED CONTENT DISCLOSURE", re.IGNORECASE))
            if ai_disclosure:
                print(f"Contenu AI détecté pour le jeu {app_id}")
                return None, None  # Le jeu utilise du contenu généré par IA
            
            # Récupérer les tags
            tag_elements = soup.find_all('a', class_='app_tag')
            tags = [tag.text.strip() for tag in tag_elements]
            return tags[:4], 'scraped'  # Retourne seulement les 4 premiers tags
    except Exception as e:
        print(f"Erreur lors du scraping pour le jeu {app_id}: {e}")
    
    return None, None

def translate_to_english(text):
    try:
        # Détection de la langue
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
    # Décode les entités HTML
    decoded_text = html.unescape(text)
    # Supprime les sauts de ligne et les espaces multiples
    cleaned_text = ' '.join(decoded_text.split())
    return cleaned_text

def is_priority_game(game_data):
    publisher = game_data.get('publishers', [])
    developer = game_data.get('developers', [])
    return not publisher or (publisher == developer)

def search_duckduckgo(query, max_results=5):
    results = DDGS().text(
        keywords=query,
        region='wt-wt',
        safesearch='off',
        timelimit='7d',
        max_results=max_results
    )
    return pd.DataFrame(list(results))

def is_twitter_link(url):
    return 'twitter.com' in url.lower()

def is_game_related(text):
    game_keywords = {
        'en': ['game', 'video game', 'developer', 'studio', 'gaming'],
        'fr': ['jeu', 'jeu vidéo', 'développeur', 'studio', 'gaming'],
        'es': ['juego', 'videojuego', 'desarrollador', 'estudio', 'gaming'],
        'de': ['spiel', 'videospiel', 'entwickler', 'studio', 'gaming'],
        'it': ['gioco', 'videogioco', 'sviluppatore', 'studio', 'gaming'],
        'ja': ['ゲーム', 'ビデオゲーム', '開発者', 'スタジオ', 'ゲーミング'],
    }
    
    try:
        lang = detect(text)
        if lang not in game_keywords:
            text = translator.translate(text, dest='en')
            lang = 'en'
        return any(keyword.lower() in text.lower() for keyword in game_keywords[lang])
    except:
        return False

def extract_twitter_handle(url):
    match = re.search(r'twitter\.com/(\w+)', url)
    if match:
        return '@' + match.group(1)
    return None

def name_similarity(name1, name2):
    return ratio(name1.lower(), name2.lower())

def get_game_studio_twitter(studio_name):
    search_query = f"{studio_name} twitter"
    results_df = search_duckduckgo(search_query)
    
    for index, row in results_df.iterrows():
        if is_twitter_link(row['href']):
            handle = extract_twitter_handle(row['href'])
            if handle and is_game_related(row['body']):
                # Vérifier la similarité du nom
                similarity = name_similarity(studio_name, handle[1:])  # Ignorer le '@'
                if similarity >= 0.9:
                    return handle
    
    return studio_name  # Retourne le nom du studio si aucun compte Twitter pertinent n'est trouvé

def format_tweet_message(game_data, tags, first_seen, tags_source):
    try:
        name = clean_text(game_data['name'])
        developers = game_data.get('developers', [])
        developer_handles = []
        for dev in developers:
            handle = get_game_studio_twitter(dev)
            developer_handles.append(handle)
        developers_str = ", ".join(developer_handles)
        
        description = clean_text(translate_to_english(game_data.get('short_description', '')))
        app_id = game_data['steam_appid']
        release_date = game_data.get('release_date', {}).get('date', 'TBA')
        
        # Formater la date
        date = datetime.fromtimestamp(first_seen, PARIS_TZ).strftime("%m-%d-%y")
        
        # Formater les tags
        tags_str = ", ".join(clean_text(tag) for tag in tags) if tags else "No tags available"
        
        # Construire le lien Steam
        steam_link = f"https://store.steampowered.com/app/{app_id}"
        
        # Construire le tweet avec le nouveau format
        tweet = f"{date} ⏵ {name}\n🏷️ {tags_str}\n🧑‍💻 {developers_str}\n⏳ {release_date}\n📜 {description}\n{steam_link}"
        
        # Vérifier et ajuster la longueur du tweet si nécessaire
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

def main():
    db_url = f"https://raw.githubusercontent.com/{os.getenv('GITHUB_USERNAME')}/{GITHUB_REPO}/main/{DB_FILE_PATH}"
    last_timestamp = read_last_timestamp()
    new_last_timestamp = last_timestamp

    total_games = 0
    published_games = 0
    priority_tweets = []
    non_priority_tweets = []

    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as temp_db:
        if download_db(db_url, temp_db.name):
            conn = connect_to_db(temp_db.name)
            new_entries = check_new_entries(conn, last_timestamp)
            
            for steam_game_id, first_seen in new_entries:
                total_games += 1
                print(f"Nouveau jeu trouvé : Steam ID: {steam_game_id}, First Seen: {first_seen}")
                game_data = get_game_details(steam_game_id)
                if game_data and filter_game(game_data):
                    tags, tags_source = get_game_tags_and_check_ai(steam_game_id)
                    if tags is None:
                        print(f"Le jeu avec Steam ID {steam_game_id} utilise du contenu généré par IA ou n'a pas pu être scrapé.")
                        continue
                    message = format_tweet_message(game_data, tags, first_seen, tags_source)
                    if message:
                        if is_priority_game(game_data):
                            priority_tweets.append((message, game_data, first_seen))
                        else:
                            non_priority_tweets.append((message, game_data, first_seen))
                    else:
                        print(f"Échec du formatage du tweet pour {game_data['name']}")
                else:
                    print(f"Le jeu avec Steam ID {steam_game_id} ne répond pas aux critères de tweet ou les détails n'ont pas pu être récupérés.")
            
            conn.close()
        else:
            print("Échec du téléchargement de la base de données")
    
    os.unlink(temp_db.name)  # Supprime le fichier temporaire

    # Publier les tweets prioritaires
    for message, game_data, first_seen in priority_tweets:
        if published_games >= MAX_TWEETS_PER_DAY:
            break
        tweet_id = send_tweet(message)
        if tweet_id:
            print(f"Tweet prioritaire publié pour {game_data['name']} (ID: {tweet_id})")
            new_last_timestamp = max(new_last_timestamp, first_seen)
            published_games += 1
        else:
            print(f"Échec de la publication du tweet prioritaire pour {game_data['name']}")

    # Publier les tweets non prioritaires si la limite n'est pas atteinte
    for message, game_data, first_seen in non_priority_tweets:
        if published_games >= MAX_TWEETS_PER_DAY:
            break
        tweet_id = send_tweet(message)
        if tweet_id:
            print(f"Tweet non prioritaire publié pour {game_data['name']} (ID: {tweet_id})")
            new_last_timestamp = max(new_last_timestamp, first_seen)
            published_games += 1
        else:
            print(f"Échec de la publication du tweet non prioritaire pour {game_data['name']}")

    if new_last_timestamp > last_timestamp:
        write_last_timestamp(new_last_timestamp)
        print(f"Timestamp mis à jour : {new_last_timestamp}")

    print(f"\nRésumé : {published_games} jeux publiés sur {total_games} jeux traités au total.")
    print(f"Tweets prioritaires : {len(priority_tweets)}")
    print(f"Tweets non prioritaires : {len(non_priority_tweets)}")

if __name__ == "__main__":
    main()

#notepourplustard : les token sont dans .env -> comment gérer côté github
