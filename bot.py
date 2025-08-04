import logging
import time
from config import Config
from state import State
from clients import get_twitter_client
from twitter_client import get_mentions, reply_to_tweet, get_tweet_by_id
from venice_api import get_expert_analysis, summarize_analysis, craft_tweet
from image_processor import process_tweet_media

logger = logging.getLogger(__name__)


class VeniceBot:
    """Core bot class."""

    def __init__(self):
        """Initializes the bot."""
        logger.info("Initializing bot...")
        self.state = State()
        self.state.load()  # Load the previously processed tweets from state.json
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

    def _extract_context_from_tweet(self, tweet, media_lookup):
        """Extracts context text and images from a tweet, including quote tweets."""
        context_text = None
        context_images = []
        
        # Check if this tweet has referenced tweets (quote tweets, replies, etc.)
        if hasattr(tweet, 'referenced_tweets') and tweet.referenced_tweets:
            for ref in tweet.referenced_tweets:
                if ref.type == 'quoted':
                    logger.info(f"Tweet {tweet.id} is quoting tweet {ref.id}. Fetching quoted tweet for context.")
                    quoted_response = get_tweet_by_id(self.client, ref.id)
                    if quoted_response and quoted_response.data:
                        context_text, quoted_images = self._extract_full_context(quoted_response)
                        context_images.extend(quoted_images)
                        logger.info(f"Successfully extracted context from quoted tweet {ref.id}.")
                    else:
                        logger.warning(f"Could not fetch quoted tweet {ref.id}.")
        
        return context_text, context_images
    
    def _extract_full_context(self, tweet_response):
        """Extracts comprehensive context from a tweet response including text, images, and quote tweets."""
        context_text = tweet_response.data.text
        context_images = []
        
        # Extract images from this tweet
        if hasattr(tweet_response.data, 'attachments') and tweet_response.data.attachments:
            media_keys = tweet_response.data.attachments.get('media_keys', [])
            if tweet_response.includes and 'media' in tweet_response.includes:
                media_lookup = {media.media_key: media for media in tweet_response.includes['media']}
                for media_key in media_keys:
                    media = media_lookup.get(media_key)
                    if media and media.type == 'photo':
                        try:
                            import requests
                            response = requests.get(media.url)
                            if response.status_code == 200:
                                context_images.append(response.content)
                                logger.info(f"Downloaded context image from {media.url}")
                        except Exception as e:
                            logger.warning(f"Failed to download context image: {e}")
        
        # Check for quote tweets in the context tweet
        if hasattr(tweet_response.data, 'referenced_tweets') and tweet_response.data.referenced_tweets:
            for ref in tweet_response.data.referenced_tweets:
                if ref.type == 'quoted':
                    logger.info(f"Context tweet is quoting tweet {ref.id}. Fetching nested quoted tweet.")
                    nested_quoted_response = get_tweet_by_id(self.client, ref.id)
                    if nested_quoted_response and nested_quoted_response.data:
                        quoted_text, quoted_images = self._extract_full_context(nested_quoted_response)
                        context_text += f"\n\n[Quoted tweet: {quoted_text}]"
                        context_images.extend(quoted_images)
                        logger.info(f"Successfully extracted nested quoted tweet {ref.id}.")
        
        return context_text, context_images

    def _handle_image_tweet(self, tweet, image_bytes, context_text=None):
        """Handles a tweet with an image using the three-step AI chain."""
        logger.info(f"Handling image tweet {tweet.id} with three-step analysis.")
        
        # 1. Get detailed analysis
        analysis = get_expert_analysis(tweet.text, image_bytes=image_bytes, context_text=context_text)
        if not analysis or analysis == Config.ERROR_MESSAGE:
            logger.error(f"Failed to get analysis for image tweet {tweet.id}.")
            return

        # 2. Summarize the analysis
        summary = summarize_analysis(analysis)
        if not summary or summary == Config.ERROR_MESSAGE:
            logger.error(f"Failed to summarize analysis for image tweet {tweet.id}.")
            return
            
        # 3. Craft the final tweet
        final_reply = craft_tweet(summary)
        if final_reply and final_reply != Config.ERROR_MESSAGE:
            reply_to_tweet(self.client, tweet.id, final_reply)
            self.hourly_reply_count += 1
        else:
            logger.error(f"Failed to craft tweet for image tweet {tweet.id}.")

    def _handle_text_tweet(self, tweet, context_text=None):
        """Handles a text-only tweet using the three-step AI chain."""
        logger.info(f"Handling text tweet {tweet.id} with three-step analysis.")

        # 1. Get detailed analysis
        analysis = get_expert_analysis(tweet.text, context_text=context_text)
        if not analysis or analysis == Config.ERROR_MESSAGE:
            logger.error(f"Failed to get analysis for text tweet {tweet.id}.")
            return
            
        # 2. Summarize the analysis
        summary = summarize_analysis(analysis)
        if not summary or summary == Config.ERROR_MESSAGE:
            logger.error(f"Failed to summarize analysis for text tweet {tweet.id}.")
            return
            
        # 3. Craft the final tweet
        final_reply = craft_tweet(summary)
        if final_reply and final_reply != Config.ERROR_MESSAGE:
            reply_to_tweet(self.client, tweet.id, final_reply)
            self.hourly_reply_count += 1
        else:
            logger.error(f"Failed to craft tweet for text tweet {tweet.id}.")

    def _process_single_tweet(self, tweet, media_lookup, user_lookup):
        """Processes a single mention, fetching context if it's a reply."""
        if self.state.is_processed(tweet.id):
            logger.info(f"Tweet {tweet.id} already processed. Skipping.")
            return

        author = user_lookup.get(tweet.author_id)
        if not author or author.protected:
            reason = "author not found" if not author else "author is protected"
            logger.info(f"Skipping tweet {tweet.id} because {reason}.")
            self.state.add_tweet(tweet.id)
            return
            
        # Skip tweets authored by the bot itself (but allow mentions in bot's tweets)
        if author.id == self.bot_user_id:
            logger.info(f"Skipping tweet {tweet.id} because it's authored by the bot itself.")
            self.state.add_tweet(tweet.id)
            return

        # --- ENHANCED CONTEXT-AWARE LOGIC ---
        context_text = None
        context_images = []
        
        # Check if this mention is tagging the bot in an existing tweet (not a reply)
        if tweet.conversation_id == tweet.id:
            # This is a direct mention in a standalone tweet, check for quote tweets
            context_text, context_images = self._extract_context_from_tweet(tweet, media_lookup)
        else:
            # This is part of a conversation thread
            # Check if this tweet is replying directly to the bot (continuing conversation)
            if hasattr(tweet, 'in_reply_to_user_id') and tweet.in_reply_to_user_id == self.bot_user_id:
                # This is a direct reply to the bot - we have a continuing conversation
                # We'll get the conversation root to understand the overall context
                parent_tweet_id = tweet.conversation_id
                logger.info(f"Tweet {tweet.id} is replying to bot in conversation {tweet.conversation_id}. This is a CONTINUING conversation.")
                # Set a flag to indicate this is continuing
                is_continuing_conversation = True
            else:
                # This is part of a conversation but not directly replying to bot
                parent_tweet_id = tweet.conversation_id
                logger.info(f"Tweet {tweet.id} is part of conversation {tweet.conversation_id}. Fetching root tweet for context.")
                is_continuing_conversation = False
            
            parent_tweet_response = get_tweet_by_id(self.client, parent_tweet_id)
            if parent_tweet_response and parent_tweet_response.data:
                # Extract context from the parent tweet
                context_text, context_images = self._extract_full_context(parent_tweet_response)
                if is_continuing_conversation:
                    # For continuing conversations, add a special marker
                    context_text = f"[CONTINUING CONVERSATION] {context_text}" if context_text else "[CONTINUING CONVERSATION]"
                logger.info(f"Successfully fetched context from tweet {parent_tweet_id}. Continuing: {is_continuing_conversation}")
            else:
                logger.warning(f"Could not fetch parent tweet {parent_tweet_id}.")
        # --- END ENHANCED CONTEXT-AWARE LOGIC ---

        # Process the mention's own media
        image_bytes, _ = process_tweet_media(tweet, media_lookup)
        
        # If we have context images but no image in the mention itself, use the first context image
        if not image_bytes and context_images:
            image_bytes = context_images[0]
            logger.info(f"Using context image for analysis of tweet {tweet.id}")
        
        if image_bytes:
            self._handle_image_tweet(tweet, image_bytes, context_text=context_text)
        else:
            self._handle_text_tweet(tweet, context_text=context_text)
        
        self.state.add_tweet(tweet.id)
        time.sleep(2)

    def process_mentions(self):
        """Fetches and processes new mentions."""
        if not self._can_check_for_mentions():
            return
        
        self._reset_hourly_rate_limit()

        if self.hourly_reply_count >= Config.MAX_REPLIES_PER_HOUR:
            logger.warning("Hourly reply limit reached. Skipping mention check.")
            return

        mentions = get_mentions(self.client, self.bot_user_id)
        if not mentions or not mentions.data:
            logger.info("No new mentions found.")
            # Update timestamp even when no mentions found
            self.last_check_time = time.time()
            return

        media_lookup = {media.media_key: media for media in mentions.includes.get('media', [])}
        user_lookup = {user.id: user for user in mentions.includes.get('users', [])}

        logger.info(f"Found {len(mentions.data)} new mentions to process.")
        for tweet in reversed(mentions.data):  # Process oldest first
            try:
                logger.info(f"Starting to process tweet {tweet.id} from @{user_lookup.get(tweet.author_id, {}).get('username', 'unknown')}")
                self._process_single_tweet(tweet, media_lookup, user_lookup)
                logger.info(f"Finished processing tweet {tweet.id}")
            except Exception as e:
                logger.error(f"Unhandled error processing tweet {tweet.id}: {e}", exc_info=True)
                self.state.add_tweet(tweet.id) # Mark as processed to prevent retries
        
        # Update timestamp after all processing is complete
        self.last_check_time = time.time()
        logger.debug(f"Finished processing mentions. Next check allowed after {Config.MIN_CHECK_INTERVAL}s.")

    def run(self):
        """Starts the main bot loop."""
        logger.info("Venice X Bot is now running.")
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