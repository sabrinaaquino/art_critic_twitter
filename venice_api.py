import base64
import requests
import logging
from config import Config

logger = logging.getLogger(__name__)

# Module-level constants to avoid recreation
VENICE_URL = Config.VENICE_URL
VENICE_HEADERS = {
    "Authorization": f"Bearer {Config.VENICE_API_KEY}",
    "Content-Type": "application/json"
}

def get_expert_analysis(user_message: str, image_bytes: bytes = None, context_text: str = None) -> str:
    """
    STEP 1: Get focused, honest analysis using a single model for cost efficiency.
    """
    expert_prompt = Config.EXPERT_SYSTEM_PROMPT

    # Filter out old dates to prevent outdated context from interfering with web search
    if context_text:
        outdated_indicators = ["2023", "2022", "2021", "2020", "last year", "months ago"]
        has_old_dates = any(indicator in context_text.lower() for indicator in outdated_indicators)
        if has_old_dates:
            context_text = None

    # Construct the user message with appropriate context
    if context_text:
        if context_text.startswith('[CONTINUING CONVERSATION]'):
            clean_context = context_text.replace('[CONTINUING CONVERSATION] ', '').replace('[CONTINUING CONVERSATION]', '')
            final_user_message = f'CONTINUING CONVERSATION: Previous context: "{clean_context}". User now asked: "{user_message}"'
        else:
            final_user_message = f'CONVERSATION CONTEXT: In response to the tweet "{context_text}", the user asked: "{user_message}"'
    else:
        final_user_message = f'NEW CONVERSATION: User asked: "{user_message}"'

    # --- Construct the Payload ---
    if image_bytes:
        # Image request
        model = Config.VENICE_MODEL_MISTRAL
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
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
            ],
            "venice_parameters": {
                "enable_web_search": "auto",
                "enable_web_citations": True,
                "include_search_results_in_stream": False,
                "include_venice_system_prompt": False  # Use our custom system prompt
            }
        }
    else:
        # Text-only request - ENABLE ACTUAL WEB SEARCH
        model = Config.VENICE_MODEL_WEB
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": expert_prompt},
                {"role": "user", "content": final_user_message}
            ],
            "venice_parameters": {
                "enable_web_search": "auto",  # Use "auto" string instead of True boolean
                "enable_web_citations": True,  # Get citations for verification
                "include_search_results_in_stream": False,  # Get results in final response
                "include_venice_system_prompt": False  # Use our custom system prompt only
            }
        }

    try:
        response = requests.post(VENICE_URL, json=payload, headers=VENICE_HEADERS)
        response.raise_for_status()
        response_data = response.json()
        result = response_data["choices"][0]["message"]["content"].strip()
        return result
    except Exception as e:
        logger.error(f"Error calling Venice API with model {model}: {e}")
        return Config.ERROR_MESSAGE 

def summarize_analysis(analysis_text: str) -> str:
    """Extract key points while maintaining uncensored tone."""
    summarizer_prompt = Config.SUMMARIZER_INTERNAL_PROMPT
    
    payload = {
        "model": Config.VENICE_MODEL_UNCENSORED,
        "messages": [{"role": "user", "content": f"{summarizer_prompt}\n\n---Text to Summarize---\n{analysis_text}"}]
    }

    try:
        response = requests.post(VENICE_URL, json=payload, headers=VENICE_HEADERS)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Error in Step 2 (Summarization): {e}")
        return Config.ERROR_MESSAGE

def craft_tweet(summary_text: str, full_analysis: str = None) -> str:
    """
    STEP 3: Craft the final uncensored tweet.
    Uses venice-uncensored.
    If full_analysis is provided, the model should reconsider and improve the take using that reasoning.
    """
    crafter_prompt = Config.TWEET_CRAFTER_SYSTEM_PROMPT

    user_content = ""
    if full_analysis:
        user_content = (
            "Re-evaluate and improve the take using the analysis below. "
            "Preserve correct facts, strengthen reasoning, and produce the final tweet.\n\n"
            f"--- Full Analysis (Step 1) ---\n{full_analysis}\n\n"
            f"--- Key Points (Step 2) ---\n{summary_text}"
        )
    else:
        user_content = f"Points to rewrite into a tweet:\n{summary_text}"

    payload = {
        "model": Config.VENICE_MODEL_UNCENSORED,
        "messages": [
            {"role": "system", "content": crafter_prompt},
            {"role": "user", "content": user_content}
        ]
    }

    try:
        response = requests.post(VENICE_URL, json=payload, headers=VENICE_HEADERS)
        response.raise_for_status()
        initial_tweet = response.json()["choices"][0]["message"]["content"].strip()

        # Check for banned patterns and retry if found
        banned_patterns = ["Hey there!", "Hi!", "Hello!", "Stay safe", "Be careful", "Be mindful"]
        if any(pattern in initial_tweet for pattern in banned_patterns):
            logger.warning(f"Tweet contains banned patterns, retrying with stricter prompt: {initial_tweet}")
            
            # Retry with stricter prompt using the same model
            strict_prompt = f"""{crafter_prompt}

CRITICAL: The following response contained banned phrases. Rewrite it without ANY greetings, moral advice, or generic endings:
{initial_tweet}

Provide ONLY a direct answer with specific facts."""
            
            retry_payload = {
                "model": Config.VENICE_MODEL_UNCENSORED,
                "messages": [
                    {"role": "system", "content": strict_prompt},
                    {"role": "user", "content": user_content}
                ]
            }
            retry_response = requests.post(VENICE_URL, json=retry_payload, headers=VENICE_HEADERS)
            retry_response.raise_for_status()
            return retry_response.json()["choices"][0]["message"]["content"].strip()

        return initial_tweet
    except Exception as e:
        logger.error(f"Error in Step 3 (Tweet Crafting): {e}")
        return Config.ERROR_MESSAGE 