import logging
import time
import requests
from datetime import datetime, timezone, timedelta
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
        # Capture process start time in RFC3339 for API filtering and as datetime for local checks
        self.process_start_dt = datetime.now(timezone.utc)
        # RFC3339 with milliseconds, e.g., 2025-08-27T03:38:08.694Z
        ms = int(self.process_start_dt.microsecond / 1000)
        self.process_start_rfc3339 = f"{self.process_start_dt.strftime('%Y-%m-%dT%H:%M:%S')}.{ms:03d}Z"
        logger.info(f"Bot process start time captured: {self.process_start_rfc3339}")
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

    def _is_tweet_too_old(self, tweet):
        """Checks if tweet is older than the configured maximum age."""
        try:
            created_at = getattr(tweet, 'created_at', None)
            if created_at is None:
                logger.warning(f"Tweet {tweet.id} missing created_at. Skipping to avoid wasted calls.")
                return True

            # Support both datetime and string timestamps
            if isinstance(created_at, str):
                # Handle RFC3339 like 2025-01-14T12:34:56.000Z
                if created_at.endswith('Z'):
                    tweet_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                else:
                    # Best-effort parse; if it fails, skip
                    try:
                        tweet_time = datetime.fromisoformat(created_at)
                    except Exception:
                        logger.warning(f"Could not parse tweet {tweet.id} timestamp string '{created_at}'. Skipping.")
                        return True
            else:
                tweet_time = created_at  # Assume datetime

            current_time = datetime.now(timezone.utc)
            time_diff = current_time - tweet_time
            
            if time_diff > timedelta(hours=Config.MAX_TWEET_AGE_HOURS):
                logger.info(f"Tweet {tweet.id} is {time_diff} old (>{Config.MAX_TWEET_AGE_HOURS}h). Skipping.")
                return True
            
            logger.debug(f"Tweet {tweet.id} is {time_diff} old (<{Config.MAX_TWEET_AGE_HOURS}h). Processing.")
            return False
        except Exception as e:
            logger.warning(f"Could not reliably evaluate age for tweet {tweet.id}: {e}. Skipping to avoid wasted calls.")
            return True

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
    
    def _extract_full_context(self, tweet_response, depth=0, max_depth=3):
        """Extracts comprehensive context from a tweet response including text, images, and quote tweets."""
        # Prevent infinite recursion
        if depth >= max_depth:
            logger.debug(f"Reached max quote tweet depth ({max_depth}), stopping recursion.")
            return tweet_response.data.text, []
            
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
                            response = requests.get(media.url)
                            if response.status_code == 200:
                                context_images.append(response.content)
                                logger.info(f"Downloaded context image from {media.url}")
                        except Exception as e:
                            logger.warning(f"Failed to download context image: {e}")
        
        # Check for quote tweets in the context tweet (with depth limit)
        if hasattr(tweet_response.data, 'referenced_tweets') and tweet_response.data.referenced_tweets:
            for ref in tweet_response.data.referenced_tweets:
                if ref.type == 'quoted':
                    logger.info(f"Context tweet is quoting tweet {ref.id}. Fetching nested quoted tweet (depth {depth+1}).")
                    nested_quoted_response = get_tweet_by_id(self.client, ref.id)
                    if nested_quoted_response and nested_quoted_response.data:
                        quoted_text, quoted_images = self._extract_full_context(nested_quoted_response, depth + 1, max_depth)
                        context_text += f"\n\n[Quoted tweet: {quoted_text}]"
                        context_images.extend(quoted_images)
                        logger.info(f"Successfully extracted nested quoted tweet {ref.id}.")
        
        return context_text, context_images

    def _handle_image_tweet(self, tweet, image_bytes, context_text=None):
        """Handles image tweets with three-step AI pipeline."""
        user_query = tweet.text.replace("@venice_bot", "").strip()
        
        if context_text and "[CONTINUING CONVERSATION]" in context_text:
            use_context = context_text
        else:
            use_context = None
        
        try:
            analysis = get_expert_analysis(user_query, image_bytes=image_bytes, context_text=use_context)
            if analysis == Config.ERROR_MESSAGE:
                return False
            
            summary = summarize_analysis(analysis)
            if summary == Config.ERROR_MESSAGE:
                return False
            
            final_reply = craft_tweet(summary, full_analysis=analysis)
            if not final_reply or final_reply == Config.ERROR_MESSAGE:
                return False
            
            reply_response = reply_to_tweet(self.client, tweet.id, final_reply)
            if reply_response is not None:
                self.hourly_reply_count += 1
                # Set allowed author for this conversation if not set
                if not self.state.get_allowed_author(tweet.conversation_id):
                    self.state.set_allowed_author(tweet.conversation_id, tweet.author_id)
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error processing image tweet {tweet.id}: {e}")
            return False

    def _handle_text_tweet(self, tweet, context_text=None):
        """Handles text tweets with three-step AI pipeline."""
        user_query = tweet.text.replace("@venice_bot", "").strip()
        
        if context_text and "[CONTINUING CONVERSATION]" in context_text:
            use_context = context_text
        else:
            use_context = None
        
        try:
            analysis = get_expert_analysis(user_query, context_text=use_context)
            if analysis == Config.ERROR_MESSAGE:
                return False
            
            summary = summarize_analysis(analysis)
            if summary == Config.ERROR_MESSAGE:
                return False
            
            final_reply = craft_tweet(summary, full_analysis=analysis)
            if not final_reply or final_reply == Config.ERROR_MESSAGE:
                return False
            
            reply_response = reply_to_tweet(self.client, tweet.id, final_reply)
            if reply_response is not None:
                self.hourly_reply_count += 1
                # Set allowed author for this conversation if not set
                if not self.state.get_allowed_author(tweet.conversation_id):
                    self.state.set_allowed_author(tweet.conversation_id, tweet.author_id)
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error processing text tweet {tweet.id}: {e}")
            return False

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

        # Enforce original-author-only follow-ups within a conversation
        allowed_author = self.state.get_allowed_author(tweet.conversation_id)
        if allowed_author:
            if str(tweet.author_id) != str(allowed_author):
                logger.info(f"Skipping tweet {tweet.id} in conversation {tweet.conversation_id}: author {tweet.author_id} != allowed {allowed_author}.")
                self.state.add_tweet(tweet.id)
                return

        # Skip tweets older than 24 hours
        if self._is_tweet_too_old(tweet):
            logger.info(f"Skipping tweet {tweet.id} because it's older than {Config.MAX_TWEET_AGE_HOURS} hours.")
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
        
        # Handle the tweet and check if reply was successful
        reply_successful = False
        if image_bytes:
            reply_successful = self._handle_image_tweet(tweet, image_bytes, context_text=context_text)
        else:
            reply_successful = self._handle_text_tweet(tweet, context_text=context_text)
        
        # Only mark as processed if the reply was successfully sent
        if reply_successful:
            logger.info(f"Reply sent successfully for tweet {tweet.id}. Marking as processed.")
            self.state.add_tweet(tweet.id)
        else:
            logger.warning(f"Reply failed for tweet {tweet.id}. NOT marking as processed - will retry next time.")
        
        time.sleep(Config.TWEET_PROCESSING_DELAY)

    def process_mentions(self):
        """Fetches and processes new mentions."""
        if not self._can_check_for_mentions():
            return
        
        self._reset_hourly_rate_limit()

        if self.hourly_reply_count >= Config.MAX_REPLIES_PER_HOUR:
            logger.warning("Hourly reply limit reached. Skipping mention check.")
            return

        mentions = get_mentions(self.client, self.bot_user_id, start_time=self.process_start_rfc3339)
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
                # Efficiently get username with fallback
                author = user_lookup.get(tweet.author_id)
                username = author.username if author and hasattr(author, 'username') else 'unknown'

                # Skip mentions created before or at bot start
                created_at = getattr(tweet, 'created_at', None)
                if created_at:
                    if isinstance(created_at, str):
                        # Normalize to datetime
                        if created_at.endswith('Z'):
                            tweet_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        else:
                            tweet_dt = datetime.fromisoformat(created_at)
                    else:
                        tweet_dt = created_at
                    if tweet_dt <= self.process_start_dt:
                        logger.info(f"Skipping tweet {tweet.id} created before startup ({created_at}).")
                        self.state.add_tweet(tweet.id)
                        continue
                else:
                    logger.info(f"Skipping tweet {tweet.id} with no created_at (pre-start safety).")
                    self.state.add_tweet(tweet.id)
                    continue
                
                logger.info(f"Starting to process tweet {tweet.id} from @{username}")
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