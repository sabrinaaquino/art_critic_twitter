import logging
import tweepy
from config import Config

logger = logging.getLogger(__name__)


def get_mentions(client, bot_user_id, max_results=None, start_time=None):
    """Fetches recent mentions for the bot. Optionally filter with start_time (RFC3339)."""
    if max_results is None:
        max_results = Config.MAX_MENTIONS_PER_CHECK
        
    logger.info(f"Requesting up to {max_results} mentions for user {bot_user_id}...")
    
    try:
        kwargs = {
            'id': bot_user_id,
            'max_results': max_results,
            'tweet_fields': ['created_at', 'author_id', 'attachments', 'public_metrics', 'conversation_id', 'referenced_tweets', 'in_reply_to_user_id', 'entities'],
            'expansions': ['attachments.media_keys', 'author_id', 'in_reply_to_user_id', 'referenced_tweets.id'],
            'media_fields': ['type', 'url', 'preview_image_url'],
            'user_fields': ['protected', 'verified', 'username']
        }
        if start_time:
            kwargs['start_time'] = start_time
        return client.get_users_mentions(**kwargs)
    except tweepy.errors.TooManyRequests as e:
        # Let the caller handle rate limits
        raise
    except tweepy.errors.TweepyException as e:
        logger.error(f"Error fetching mentions: {e}")
        raise


def reply_to_tweet(client, tweet_id, text):
    """Posts a reply to a specific tweet, using X Premium long-form if available."""
    logger.info(f"Attempting to reply to tweet {tweet_id}...")

    # Determine character limit based on X Premium status
    if Config.X_PREMIUM_ENABLED:
        char_limit = Config.X_PREMIUM_CHAR_LIMIT
        logger.info(f"Using X Premium character limit: {char_limit}")
    else:
        char_limit = Config.STANDARD_CHAR_LIMIT
        logger.info(f"Using standard character limit: {char_limit}")

    if len(text) <= char_limit:
        # Single tweet - post normally (works for both standard and Premium)
        try:
            response = client.create_tweet(
                text=text,
                in_reply_to_tweet_id=tweet_id
            )
            logger.info(f"Successfully replied to tweet {tweet_id}. Response ID: {response.data['id']}")
            return response
        except tweepy.errors.Forbidden as e:
            logger.error(f"403 Forbidden error when replying to tweet {tweet_id}. This can happen if the tweet is from a protected account. Error: {e}")
            return None
        except tweepy.errors.TooManyRequests as e:
            # Let the caller handle rate limits
            raise
        except tweepy.errors.TweepyException as e:
            logger.error(f"An unexpected Tweepy error occurred when replying to tweet {tweet_id}: {e}")
            raise
    else:
        # Text exceeds limit - handle based on Premium status
        if Config.X_PREMIUM_ENABLED:
            logger.warning(f"Response is {len(text)} characters, exceeds X Premium limit of {char_limit}. Truncating.")
        else:
            logger.warning(f"Response is {len(text)} characters, exceeds standard limit of {char_limit}. Consider upgrading to X Premium for longer posts.")
        
        # Smart truncation for any limit exceeded
        truncated = text[:char_limit-10]  # Leave room for "..."
        
        # Find last sentence ending
        for punct in ['. ', '! ', '? ']:
            last_punct = truncated.rfind(punct)
            if last_punct > char_limit * 0.7:  # Only if we have substantial content
                truncated = text[:last_punct + 1]
                break
        else:
            # No good sentence break, add ellipsis
            truncated = text[:char_limit-3] + "..."
        
        try:
            response = client.create_tweet(
                text=truncated,
                in_reply_to_tweet_id=tweet_id
            )
            logger.info(f"Successfully posted truncated reply to tweet {tweet_id}. Response ID: {response.data['id']}")
            return response
        except tweepy.errors.Forbidden as e:
            logger.error(f"403 Forbidden error when replying to tweet {tweet_id}. Error: {e}")
            return None
        except tweepy.errors.TooManyRequests as e:
            # Let the caller handle rate limits
            raise
        except tweepy.errors.TweepyException as e:
            logger.error(f"An unexpected Tweepy error occurred when replying to tweet {tweet_id}: {e}")
            raise

def get_tweet_by_id(client, tweet_id):
    """Fetches a single tweet by its ID with full context including quote tweets and media."""
    logger.info(f"Fetching tweet {tweet_id} for context...")
    try:
        return client.get_tweet(
            tweet_id,
            tweet_fields=['created_at', 'author_id', 'text', 'attachments', 'referenced_tweets', 'conversation_id', 'in_reply_to_user_id', 'entities'],
            expansions=['author_id', 'attachments.media_keys', 'referenced_tweets.id', 'in_reply_to_user_id'],
            media_fields=['type', 'url', 'preview_image_url'],
            user_fields=['username', 'name']
        )
    except tweepy.errors.TooManyRequests as e:
        # Let the caller handle rate limits
        raise
    except tweepy.errors.TweepyException as e:
        logger.error(f"Error fetching tweet {tweet_id}: {e}")
        raise