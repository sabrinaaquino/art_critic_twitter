import logging
import time
import requests
from datetime import datetime, timezone, timedelta
from config import Config
from state import State
from clients import get_twitter_client
from twitter_client import get_mentions, reply_to_tweet, get_tweet_by_id
from venice_api import get_expert_analysis, craft_tweet
from image_processor import process_tweet_media
from typing import List, Optional
from utils import extract_urls_from_entities
import tweepy

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
        # Record session start to avoid replying to older mentions if enabled
        self.session_start = datetime.now(timezone.utc)
        # Rate limit handling
        self.rate_limit_reset_time = 0
        self.rate_limit_remaining = 100  # Conservative default
        self.rate_limit_backoff = 1  # Exponential backoff multiplier
        # No longer using process start time - will calculate lookback time dynamically
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
        except tweepy.errors.TooManyRequests as e:
            # Handle rate limit during initialization
            reset_time = int(e.response.headers.get('x-rate-limit-reset', 0))
            remaining = int(e.response.headers.get('x-rate-limit-remaining', 0))
            logger.critical(f"Rate limit exceeded during bot initialization. Reset at {reset_time}, remaining: {remaining}")
            # Wait for rate limit to reset
            current_time = time.time()
            if reset_time > current_time:
                wait_time = reset_time - current_time + 5
                logger.info(f"Waiting {wait_time:.0f}s for rate limit to reset...")
                time.sleep(wait_time)
                # Retry once
                try:
                    me_response = self.client.get_me()
                    if not me_response or not me_response.data:
                        raise Exception("Could not retrieve bot user information from Twitter after rate limit reset.")
                    bot_id = me_response.data.id
                    logger.info(f"Bot User ID is {bot_id}")
                    return bot_id
                except Exception as retry_e:
                    logger.critical(f"Failed to get bot user ID after rate limit retry: {retry_e}")
                    exit(1)
            else:
                logger.critical("Rate limit expired but still failing. Exiting.")
                exit(1)
        except Exception as e:
            logger.critical(f"Fatal: Failed to get bot user ID. Check credentials and network. Error: {e}")
            exit(1)

    def _handle_rate_limit(self, reset_time: int, remaining: int = 0):
        """Handles Twitter rate limit responses with exponential backoff."""
        current_time = time.time()
        
        if reset_time > current_time:
            # Rate limit active, wait until reset
            wait_time = reset_time - current_time + 5  # Add 5s buffer
            logger.warning(f"Rate limit active. Waiting {wait_time:.0f}s until reset at {reset_time}")
            time.sleep(wait_time)
            self.rate_limit_reset_time = reset_time
            self.rate_limit_remaining = remaining
            self.rate_limit_backoff = 1  # Reset backoff
        else:
            # Rate limit expired, but use exponential backoff
            wait_time = min(Config.MIN_CHECK_INTERVAL * self.rate_limit_backoff, 900)  # Max 15 min
            logger.warning(f"Rate limit expired but using backoff. Waiting {wait_time:.0f}s (backoff: {self.rate_limit_backoff}x)")
            time.sleep(wait_time)
            self.rate_limit_backoff = min(self.rate_limit_backoff * 2, 16)  # Max 16x backoff

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
            
            if time_diff > timedelta(minutes=Config.MAX_TWEET_AGE_MINUTES):
                logger.info(f"Tweet {tweet.id} is {time_diff} old (>{Config.MAX_TWEET_AGE_MINUTES}m). Skipping.")
                return True
            
            logger.debug(f"Tweet {tweet.id} is {time_diff} old (<{Config.MAX_TWEET_AGE_MINUTES}m). Processing.")
            return False
        except Exception as e:
            logger.warning(f"Could not reliably evaluate age for tweet {tweet.id}: {e}. Skipping to avoid wasted calls.")
            return True

    def _extract_context_from_tweet(self, tweet, media_lookup):
        """Extracts context text and images from a tweet, including quote tweets."""
        context_text = None
        context_images = []
        context_urls: List[str] = []
        
        # Check if this tweet has referenced tweets (quote tweets, replies, etc.)
        if hasattr(tweet, 'referenced_tweets') and tweet.referenced_tweets:
            for ref in tweet.referenced_tweets:
                if ref.type == 'quoted':
                    logger.info(f"Tweet {tweet.id} is quoting tweet {ref.id}. Fetching quoted tweet for context.")
                    try:
                        quoted_response = get_tweet_by_id(self.client, ref.id)
                        if quoted_response and quoted_response.data:
                            context_text, quoted_images = self._extract_full_context(quoted_response)
                            # Extract URLs from quoted tweet entities if present
                            context_urls.extend(extract_urls_from_entities(getattr(quoted_response.data, 'entities', None)))
                            context_images.extend(quoted_images)
                            logger.info(f"Successfully extracted context from quoted tweet {ref.id}.")
                        else:
                            logger.warning(f"Could not fetch quoted tweet {ref.id}.")
                    except tweepy.errors.TooManyRequests as e:
                        # Handle rate limit during context fetching
                        reset_time = int(e.response.headers.get('x-rate-limit-reset', 0))
                        remaining = int(e.response.headers.get('x-rate-limit-remaining', 0))
                        logger.error(f"Rate limit exceeded while fetching quoted tweet context. Reset at {reset_time}, remaining: {remaining}")
                        self._handle_rate_limit(reset_time, remaining)
                        break  # Stop fetching more context
                    except tweepy.errors.TweepyException as e:
                        logger.warning(f"Twitter API error fetching quoted tweet {ref.id}: {e}")
                        continue  # Try next referenced tweet
        
        # Also extract URLs from the original tweet if available
        context_urls.extend(extract_urls_from_entities(getattr(tweet, 'entities', None)))

        return context_text, context_images, list(dict.fromkeys(context_urls))
    
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
                            response = requests.get(media.url, timeout=10)
                            if response.status_code == 200:
                                context_images.append(response.content)
                                logger.info(f"Downloaded context image from {media.url}")
                        except requests.exceptions.Timeout:
                            logger.warning(f"Timeout downloading context image from {media.url}")
                        except requests.exceptions.RequestException as e:
                            logger.warning(f"Failed to download context image: {e}")
                        except Exception as e:
                            logger.warning(f"Unexpected error downloading context image: {e}")
        
        # Check for quote tweets in the context tweet (with depth limit)
        if hasattr(tweet_response.data, 'referenced_tweets') and tweet_response.data.referenced_tweets:
            for ref in tweet_response.data.referenced_tweets:
                if ref.type == 'quoted':
                    logger.info(f"Context tweet is quoting tweet {ref.id}. Fetching nested quoted tweet (depth {depth+1}).")
                    try:
                        nested_quoted_response = get_tweet_by_id(self.client, ref.id)
                        if nested_quoted_response and nested_quoted_response.data:
                            quoted_text, quoted_images = self._extract_full_context(nested_quoted_response, depth + 1, max_depth)
                            context_text += f"\n\n[Quoted tweet: {quoted_text}]"
                            context_images.extend(quoted_images)
                            logger.info(f"Successfully extracted nested quoted tweet {ref.id}.")
                    except tweepy.errors.TooManyRequests as e:
                        # Handle rate limit during nested context fetching
                        reset_time = int(e.response.headers.get('x-rate-limit-reset', 0))
                        remaining = int(e.response.headers.get('x-rate-limit-remaining', 0))
                        logger.error(f"Rate limit exceeded while fetching nested quoted tweet context. Reset at {reset_time}, remaining: {remaining}")
                        # Note: We can't call _handle_rate_limit here as it's not a bot method
                        # The error will bubble up to the main processing loop
                        raise  # Re-raise to be handled by the caller
                    except tweepy.errors.TweepyException as e:
                        logger.warning(f"Twitter API error fetching nested quoted tweet {ref.id}: {e}")
                        continue  # Try next referenced tweet
        
        return context_text, context_images

    def _generate_and_send_reply(self, tweet, user_query: str, use_context: Optional[str] = None, urls: Optional[List[str]] = None, image_bytes: Optional[bytes] = None, image_url: Optional[str] = None, article_texts: Optional[List[str]] = None) -> bool:
        """Generates final reply (vision or text path) and posts it. Returns success."""
        try:
            analysis = get_expert_analysis(
                user_query,
                image_bytes=image_bytes,
                image_url=image_url,
                context_text=use_context,
                urls=urls,
                article_texts=article_texts,
            )
            if analysis == Config.ERROR_MESSAGE:
                return False

            use_mistral = bool(image_bytes or image_url)
            final_reply = craft_tweet(analysis, full_analysis=None, use_mistral=use_mistral)
            if not final_reply or final_reply == Config.ERROR_MESSAGE:
                return False

            try:
                reply_response = reply_to_tweet(self.client, tweet.id, final_reply)
                if reply_response is not None:
                    self.hourly_reply_count += 1
                    if not self.state.get_allowed_author(tweet.conversation_id):
                        self.state.set_allowed_author(tweet.conversation_id, tweet.author_id)
                    return True
                return False
            except tweepy.errors.TooManyRequests as e:
                # Handle rate limit during reply posting
                reset_time = int(e.response.headers.get('x-rate-limit-reset', 0))
                remaining = int(e.response.headers.get('x-rate-limit-remaining', 0))
                logger.error(f"Rate limit exceeded while posting reply. Reset at {reset_time}, remaining: {remaining}")
                self._handle_rate_limit(reset_time, remaining)
                return False
            except tweepy.errors.TweepyException as e:
                logger.error(f"Twitter API error while posting reply: {e}")
                return False
        except Exception as e:
            logger.error(f"Error generating/sending reply for tweet {tweet.id}: {e}")
            return False

    def _handle_image_tweet(self, tweet, image_bytes, image_url: Optional[str] = None, context_text: Optional[str] = None, urls: Optional[List[str]] = None, article_texts: Optional[List[str]] = None):
        """Handles image tweets with three-step AI pipeline."""
        user_query = tweet.text.replace("@venice_bot", "").strip()
        return self._generate_and_send_reply(
            tweet,
            user_query,
            use_context=context_text,
            urls=urls,
            image_bytes=image_bytes,
            image_url=image_url,
            article_texts=article_texts,
        )

    def _handle_text_tweet(self, tweet, context_text: Optional[str] = None, urls: Optional[List[str]] = None, article_texts: Optional[List[str]] = None):
        """Handles text tweets with three-step AI pipeline."""
        user_query = tweet.text.replace("@venice_bot", "").strip()
        return self._generate_and_send_reply(
            tweet,
            user_query,
            use_context=context_text,
            urls=urls,
            image_bytes=None,
            image_url=None,
            article_texts=article_texts,
        )

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

        # Skip tweets older than 20 minutes
        if self._is_tweet_too_old(tweet):
            logger.info(f"Skipping tweet {tweet.id} because it's older than {Config.MAX_TWEET_AGE_MINUTES} minutes.")
            self.state.add_tweet(tweet.id)
            return

        # --- ENHANCED CONTEXT-AWARE LOGIC ---
        context_text = None
        context_images = []
        context_urls = []
        
        # Check if this mention is tagging the bot in an existing tweet (not a reply)
        if tweet.conversation_id == tweet.id:
            # This is a direct mention in a standalone tweet, check for quote tweets
            context_text, context_images, context_urls = self._extract_context_from_tweet(tweet, media_lookup)
        else:
            # This is part of a conversation thread
            # Check if this tweet is replying directly to the bot (continuing conversation)
            if hasattr(tweet, 'in_reply_to_user_id') and tweet.in_reply_to_user_id == self.bot_user_id:
                # This is a direct reply to the bot - we have a continuing conversation
                # Get the conversation root to understand the overall context
                parent_tweet_id = tweet.conversation_id
                logger.info(f"Tweet {tweet.id} is replying to bot in conversation {tweet.conversation_id}. This is a CONTINUING conversation.")
                is_continuing_conversation = True
            else:
                # This is part of a conversation but not directly replying to bot
                # For mentions in threads, we want the original tweet they're asking about
                # First try to get the conversation root (original tweet)
                parent_tweet_id = tweet.conversation_id
                logger.info(f"Tweet {tweet.id} is part of conversation {tweet.conversation_id}. Fetching original tweet for context.")
                is_continuing_conversation = False
            
            try:
                parent_tweet_response = get_tweet_by_id(self.client, parent_tweet_id)
                if parent_tweet_response and parent_tweet_response.data:
                    # Extract context from the parent tweet
                    context_text, context_images = self._extract_full_context(parent_tweet_response)
                    if is_continuing_conversation:
                        # For continuing conversations, add a special marker
                        context_text = f"[CONTINUING CONVERSATION] {context_text}" if context_text else "[CONTINUING CONVERSATION]"
                    
                    # Extract URLs from parent and current tweets
                    context_urls.extend(extract_urls_from_entities(getattr(parent_tweet_response.data, 'entities', None)))
                    context_urls.extend(extract_urls_from_entities(getattr(tweet, 'entities', None)))
                    
                    # Debug logging
                    logger.info(f"Successfully fetched context from tweet {parent_tweet_id}. Continuing: {is_continuing_conversation}")
                    logger.info(f"Context text length: {len(context_text) if context_text else 0}")
                    if context_text:
                        logger.info(f"Context preview: {context_text[:200]}...")
                else:
                    logger.warning(f"Could not fetch parent tweet {parent_tweet_id}.")
            except tweepy.errors.TooManyRequests as e:
                # Handle rate limit during parent tweet fetching
                reset_time = int(e.response.headers.get('x-rate-limit-reset', 0))
                remaining = int(e.response.headers.get('x-rate-limit-remaining', 0))
                logger.error(f"Rate limit exceeded while fetching parent tweet context. Reset at {reset_time}, remaining: {remaining}")
                self._handle_rate_limit(reset_time, remaining)
                return  # Exit processing this tweet
            except tweepy.errors.TweepyException as e:
                logger.warning(f"Twitter API error fetching parent tweet {parent_tweet_id}: {e}")
                # Continue without context
            except Exception as e:
                logger.error(f"Unexpected error fetching parent tweet context: {e}")
                # Continue without context
        # --- END ENHANCED CONTEXT-AWARE LOGIC ---

        # Process the mention's own media
        try:
            image_bytes, image_url = process_tweet_media(tweet, media_lookup)
        except tweepy.errors.TooManyRequests as e:
            # Handle rate limit during media processing
            reset_time = int(e.response.headers.get('x-rate-limit-reset', 0))
            remaining = int(e.response.headers.get('x-rate-limit-remaining', 0))
            logger.error(f"Rate limit exceeded during media processing. Reset at {reset_time}, remaining: {remaining}")
            self._handle_rate_limit(reset_time, remaining)
            return  # Exit processing this tweet
        except tweepy.errors.TweepyException as e:
            logger.warning(f"Twitter API error during media processing: {e}")
            image_bytes, image_url = None, None
        except Exception as e:
            logger.warning(f"Unexpected error during media processing: {e}")
            image_bytes, image_url = None, None
        
        # If we have context images but no image in the mention itself, use the first context image
        if not image_bytes and context_images:
            image_bytes = context_images[0]
            image_url = None  # context images are bytes-only
            logger.info(f"Using context image for analysis of tweet {tweet.id}")
        
        # No pre-extraction: let Venice handle URLs directly
        article_texts = []
        if image_bytes:
            logger.info(f"Vision path: Mistral will be used. Image URL present: {bool(image_url)}")
            reply_successful = self._handle_image_tweet(
                tweet,
                image_bytes,
                image_url=image_url,
                context_text=context_text,
                urls=context_urls,
                article_texts=article_texts,
            )
        else:
            reply_successful = self._handle_text_tweet(tweet, context_text=context_text, urls=context_urls, article_texts=article_texts)
        
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

        # Calculate start time as 20 minutes ago
        if Config.USE_SESSION_START_CUTOFF:
            lookback_time = max(
                self.session_start,
                datetime.now(timezone.utc) - timedelta(minutes=Config.MAX_TWEET_AGE_MINUTES)
            )
        else:
            lookback_time = datetime.now(timezone.utc) - timedelta(minutes=Config.MAX_TWEET_AGE_MINUTES)
        ms = int(lookback_time.microsecond / 1000)
        start_time_rfc3339 = f"{lookback_time.strftime('%Y-%m-%dT%H:%M:%S')}.{ms:03d}Z"
        
        try:
            mentions = get_mentions(self.client, self.bot_user_id, start_time=start_time_rfc3339)
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

                    # Age filtering is now handled by the API start_time parameter and _is_tweet_too_old() method
                    # Additional guard: ignore tweets created before this session started (if enabled)
                    if Config.USE_SESSION_START_CUTOFF:
                        created_at = getattr(tweet, 'created_at', None)
                        if created_at:
                            try:
                                created_dt = created_at if not isinstance(created_at, str) else datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                                if created_dt < self.session_start:
                                    logger.info(f"Skipping tweet {tweet.id} created before session start.")
                                    self.state.add_tweet(tweet.id)
                                    continue
                            except Exception:
                                pass
                    
                    logger.info(f"Starting to process tweet {tweet.id} from @{username}")
                    self._process_single_tweet(tweet, media_lookup, user_lookup)
                    logger.info(f"Finished processing tweet {tweet.id}")
                except Exception as e:
                    logger.error(f"Unhandled error processing tweet {tweet.id}: {e}", exc_info=True)
                    self.state.add_tweet(tweet.id) # Mark as processed to prevent retries
            
            # Update timestamp after all processing is complete
            self.last_check_time = time.time()
            logger.debug(f"Finished processing mentions. Next check allowed after {Config.MIN_CHECK_INTERVAL}s.")
            
        except tweepy.errors.TooManyRequests as e:
            # Handle rate limit
            reset_time = int(e.response.headers.get('x-rate-limit-reset', 0))
            remaining = int(e.response.headers.get('x-rate-limit-remaining', 0))
            logger.error(f"Rate limit exceeded. Reset at {reset_time}, remaining: {remaining}")
            self._handle_rate_limit(reset_time, remaining)
        except tweepy.errors.TweepyException as e:
            logger.error(f"Twitter API error: {e}")
            # Use exponential backoff for other Twitter errors
            wait_time = min(Config.MIN_CHECK_INTERVAL * self.rate_limit_backoff, 300)  # Max 5 min
            logger.warning(f"Twitter error, backing off for {wait_time:.0f}s")
            time.sleep(wait_time)
            self.rate_limit_backoff = min(self.rate_limit_backoff * 2, 16)
        except Exception as e:
            logger.error(f"Unexpected error in process_mentions: {e}", exc_info=True)
            # Use exponential backoff for unexpected errors
            wait_time = min(Config.MIN_CHECK_INTERVAL * self.rate_limit_backoff, 300)
            logger.warning(f"Unexpected error, backing off for {wait_time:.0f}s")
            time.sleep(wait_time)
            self.rate_limit_backoff = min(self.rate_limit_backoff * 2, 16)

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