import json
import os
from config import Config

class State:
    def __init__(self):
        self.processed_tweets = set()
        self.filename = Config.STATE_FILENAME

    def load(self):
        try:
            with open(self.filename, 'r') as f:
                tweets = json.load(f)
                self.processed_tweets = set(tweets)
        except FileNotFoundError:
            self.processed_tweets = set()

    def save(self):
        with open(self.filename, 'w') as f:
            json.dump(list(self.processed_tweets), f)

    def is_processed(self, tweet_id):
        return str(tweet_id) in self.processed_tweets
    
    def add_tweet(self, tweet_id):
        self.processed_tweets.add(str(tweet_id)) 