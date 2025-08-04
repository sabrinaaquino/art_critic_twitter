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
            tweet_fields=['created_at', 'author_id', 'attachments', 'public_metrics', 'conversation_id', 'referenced_tweets', 'in_reply_to_user_id'],
            expansions=['attachments.media_keys', 'author_id', 'in_reply_to_user_id', 'referenced_tweets.id'],
            media_fields=['type', 'url', 'preview_image_url'],
            user_fields=['protected', 'verified', 'username']
        )
    except tweepy.errors.TweepyException as e:
        logger.error(f"Error fetching mentions: {e}")
        return None


def reply_to_tweet(client, tweet_id, text):
    """Posts a reply to a specific tweet, creating a thread if the text is too long."""
    logger.info(f"Attempting to reply to tweet {tweet_id}...")

    char_limit = 280

    if len(text) <= char_limit:
        # Single tweet - post normally
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
        except tweepy.errors.TweepyException as e:
            logger.error(f"An unexpected Tweepy error occurred when replying to tweet {tweet_id}: {e}")
            return None
    else:
        # Create a thread for longer responses
        logger.info(f"Response is {len(text)} characters. Creating thread for tweet {tweet_id}.")
        
        def create_chunks(text, limit):
            words = text.split()
            if not words:
                return []
            
            chunks = []
            current_chunk = words[0]
            
            for word in words[1:]:
                if len(current_chunk) + len(word) + 1 <= limit:
                    current_chunk += " " + word
                else:
                    chunks.append(current_chunk)
                    current_chunk = word
                    
            chunks.append(current_chunk)
            return chunks

        text_chunks = create_chunks(text, char_limit)
        if not text_chunks:
            logger.warning(f"Reply text for tweet {tweet_id} is empty after chunking.")
            return None

        last_tweet_id_in_thread = tweet_id
        last_response = None

        for i, chunk in enumerate(text_chunks):
            try:
                response = client.create_tweet(
                    text=chunk,
                    in_reply_to_tweet_id=last_tweet_id_in_thread
                )
                logger.info(f"Successfully posted chunk {i+1}/{len(text_chunks)} for tweet {tweet_id}. Response ID: {response.data['id']}")
                last_tweet_id_in_thread = response.data['id']
                last_response = response
            except tweepy.errors.Forbidden as e:
                logger.error(f"403 Forbidden error when posting chunk {i+1} for tweet {tweet_id}. Error: {e}")
                return None
            except tweepy.errors.TweepyException as e:
                logger.error(f"An unexpected Tweepy error occurred when posting chunk {i+1} for tweet {tweet_id}: {e}")
                return None
                
        return last_response

def get_tweet_by_id(client, tweet_id):
    """Fetches a single tweet by its ID with full context including quote tweets and media."""
    logger.info(f"Fetching tweet {tweet_id} for context...")
    try:
        return client.get_tweet(
            tweet_id,
            tweet_fields=['created_at', 'author_id', 'text', 'attachments', 'referenced_tweets'],
            expansions=['author_id', 'attachments.media_keys', 'referenced_tweets.id'],
            media_fields=['type', 'url', 'preview_image_url'],
            user_fields=['username', 'name']
        )
    except tweepy.errors.TweepyException as e:
        logger.error(f"Error fetching tweet {tweet_id}: {e}")
        return None