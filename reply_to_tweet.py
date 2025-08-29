#!/usr/bin/env python3
"""
Script to manually reply to a specific tweet by URL.
Useful for testing or handling tweets that got missed.
"""

import sys
import os
import re
import time
import requests
from typing import List, Optional, Tuple

# Ensure imports work whether run from repo root or within the package dir
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

from clients import get_twitter_client
from twitter_client import get_tweet_by_id, reply_to_tweet
from venice_api import get_expert_analysis, craft_tweet
from image_processor import process_tweet_media
from utils import extract_urls_from_entities, extract_urls_from_text
import tweepy


def handle_rate_limit(e: tweepy.errors.TooManyRequests):
    """Handle Twitter rate limit with proper wait time."""
    try:
        reset_time = int(e.response.headers.get('x-rate-limit-reset', 0))
        remaining = int(e.response.headers.get('x-rate-limit-remaining', 0))
        current_time = time.time()
        
        if reset_time > current_time:
            wait_time = reset_time - current_time + 5  # Add 5s buffer
            print(f"⚠️ Rate limit exceeded. Waiting {wait_time:.0f}s until reset...")
            print(f"   Reset at: {reset_time}, Remaining: {remaining}")
            time.sleep(wait_time)
            return True
        else:
            print("⚠️ Rate limit expired but still failing. Waiting 60s...")
            time.sleep(60)
            return True
    except Exception:
        print("⚠️ Could not parse rate limit info. Waiting 60s...")
        time.sleep(60)
        return True


def extract_tweet_id(url: str) -> Optional[str]:
    """Extract tweet ID from Twitter URL or return the numeric input as-is."""
    match = re.search(r'/status/(\d+)', url)
    if match:
        return match.group(1)
    if url.isdigit():
        return url
    return None


def get_tweet_content(client, tweet_id: str) -> Tuple[object, Optional[str], dict, List[str], Optional[bytes], Optional[str]]:
    """Fetch tweet content, context, media lookup, and extracted URLs."""
    print(f"Fetching tweet {tweet_id}...")
    
    try:
        tweet_response = get_tweet_by_id(client, tweet_id)
        if not tweet_response or not tweet_response.data:
            print("❌ Could not fetch tweet")
            return None, None, None, [], None, None
        
        tweet = tweet_response.data
        print(f"✅ Tweet found: {tweet.text[:100]}...")
        print(f"🔍 Tweet ID: {tweet.id}, Author: {getattr(tweet, 'author_id', 'unknown')}")
        print(f"🔍 Tweet attachments: {getattr(tweet, 'attachments', 'None')}")
        print(f"🔍 Tweet entities: {getattr(tweet, 'entities', 'None')}")
        
        # Conversation context
        context_text = None
        urls: List[str] = []
        context_image_bytes = None
        context_image_url = None
        if hasattr(tweet, 'conversation_id') and tweet.conversation_id != tweet.id:
            print("🔍 This tweet is part of a conversation, fetching context...")
            try:
                parent_response = get_tweet_by_id(client, tweet.conversation_id)
                if parent_response and parent_response.data:
                    context_text = parent_response.data.text
                    print(f"📋 Context found: {context_text[:100]}...")
                    # URLs from parent
                    urls.extend(extract_urls_from_entities(getattr(parent_response.data, 'entities', None)))
                    # Fallback: parse text
                    urls.extend(extract_urls_from_text(context_text))
                    
                    # Check if parent tweet has media (using main bot logic)
                    if hasattr(parent_response.data, 'attachments') and parent_response.data.attachments:
                        media_keys = parent_response.data.attachments.get('media_keys', [])
                        if parent_response.includes and 'media' in parent_response.includes:
                            parent_media_lookup = {media.media_key: media for media in parent_response.includes['media']}
                            print(f"📸 Parent tweet has {len(parent_response.includes['media'])} media items")
                            for media_key in media_keys:
                                media = parent_media_lookup.get(media_key)
                                if media and media.type == 'photo':
                                    try:
                                        print(f"🖼️ Downloading context image from {media.url}")
                                        headers = {
                                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                                        }
                                        response = requests.get(media.url, timeout=10, headers=headers)
                                        if response.status_code == 200:
                                            context_image_bytes = response.content
                                            context_image_url = media.url
                                            print(f"✅ Downloaded context image ({len(context_image_bytes)} bytes)")
                                            break
                                    except Exception as e:
                                        print(f"⚠️ Failed to download context image: {e}")
                        else:
                            print("📸 Parent tweet has no media includes")
                    else:
                        print("📸 Parent tweet has no media attachments")
                else:
                    print("⚠️ Could not fetch parent tweet")
            except tweepy.errors.TooManyRequests as e:
                if handle_rate_limit(e):
                    # Retry once after rate limit
                    try:
                        parent_response = get_tweet_by_id(client, tweet.conversation_id)
                        if parent_response and parent_response.data:
                            context_text = parent_response.data.text
                            print(f"📋 Context found (retry): {context_text[:100]}...")
                            urls.extend(extract_urls_from_entities(getattr(parent_response.data, 'entities', None)))
                            urls.extend(extract_urls_from_text(context_text))
                            
                            # Check if parent tweet has media (retry) - using main bot logic
                            if hasattr(parent_response.data, 'attachments') and parent_response.data.attachments:
                                media_keys = parent_response.data.attachments.get('media_keys', [])
                                if parent_response.includes and 'media' in parent_response.includes:
                                    parent_media_lookup = {media.media_key: media for media in parent_response.includes['media']}
                                    print(f"📸 Parent tweet has {len(parent_response.includes['media'])} media items (retry)")
                                    for media_key in media_keys:
                                        media = parent_media_lookup.get(media_key)
                                        if media and media.type == 'photo':
                                            try:
                                                print(f"🖼️ Downloading context image from {media.url} (retry)")
                                                headers = {
                                                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                                                }
                                                response = requests.get(media.url, timeout=10, headers=headers)
                                                if response.status_code == 200:
                                                    context_image_bytes = response.content
                                                    context_image_url = media.url
                                                    print(f"✅ Downloaded context image ({len(context_image_bytes)} bytes) (retry)")
                                                    break
                                            except Exception as e:
                                                print(f"⚠️ Failed to download context image (retry): {e}")
                    except Exception as retry_e:
                        print(f"⚠️ Retry failed: {retry_e}")
        else:
            print("📝 This is a standalone tweet (no conversation context)")
        
        # Media lookup - Debug the response structure
        media_lookup = {}
        print(f"🔍 Tweet response includes: {getattr(tweet_response, 'includes', 'None')}")
        if hasattr(tweet_response, 'includes') and tweet_response.includes:
            print(f"📸 Includes keys: {list(tweet_response.includes.keys())}")
            if 'media' in tweet_response.includes:
                media_lookup = {media.media_key: media for media in tweet_response.includes['media']}
                print(f"📸 Media includes found: {len(tweet_response.includes['media'])} items")
                for media in tweet_response.includes['media']:
                    print(f"   - Media key: {media.media_key}, Type: {getattr(media, 'type', 'unknown')}, URL: {getattr(media, 'url', 'none')}")
            else:
                print("📸 'media' key not found in includes")
        else:
            print("📸 No includes in tweet response")
        
        # Extract URLs from this tweet
        urls.extend(extract_urls_from_entities(getattr(tweet, 'entities', None)))
        urls.extend(extract_urls_from_text(tweet.text))
        urls = list(dict.fromkeys(urls))
        
        return tweet, context_text, media_lookup, urls, context_image_bytes, context_image_url
        
    except tweepy.errors.TooManyRequests as e:
        if handle_rate_limit(e):
            # Retry once after rate limit
            return get_tweet_content(client, tweet_id)
        return None, None, None, [], None, None
    except tweepy.errors.TweepyException as e:
        print(f"❌ Twitter API error: {e}")
        return None, None, None, [], None, None
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None, None, None, [], None, None


