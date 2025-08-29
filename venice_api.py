import base64
import requests
import logging
from config import Config
import re

logger = logging.getLogger(__name__)

# Module-level constants to avoid recreation
VENICE_URL = Config.VENICE_URL
VENICE_HEADERS = {
    "Authorization": f"Bearer {Config.VENICE_API_KEY}",
    "Content-Type": "application/json"
}


def _strip_ref_tags(text: str) -> str:
    try:
        return re.sub(r"\[REF\].*?\[/REF\]", "", text, flags=re.DOTALL).strip()
    except Exception:
        return text


def _get_tweet_char_limit() -> int:
    try:
        return Config.X_PREMIUM_CHAR_LIMIT if Config.X_PREMIUM_ENABLED else Config.STANDARD_CHAR_LIMIT
    except Exception:
        return Config.STANDARD_CHAR_LIMIT


def _extract_final_reply_and_notes(text: str):
    try:
        final_match = re.search(r"\[FINAL_REPLY\](.*?)\[/FINAL_REPLY\]", text, flags=re.DOTALL | re.IGNORECASE)
        notes_match = re.search(r"\[NOTES\](.*?)\[/NOTES\]", text, flags=re.DOTALL | re.IGNORECASE)
        final_reply = final_match.group(1).strip() if final_match else None
        notes = notes_match.group(1).strip() if notes_match else None
        return final_reply, notes
    except Exception:
        return None, None


def get_expert_analysis(user_message: str, image_bytes: bytes = None, image_url: str = None, context_text: str = None, urls: list = None, article_texts: list = None) -> str:
    """
    STEP 1: Get focused, honest analysis using a single model for cost efficiency.
    Now returns a concise, tweet-ready answer directly.
    """
    expert_prompt = Config.EXPERT_SYSTEM_PROMPT

    # Keep all context - let the AI model decide what's relevant

    # Construct the user message with appropriate context
    if context_text:
        if context_text.startswith('[CONTINUING CONVERSATION]'):
            clean_context = context_text.replace('[CONTINUING CONVERSATION] ', '').replace('[CONTINUING CONVERSATION]', '')
            final_user_message = f'CONTINUING CONVERSATION: Previous context: "{clean_context}". User now asked: "{user_message}"'
        else:
            final_user_message = f'CONVERSATION CONTEXT: In response to the tweet "{context_text}", the user asked: "{user_message}"'
    else:
        final_user_message = f'NEW CONVERSATION: User asked: "{user_message}"'

    urls = urls or []
    article_texts = article_texts or []

    if urls:
        joined_urls = "\n".join(urls)
        final_user_message += f"\n\nLINKS TO USE (open and summarize if relevant):\n{joined_urls}"

    if article_texts:
        # Provide extracted article content as context for summarization
        joined_articles = "\n\n".join(article_texts)
        final_user_message += f"\n\nEXTRACTED ARTICLE CONTENT (use as the primary source if links are blocked):\n{joined_articles}"

    # Instruct the expert to produce a final tweet-ready reply block
    char_limit = _get_tweet_char_limit()
    final_user_message += (
        f"\n\nOUTPUT FORMAT (STRICT):\n"
        f"[FINAL_REPLY]\n"
        f"<tweet-ready reply within {char_limit} characters; no greetings, no moral advice, no hashtags, no generic endings, no @mentions unless explicitly present in the user's text, no markdown formatting like **bold** or numbered lists>\n"
        f"[/FINAL_REPLY]\n\n"
        f"[NOTES]\n"
        f"(optional) up to 5 bullets with key facts/citations used.\n"
        f"[/NOTES]\n"
    )

    # --- Construct the Payload ---
    if image_bytes or image_url:
        # Image request - Use Mistral for vision capabilities with web search
        model = Config.VENICE_MODEL_MISTRAL
        image_base64 = base64.b64encode(image_bytes).decode('utf-8') if image_bytes else None
        
        message_text = final_user_message.strip() or "What's in this image?"
        
        # Prefer direct URL if available; otherwise, embed base64
        image_content = (
            {"type": "image_url", "image_url": {"url": image_url}}
            if image_url
            else {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
        )

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": expert_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": message_text},
                        image_content
                    ]
                }
            ],
            "venice_parameters": {
                "enable_web_search": "auto",
                "enable_web_citations": False,
                "include_search_results_in_stream": False,
                "include_venice_system_prompt": False,
                "web_search_urls": urls if urls else None
            }
        }
        if payload["venice_parameters"].get("web_search_urls") is None:
            del payload["venice_parameters"]["web_search_urls"]
    else:
        # Text-only request - Use Venice Uncensored with web search
        model = Config.VENICE_MODEL_UNCENSORED
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": expert_prompt},
                {"role": "user", "content": final_user_message}
            ],
            "venice_parameters": {
                "enable_web_search": "auto",
                "enable_web_citations": False,
                "include_search_results_in_stream": False,
                "include_venice_system_prompt": False,
                "web_search_urls": urls if urls else None
            }
        }
        if payload["venice_parameters"].get("web_search_urls") is None:
            del payload["venice_parameters"]["web_search_urls"]

    try:
        response = requests.post(VENICE_URL, json=payload, headers=VENICE_HEADERS)
        response.raise_for_status()
        response_data = response.json()
        result = response_data["choices"][0]["message"]["content"].strip()
        return _strip_ref_tags(result)
    except Exception as e:
        logger.error(f"Error calling Venice API with model {model}: {e}")
        return Config.ERROR_MESSAGE 


