import re
from typing import List, Optional

URL_REGEX = re.compile(r"https?://[^\s)]+", re.IGNORECASE)


def extract_urls_from_entities(entities: Optional[dict]) -> List[str]:
    urls: List[str] = []
    if not entities:
        return urls
    try:
        for u in entities.get('urls', []):
            expanded = u.get('unwound_url') or u.get('expanded_url') or u.get('url')
            if expanded and isinstance(expanded, str):
                urls.append(expanded)
    except Exception:
        pass
    return list(dict.fromkeys(urls))


def extract_urls_from_text(text: Optional[str]) -> List[str]:
    if not text:
        return []
    found = URL_REGEX.findall(text)
    return list(dict.fromkeys(found)) 