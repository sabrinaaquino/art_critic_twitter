import base64
import requests
import logging
from config import Config

logger = logging.getLogger(__name__)

def send_image_to_venice(image_bytes: bytes, user_message: str = "") -> str:
    """Send image to Venice API for art critique."""
    url = Config.VENICE_URL
    headers = {
        "Authorization": f"Bearer {Config.VENICE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Convert image to base64
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')

    # Clean up user message (remove bot mention)
    clean_message = user_message.strip()

    # Create the text prompt based on user input
    if clean_message:
        text_prompt = f"User says: '{clean_message}'. Please critique this artwork accordingly. Be honest and direct, and keep your entire response under 280 characters."
    else:
        text_prompt = "Critique this artwork. Be honest and direct, and keep your entire response under 280 characters."
    
    payload = {
        "model": Config.VENICE_MODEL,
        "messages": [
            {
                "role": "system",
                "content": Config.SYSTEM_PROMPT
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
        critique = response.json()["choices"][0]["message"]["content"].strip()
        
        # Final check to enforce character limit
        if len(critique) > 280:
            logger.warning(f"Venice API returned a critique that was too long ({len(critique)} chars). Truncating.")
            # Find the last space within the limit to avoid cutting off words
            last_space = critique[:277].rfind(' ')
            if last_space != -1:
                critique = critique[:last_space] + "..."
            else:
                critique = critique[:277] + "..."
                
        return critique
    except Exception as e:
        logger.error(f"Error calling Venice API: {e}")
        return Config.ERROR_MESSAGE 