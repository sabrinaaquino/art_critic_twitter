import logging
import tweepy
from config import Config

logger = logging.getLogger(__name__)

def get_twitter_client():
    """Initializes and returns a Tweepy client."""
    logger.debug("Initializing Twitter client...")
    Config.validate()
    
    try:
        client = tweepy.Client(
            bearer_token=Config.TWITTER_BEARER_TOKEN,
            consumer_key=Config.TWITTER_API_KEY,
            consumer_secret=Config.TWITTER_API_SECRET,
            access_token=Config.TWITTER_ACCESS_TOKEN,
            access_token_secret=Config.TWITTER_ACCESS_TOKEN_SECRET,
            wait_on_rate_limit=False  # Handle rate limits manually for better control
        )
        logger.info("Twitter client initialized successfully.")
        return client
    except Exception as e:
        logger.critical(f"Failed to initialize Twitter client: {e}")
        raise 