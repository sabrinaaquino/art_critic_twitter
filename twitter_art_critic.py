import os
import base64
import requests
import tweepy
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv
import time
import logging

# === Load environment ===
load_dotenv()
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
VENICE_API_KEY = os.getenv("VENICE_API_KEY")

# === Set up logging ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Set up Twitter client ===
client = tweepy.Client(
    bearer_token=TWITTER_BEARER_TOKEN,
    consumer_key=TWITTER_API_KEY,
    consumer_secret=TWITTER_API_SECRET,
    access_token=TWITTER_ACCESS_TOKEN,
    access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
    wait_on_rate_limit=True
)

# === Venice API call with image ===
def send_image_to_venice(image_bytes: bytes, user_message: str = "") -> str:
    url = "https://api.venice.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {VENICE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Convert image to base64
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')

    # Clean up user message (remove bot mention)
    clean_message = user_message.strip()

    # Create the text prompt based on user input
    if clean_message:
        text_prompt = f"User says: '{clean_message}'. Please critique this artwork accordingly. Be honest and direct."
    else:
        text_prompt = "Critique this artwork. Be honest and direct."
    
    payload = {
        "model": "mistral-31-24b",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a discerning art critic with sharp wit and deep knowledge. Be honest and direct - "
                    "praise what deserves praise, critique what needs critique. You can be bold and philosophical, "
                    "Be concise - a few sentences at most."
                )
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": text_prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ],
        "venice_parameters": {
            "include_venice_system_prompt": False,
            "enable_web_search": "auto",
            "enable_web_citations": False
        }
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Error calling Venice API: {e}")
        return "Sorry, I'm having trouble analyzing this artwork right now."

# === Process mentions and images ===
def process_mentions():
    try:
        # Get mentions timeline
        mentions = client.get_users_mentions(
            id=client.get_me().data.id,
            max_results=10,
            tweet_fields=['created_at', 'author_id', 'attachments'],
            expansions=['attachments.media_keys'],
            media_fields=['type', 'url']
        )
        
        if not mentions.data:
            logger.info("No new mentions found")
            return
        
        # Create a mapping of media keys to media objects
        media_lookup = {}

        if mentions.includes and 'media' in mentions.includes:
            for media in mentions.includes['media']:
                media_lookup[media.media_key] = media
        
        for tweet in mentions.data:
            try:
                # Check if tweet has media attachments
                if hasattr(tweet, 'attachments') and tweet.attachments and 'media_keys' in tweet.attachments:
                    media_keys = tweet.attachments['media_keys']
                    
                    # Process each media attachment
                    for media_key in media_keys:
                        if media_key in media_lookup:
                            media = media_lookup[media_key]
                            if media.type == 'photo':
                                # Download the image
                                image_url = media.url
                                response = requests.get(image_url)
                                response.raise_for_status()
                                image_bytes = response.content
                                
                                # Get critique from Venice API
                                critique = send_image_to_venice(image_bytes, tweet.text)
                                
                                # Reply to the tweet with critique
                                client.create_tweet(
                                    text=critique,
                                    in_reply_to_tweet_id=tweet.id
                                )
                                
                                logger.info(f"Replied to tweet {tweet.id} with critique")
                                break
                else:
                    # No image found, reply asking for one
                    client.create_tweet(
                        text="Please attach an image you'd like me to critique! 🎨",
                        in_reply_to_tweet_id=tweet.id
                    )
                    logger.info(f"Replied to tweet {tweet.id} asking for image")
                    
            except Exception as e:
                logger.error(f"Error processing tweet {tweet.id}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error getting mentions: {e}")

# === Main bot loop ===
def run_bot():
    logger.info("🎨 Venice Art Critic Twitter Bot is starting...")
    
    while True:
        try:
            process_mentions()
            # Wait 60 seconds before checking for new mentions
            time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run_bot() 