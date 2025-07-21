import logging
import requests
from io import BytesIO

logger = logging.getLogger(__name__)

def process_tweet_media(tweet, media_lookup):
    """Downloads the first photo found in a tweet's media attachments."""
    if not tweet.attachments or not tweet.attachments.get('media_keys'):
        logger.info(f"No media attachments found in tweet {tweet.id}")
        return None, None

    for media_key in tweet.attachments['media_keys']:
        media = media_lookup.get(media_key)
        if media and media.type == 'photo':
            image_url = media.url
            logger.info(f"Found image URL in tweet {tweet.id}: {image_url}")
            
            try:
                response = requests.get(image_url, stream=True)
                response.raise_for_status()
                
                image_bytes = BytesIO(response.content).read()
                logger.info(f"Successfully downloaded image from {image_url}")
                return image_bytes, image_url
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to download image from {image_url}: {e}")
                return None, None

    logger.info(f"No photos found in tweet {tweet.id} attachments.")
    return None, None 