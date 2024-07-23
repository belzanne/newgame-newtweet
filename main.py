import tweepy
import creds 
import os
from steam_web_api import Steam

# You can authenticate as your app with just your bearer token
#client = tweepy.Client(bearer_token=creds.bearer_token)

# You can provide the consumer key and secret with the access token and access
# token secret to authenticate as a user
#client = tweepy.Client(
    #consumer_key=creds.consumer_key, consumer_secret=creds.consumer_secret,
    #access_token=creds.access_token, access_token_secret=creds.access_token_secret)
    
client = tweepy.Client(
    consumer_key=creds.consumer_key, consumer_secret=creds.consumer_secret,
    access_token=creds.access_token, access_token_secret=creds.access_token_secret
)

# Create Tweet

response = client.create_tweet(
    text="This Tweet is a test!"
)
print(f"https://twitter.com/user/status/{response.data['id']}")







#notepourplustard : mettre token dans .env pour la partie github, là je mets dans creds pour tester en local
