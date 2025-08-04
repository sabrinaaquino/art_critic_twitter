import base64
import requests
import logging
from config import Config

logger = logging.getLogger(__name__)

def get_expert_analysis(user_message: str, image_bytes: bytes = None, context_text: str = None) -> str:
    """
    STEP 1: Sends the user's query to the expert model for a detailed analysis.
    Uses Venice's web-enabled models for current information and image models for visual content.
    """
    url = Config.VENICE_URL
    headers = {
        "Authorization": f"Bearer {Config.VENICE_API_KEY}",
        "Content-Type": "application/json"
    }

    # The system prompt is now managed entirely in Config.
    # It's designed to handle both direct questions and replies with context.
    expert_prompt = Config.EXPERT_SYSTEM_PROMPT

    # --- Construct the User's Message ---
    # If context is available, frame the message to make it clear it's a continuing conversation.
    if context_text:
        if context_text.startswith('[CONTINUING CONVERSATION]'):
            # This is a direct reply to the bot - continuing conversation
            clean_context = context_text.replace('[CONTINUING CONVERSATION] ', '').replace('[CONTINUING CONVERSATION]', '')
            final_user_message = f'CONTINUING CONVERSATION: Previous context: "{clean_context}". User now asked: "{user_message}"'
        else:
            # This is context from a conversation but not directly replying to bot
            final_user_message = f'CONVERSATION CONTEXT: In response to the tweet "{context_text}", the user asked: "{user_message}"'
    else:
        final_user_message = f'NEW CONVERSATION: User asked: "{user_message}"'

    # --- Construct the Payload ---
    if image_bytes:
        # Image request
        model = Config.VENICE_MODEL_MISTRAL
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # Use the user's message, or a simple default
        message_text = final_user_message.strip() or "What's in this image?"
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": expert_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": message_text},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
                    ]
                }
            ]
        }
    else:
        # Text-only request - use web-enabled model for current information
        model = Config.VENICE_MODEL_WEB
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": expert_prompt},
                {"role": "user", "content": final_user_message}
            ]
        }

    try:
        logger.info(f"Using Venice model: {model} for {'image' if image_bytes else 'text'} analysis")
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()["choices"][0]["message"]["content"].strip()
        logger.info(f"Successfully got {'web-enabled' if model == Config.VENICE_MODEL_WEB else 'vision'} analysis from Venice")
        return result
    except Exception as e:
        logger.error(f"Error calling Venice API with model {model}: {e}")
        return Config.ERROR_MESSAGE

def summarize_analysis(analysis_text: str) -> str:
    """
    STEP 2: Sends the detailed analysis to a model for summarization.
    """
    url = Config.VENICE_URL
    headers = {"Authorization": f"Bearer {Config.VENICE_API_KEY}", "Content-Type": "application/json"}
    
    summarizer_prompt = """
You are a ruthless editor. Your only job is to read the following text and extract the most important, core message.
Present these key points as a clear, concise summary. Remove all pleasantries and introductory text.
"""
    
    payload = {
        "model": Config.VENICE_MODEL_UNIX,
        "messages": [{"role": "user", "content": f"{summarizer_prompt}\n\n---Text to Summarize---\n{analysis_text}"}]
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Error in Step 2 (Summarization): {e}")
        return Config.ERROR_MESSAGE

def craft_tweet(summary_text: str) -> str:
    """
    STEP 3: Sends the clean summary to a model to craft the final, compliant tweet.
    """
    url = Config.VENICE_URL
    headers = {"Authorization": f"Bearer {Config.VENICE_API_KEY}", "Content-Type": "application/json"}

    crafter_prompt = Config.TWEET_CRAFTER_SYSTEM_PROMPT

    payload = {
        "model": Config.VENICE_MODEL_UNIX,
        "messages": [
            {"role": "system", "content": crafter_prompt},
            {"role": "user", "content": f"Points to rewrite into a tweet:\n{summary_text}"}
        ]
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        initial_tweet = response.json()["choices"][0]["message"]["content"].strip()
        
        # Check for banned patterns and retry if found
        banned_patterns = ["Hey there!", "Hi!", "Hello!", "Stay safe", "Be careful", "Be mindful"]
        if any(pattern in initial_tweet for pattern in banned_patterns):
            logger.warning(f"Tweet contains banned patterns, retrying: {initial_tweet}")
            
            # Retry with stricter prompt
            strict_prompt = f"""{crafter_prompt}

CRITICAL: The following response contained banned phrases. Rewrite it without ANY greetings, moral advice, or generic endings:
{initial_tweet}

Provide ONLY a direct, technical answer with specific facts."""
            
            retry_payload = {
                "model": Config.VENICE_MODEL_UNIX,
                "messages": [
                    {"role": "system", "content": strict_prompt},
                    {"role": "user", "content": f"Original content to improve:\n{summary_text}"}
                ]
            }
            
            retry_response = requests.post(url, json=retry_payload, headers=headers)
            retry_response.raise_for_status()
            return retry_response.json()["choices"][0]["message"]["content"].strip()
        
        return initial_tweet
    except Exception as e:
        logger.error(f"Error in Step 3 (Tweet Crafting): {e}")
        return Config.ERROR_MESSAGE 