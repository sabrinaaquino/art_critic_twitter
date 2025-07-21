import logging
import time
from config import Config
from state import State
from clients import get_twitter_client
from twitter_client import get_mentions, reply_to_tweet
from venice_api import send_image_to_venice
from image_processor import process_tweet_media

logger = logging.getLogger(__name__)


class ArtCriticBot:
    """Core bot class."""

    def __init__(self):
        """Initializes the bot."""
        logger.info("Initializing bot...")
        self.state = State()
        self.client = get_twitter_client()
        self.bot_user_id = self._get_bot_user_id()
        self.last_check_time = 0
        self.hourly_reply_count = 0
        self.hourly_check_time = time.time()
        logger.info("Bot initialized successfully.")

    def _get_bot_user_id(self):
        """Fetches bot's Twitter user ID."""
        try:
            logger.info("Fetching bot user ID...")
            me_response = self.client.get_me()
            if not me_response or not me_response.data:
                raise Exception("Could not retrieve bot user information from Twitter.")
            bot_id = me_response.data.id
            logger.info(f"Bot User ID is {bot_id}")
            return bot_id
        except Exception as e:
            logger.critical(f"Fatal: Failed to get bot user ID. Check credentials and network. Error: {e}")
            exit(1)

    def _can_check_for_mentions(self):
        """Pauses to respect rate limits."""
        elapsed_time = time.time() - self.last_check_time
        if elapsed_time < Config.MIN_CHECK_INTERVAL:
            wait_time = Config.MIN_CHECK_INTERVAL - elapsed_time
            logger.info(f"Rate limit check: waiting {wait_time:.1f}s before next check.")
            time.sleep(wait_time)
        return True

    def _reset_hourly_rate_limit(self):
        """Resets the hourly reply counter."""
        if time.time() - self.hourly_check_time >= 3600:
            logger.info(f"Resetting hourly reply count from {self.hourly_reply_count} to 0.")
            self.hourly_reply_count = 0
            self.hourly_check_time = time.time()

    def _handle_image_tweet(self, tweet, image_bytes):
        """Handles a tweet with an image."""
        logger.info(f"Processing tweet {tweet.id} with image...")
        critique = send_image_to_venice(image_bytes, tweet.text)
        if critique:
            reply_to_tweet(self.client, tweet.id, critique)
            self.hourly_reply_count += 1
        else:
            logger.error(f"Failed to get critique for tweet {tweet.id}.")

    def _handle_text_tweet(self, tweet):
        """Handles a tweet without an image."""
        logger.info(f"Processing tweet {tweet.id} without image...")
        reply_to_tweet(self.client, tweet.id, Config.NO_IMAGE_MESSAGE)
        self.hourly_reply_count += 1

    def _process_single_tweet(self, tweet, media_lookup, user_lookup):
        """Processes a single mention."""
        if self.state.is_processed(tweet.id):
            logger.debug(f"Tweet {tweet.id} already processed. Skipping.")
            return

        author = user_lookup.get(tweet.author_id)
        if not author or author.id == self.bot_user_id or author.protected:
            reason = "author not found" if not author else \
                     "it's a self-reply" if author.id == self.bot_user_id else \
                     "author is protected"
            logger.info(f"Skipping tweet {tweet.id} because {reason}.")
            self.state.add_tweet(tweet.id)
            return

        image_bytes, _ = process_tweet_media(tweet, media_lookup)
        if image_bytes:
            self._handle_image_tweet(tweet, image_bytes)
        else:
            self._handle_text_tweet(tweet)
        
        self.state.add_tweet(tweet.id)
        time.sleep(2)

    def process_mentions(self):
        """Fetches and processes new mentions."""
        if not self._can_check_for_mentions():
            return
        self.last_check_time = time.time()
        self._reset_hourly_rate_limit()

        if self.hourly_reply_count >= Config.MAX_REPLIES_PER_HOUR:
            logger.warning("Hourly reply limit reached. Skipping mention check.")
            return

        mentions = get_mentions(self.client, self.bot_user_id)
        if not mentions or not mentions.data:
            logger.info("No new mentions found.")
            return

        media_lookup = {media.media_key: media for media in mentions.includes.get('media', [])}
        user_lookup = {user.id: user for user in mentions.includes.get('users', [])}

        logger.info(f"Found {len(mentions.data)} new mentions to process.")
        for tweet in reversed(mentions.data):  # Process oldest first
            try:
                self._process_single_tweet(tweet, media_lookup, user_lookup)
            except Exception as e:
                logger.error(f"Unhandled error processing tweet {tweet.id}: {e}", exc_info=True)
                self.state.add_tweet(tweet.id) # Mark as processed to prevent retries

    def run(self):
        """Starts the main bot loop."""
        logger.info("Venice Art Critic Bot is now running.")
        while True:
            try:
                self.process_mentions()
                self.state.save()
            except KeyboardInterrupt:
                logger.info("Bot stopped by user. Saving state...")
                self.state.save()
                break
            except Exception as e:
                logger.critical(f"An unexpected critical error occurred in the main loop: {e}", exc_info=True)
                time.sleep(60) # Wait a minute before retrying on critical failure 