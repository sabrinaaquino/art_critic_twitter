import json
import os
from config import Config

class State:
    def __init__(self):
        self.processed_tweets = set()
        self.allowed_authors = {}  # conversation_id (str) -> author_id (str)
        self.filename = Config.STATE_FILENAME

    def load(self):
        try:
            with open(self.filename, 'r') as f:
                data = json.load(f)
                # Backward compatibility: prior format was a list of tweet IDs
                if isinstance(data, list):
                    self.processed_tweets = {str(tweet_id) for tweet_id in data}
                    self.allowed_authors = {}
                elif isinstance(data, dict):
                    tweets = data.get('processed_tweets', [])
                    self.processed_tweets = {str(tweet_id) for tweet_id in tweets}
                    self.allowed_authors = {
                        str(conv_id): str(author_id)
                        for conv_id, author_id in data.get('allowed_authors', {}).items()
                    }
                else:
                    # Unknown format; reset safely
                    self.processed_tweets = set()
                    self.allowed_authors = {}
        except FileNotFoundError:
            self.processed_tweets = set()
            self.allowed_authors = {}

    def save(self):
        with open(self.filename, 'w') as f:
            json.dump({
                'processed_tweets': list(self.processed_tweets),
                'allowed_authors': self.allowed_authors
            }, f)

    def is_processed(self, tweet_id):
        return str(tweet_id) in self.processed_tweets
    
    def add_tweet(self, tweet_id):
        self.processed_tweets.add(str(tweet_id))

    def get_allowed_author(self, conversation_id: str):
        return self.allowed_authors.get(str(conversation_id))

    def set_allowed_author(self, conversation_id: str, author_id: str):
        self.allowed_authors[str(conversation_id)] = str(author_id) 