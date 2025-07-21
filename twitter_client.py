import logging
import tweepy
from config import Config

logger = logging.getLogger(__name__)


def get_mentions(client, bot_user_id, max_results=None):
    """Fetches recent mentions for the bot."""
    if max_results is None:
        max_results = Config.MAX_MENTIONS_PER_CHECK
        
    logger.info(f"Requesting up to {max_results} mentions for user {bot_user_id}...")
    
    try:
        return client.get_users_mentions(
            id=bot_user_id,
            max_results=max_results,
            tweet_fields=['created_at', 'author_id', 'attachments', 'public_metrics', 'conversation_id'],
            expansions=['attachments.media_keys', 'author_id', 'in_reply_to_user_id'],
            media_fields=['type', 'url', 'preview_image_url'],
            user_fields=['protected', 'verified', 'username']
        )
    except tweepy.errors.TweepyException as e:
        logger.error(f"Error fetching mentions: {e}")
        return None


def reply_to_tweet(client, tweet_id, text):
    """Posts a reply to a specific tweet."""
    logger.info(f"Attempting to reply to tweet {tweet_id}...")
    try:
        response = client.create_tweet(
            text=text,
            in_reply_to_tweet_id=tweet_id
        )
        logger.info(f"Successfully replied to tweet {tweet_id}. Response ID: {response.data['id']}")
        return response
    except tweepy.errors.Forbidden as e:
        logger.error(f"403 Forbidden error when replying to tweet {tweet_id}. This can happen if the tweet is from a protected account or if the reply is too long. Error: {e}")
        return None
    except tweepy.errors.TweepyException as e:
        logger.error(f"An unexpected Tweepy error occurred when replying to tweet {tweet_id}: {e}")
        return None 