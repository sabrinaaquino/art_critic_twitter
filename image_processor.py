import logging
import requests
from io import BytesIO
import re

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
            
            # Try to get the actual image URL from Twitter's media object
            if hasattr(media, 'url') and media.url:
                # Twitter often provides a preview URL, try to get the full resolution
                if '?format=' in image_url:
                    # Remove format parameter to get full resolution
                    image_url = image_url.split('?')[0]
                
                # Try different URL formats
                url_variants = [
                    image_url,
                    image_url.replace('https://pbs.twimg.com/media/', 'https://pbs.twimg.com/media/'),
                    image_url.replace('?format=jpg&name=large', ''),
                    image_url.replace('?format=jpg&name=medium', ''),
                    image_url.replace('?format=jpg&name=small', '')
                ]
                
                for url in url_variants:
                    try:
                        logger.info(f"Attempting to download from: {url}")
                        headers = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                        }
                        response = requests.get(url, stream=True, headers=headers, timeout=10)
                        response.raise_for_status()
                        
                        # Check if we got actual image data
                        content_type = response.headers.get('content-type', '')
                        if content_type.startswith('image/'):
                            image_bytes = BytesIO(response.content).read()
                            logger.info(f"Successfully downloaded image ({len(image_bytes)} bytes) from {url}")
                            return image_bytes, url
                        else:
                            logger.warning(f"URL returned non-image content: {content_type}")
                            
                    except requests.exceptions.RequestException as e:
                        logger.warning(f"Failed to download from {url}: {e}")
                        continue
                
                logger.error(f"All download attempts failed for media key {media_key}")
            else:
                logger.warning(f"No URL found in media object for key {media_key}")
        else:
            logger.info(f"Media {media_key} is not a photo (type: {getattr(media, 'type', 'unknown')})")

    logger.info(f"No photos successfully downloaded from tweet {tweet.id} attachments.")
    return None, None 