# Removed summarizer; the tweet will be crafted directly from the concise expert answer.


def craft_tweet(summary_text: str, full_analysis: str = None, use_mistral: bool = False) -> str:
    """
    STEP 3: Craft the final uncensored tweet.
    Uses venice-uncensored by default.
    If a [FINAL_REPLY] is provided in summary_text, use it directly if it passes checks; otherwise rewrite.
    If full_analysis is provided, the model should reconsider and improve the take using that reasoning.
    If use_mistral is True (e.g., image tweets), use the Mistral vision-capable model.
    """
    crafter_prompt = Config.TWEET_CRAFTER_SYSTEM_PROMPT
    char_limit = _get_tweet_char_limit()

    # Try to extract candidate tweet from [FINAL_REPLY]
    candidate_tweet, notes = _extract_final_reply_and_notes(summary_text or "")
    banned_patterns = ["Hey there!", "Hi!", "Hello!", "Stay safe", "Be careful", "Be mindful"]

    if candidate_tweet:
        candidate_tweet = _strip_ref_tags(candidate_tweet)
        is_banned = any(pattern in candidate_tweet for pattern in banned_patterns)
        if not is_banned and len(candidate_tweet) <= char_limit:
            return candidate_tweet.strip()
        # Needs rewrite: banned phrases or too long
        strict_prompt = f"""{crafter_prompt}

CRITICAL: Rewrite the following into a compliant tweet under {char_limit} characters. No greetings, no hashtags, no moral advice, no generic endings. Keep specifics.

Original:
{candidate_tweet}

Optional notes to preserve key facts:
{notes or ''}
"""
        retry_payload = {
            "model": (Config.VENICE_MODEL_MISTRAL if use_mistral else Config.VENICE_MODEL_UNCENSORED),
            "messages": [
                {"role": "system", "content": strict_prompt},
                {"role": "user", "content": "Rewrite the 'Original' into the final tweet now."}
            ],
            "venice_parameters": {
                "enable_web_search": "auto",
                "enable_web_citations": False,
                "include_search_results_in_stream": False,
                "include_venice_system_prompt": False
            }
        }
        try:
            retry_response = requests.post(VENICE_URL, json=retry_payload, headers=VENICE_HEADERS)
            retry_response.raise_for_status()
            return _strip_ref_tags(retry_response.json()["choices"][0]["message"]["content"].strip())
        except Exception as e:
            logger.error(f"Error rewriting FINAL_REPLY: {e}")
            return Config.ERROR_MESSAGE

    # Fallback: no FINAL_REPLY present—use model to craft from provided points/analysis
    user_content = ""
    if full_analysis:
        user_content = (
            "Re-evaluate and improve the take using the analysis below. "
            "Preserve correct facts, strengthen reasoning, and produce the final tweet.\n\n"
            f"--- Full Analysis (Step 1) ---\n{full_analysis}\n\n"
            f"--- Key Points ---\n{summary_text}"
        )
    else:
        user_content = f"Points to rewrite into a tweet:\n{summary_text}"

    # Select model based on whether we need vision-capable reply
    model = Config.VENICE_MODEL_MISTRAL if use_mistral else Config.VENICE_MODEL_UNCENSORED

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": crafter_prompt},
            {"role": "user", "content": user_content}
        ],
        "venice_parameters": {
            "enable_web_search": "auto",
            "enable_web_citations": False,
            "include_search_results_in_stream": False,
            "include_venice_system_prompt": False
        }
    }

    try:
        response = requests.post(VENICE_URL, json=payload, headers=VENICE_HEADERS)
        response.raise_for_status()
        initial_tweet = response.json()["choices"][0]["message"]["content"].strip()
        initial_tweet = _strip_ref_tags(initial_tweet)

        # Check for banned patterns and retry if found
        if any(pattern in initial_tweet for pattern in banned_patterns) or len(initial_tweet) > char_limit:
            logger.warning(f"Tweet violates style/length, retrying with stricter prompt: {initial_tweet}")
            
            strict_prompt = f"""{crafter_prompt}

CRITICAL: The following response contained banned phrases or exceeded {char_limit} chars. Rewrite without greetings, moral advice, hashtags, or generic endings. Keep specifics and stay under limit:
{initial_tweet}
"""
            retry_payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": strict_prompt},
                    {"role": "user", "content": user_content}
                ],
                "venice_parameters": {
                    "enable_web_search": "auto",
                    "enable_web_citations": False,
                    "include_search_results_in_stream": False,
                    "include_venice_system_prompt": False
                }
            }
            retry_response = requests.post(VENICE_URL, json=retry_payload, headers=VENICE_HEADERS)
            retry_response.raise_for_status()
            return _strip_ref_tags(retry_response.json()["choices"][0]["message"]["content"].strip())

        return _strip_ref_tags(initial_tweet)
    except Exception as e:
        logger.error(f"Error in Step 3 (Tweet Crafting): {e}")
        return Config.ERROR_MESSAGE 