def generate_response(tweet_text: str, context_text: Optional[str] = None, image_bytes: Optional[bytes] = None, image_url: Optional[str] = None, urls: Optional[List[str]] = None, article_texts: Optional[List[str]] = None, has_image_context: bool = False) -> Optional[str]:
    """Generate bot response using the 3-step pipeline."""
    print("🤖 Generating response...")
    print(f"📝 Tweet text: {tweet_text}")
    if context_text:
        print(f"📋 Using context: {context_text[:100]}...")
    else:
        print("📋 No context available")
    if urls:
        print(f"🔗 URLs: {', '.join(urls[:3])}{'...' if len(urls) > 3 else ''}")
    
    try:
        # Step 1: Expert Analysis (concise and tweet-ready)
        print("🔍 Step 1: Expert Analysis (concise)...")
        concise_answer = get_expert_analysis(tweet_text, image_bytes=image_bytes, image_url=image_url, context_text=context_text, urls=urls, article_texts=article_texts)
        
        # Step 2: Tweet Crafting using concise answer directly
        print("🎨 Step 2: Tweet Crafting...")
        # Use vision model (Mistral) if we have image bytes OR image URL (matching main bot logic)
        use_vision_model = bool(image_bytes or image_url)
        if use_vision_model:
            print("🔮 Using vision-capable model for crafting")
        final_response = craft_tweet(concise_answer, use_mistral=use_vision_model)
        
        return final_response
    except Exception as e:
        print(f"❌ Error generating response: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    if len(sys.argv) != 2:
        print("Usage: python reply_to_tweet.py <tweet_url_or_id>")
        print("Examples:")
        print("  python reply_to_tweet.py https://x.com/user/status/1234567890")
        print("  python reply_to_tweet.py 1234567890")
        sys.exit(1)
    
    tweet_input = sys.argv[1]
    tweet_id = extract_tweet_id(tweet_input)
    
    if not tweet_id:
        print("❌ Could not extract tweet ID from input")
        sys.exit(1)
    
    print(f"🐦 Processing tweet ID: {tweet_id}")
    
    # Get Twitter client
    try:
        client = get_twitter_client()
        print("✅ Connected to Twitter API")
    except Exception as e:
        print(f"❌ Could not connect to Twitter: {e}")
        sys.exit(1)
    
    # Fetch tweet content
    tweet, context_text, media_lookup, urls, context_image_bytes, context_image_url = get_tweet_content(client, tweet_id)
    if not tweet:
        sys.exit(1)
    
    # Process media if any
    image_bytes = None
    image_url = None
    print(f"🔍 Media lookup contains {len(media_lookup)} items")
    
    # First try to get image from Twitter media attachments
    if hasattr(tweet, 'attachments') and tweet.attachments:
        print(f"📎 Tweet has attachments: {tweet.attachments}")
        image_bytes, image_url = process_tweet_media(tweet, media_lookup)
        if image_bytes:
            print("🖼️ Found image in tweet via media attachments (vision path)")
            if image_url:
                print(f"🔗 Image URL: {image_url}")
    
    # If no image from attachments, try to download from URLs in the tweet
    if not image_bytes and urls:
        print("🔍 No image from attachments, trying to download from URLs...")
        for url in urls:
            if 'photo/1' in url or 'photo/' in url or any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                print(f"🖼️ Attempting to download image from URL: {url}")
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }
                    response = requests.get(url, headers=headers, timeout=10)
                    response.raise_for_status()
                    
                    content_type = response.headers.get('content-type', '')
                    if content_type.startswith('image/'):
                        image_bytes = response.content
                        image_url = url
                        print(f"✅ Successfully downloaded image ({len(image_bytes)} bytes) from URL: {url}")
                        print("🖼️ Using vision model path via URL download")
                        break
                    else:
                        print(f"⚠️ URL returned non-image content: {content_type}")
                        
                except Exception as e:
                    print(f"⚠️ Failed to download from URL {url}: {e}")
                    continue
    
    # Force vision model if we detect image URLs even if download failed
    has_image_context = bool(image_bytes) or any('photo/' in url or any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']) for url in urls)
    
    # Use context image if no direct image found
    if not image_bytes and context_image_bytes:
        image_bytes = context_image_bytes
        image_url = context_image_url
        print("🖼️ Using image from conversation context")
    
    if not image_bytes:
        print("⚠️ No image could be retrieved from any source")
        if has_image_context:
            print("🖼️ But detected image URLs - will use vision model with URL context")
    else:
        print(f"🖼️ Image ready for vision model: {len(image_bytes)} bytes")
    
    # Skip pre-extracting articles; Venice can read URLs directly
    article_texts: List[str] = []
    
    # Generate response
    response = generate_response(tweet.text, context_text, image_bytes, image_url, urls, article_texts, has_image_context)
    if not response:
        sys.exit(1)
    
    print("\n" + "="*60)
    print("🎯 GENERATED RESPONSE:")
    print("="*60)
    print(response)
    print("="*60)
    print(f"📏 Length: {len(response)} characters")
    
    # Ask if user wants to actually reply
    while True:
        choice = input("\nDo you want to post this reply? (y/n/edit): ").lower().strip()
        
        if choice == 'y' or choice == 'yes':
            print("📤 Posting reply...")
            try:
                reply_response = reply_to_tweet(client, tweet_id, response)
                if reply_response:
                    print("✅ Reply posted successfully!")
                    if hasattr(reply_response, 'data') and 'id' in reply_response.data:
                        print(f"🔗 Reply URL: https://x.com/venice_mind/status/{reply_response.data['id']}")
                else:
                    print("❌ Failed to post reply")
            except tweepy.errors.TooManyRequests as e:
                print("⚠️ Rate limit exceeded while posting reply...")
                if handle_rate_limit(e):
                    print("🔄 Retrying reply after rate limit...")
                    try:
                        reply_response = reply_to_tweet(client, tweet_id, response)
                        if reply_response:
                            print("✅ Reply posted successfully (retry)!")
                            if hasattr(reply_response, 'data') and 'id' in reply_response.data:
                                print(f"🔗 Reply URL: https://x.com/venice_mind/status/{reply_response.data['id']}")
                        else:
                            print("❌ Retry failed to post reply")
                    except Exception as retry_e:
                        print(f"❌ Retry failed: {retry_e}")
            except tweepy.errors.TweepyException as e:
                print(f"❌ Twitter API error posting reply: {e}")
            except Exception as e:
                print(f"❌ Error posting reply: {e}")
                import traceback
                traceback.print_exc()
            break
            
        elif choice == 'n' or choice == 'no':
            print("👍 Response generated but not posted.")
            break
            
        elif choice == 'edit':
            new_response = input("Enter your edited response: ").strip()
            if new_response:
                response = new_response
                print(f"✏️ Response updated: {response}")
                print(f"📏 New length: {len(response)} characters")
            continue
            
        else:
            print("Please enter 'y', 'n', or 'edit'")

if __name__ == "__main__":
    main() 