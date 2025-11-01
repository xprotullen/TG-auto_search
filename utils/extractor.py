import re
from PTT import parse_title

def extract_details(caption: str):
    """
    Extracts details using PTT except language (custom regex).
    Returns only: title, year, quality, lang, print, season, episode
    """

    if not caption or len(caption.strip()) < 2:
        return {}

    try:
        # Use PTT for main parsing
        data = parse_title(caption)
    except Exception as e:
        print(f"PTT parse error: {e}")
        data = {}

    # --- Custom Language Extractor ---
    lang_match = re.search(r"\[([^\]]*?(?:Hin|Hindi|Tam|Tamil|Tel|Telugu|Eng|English|Kan|Kannada|Mal|Malayalam|Beng|Bengali|Mar|Marathi)[^\]]*?)\]", caption, re.IGNORECASE)
    if lang_match:
        raw_lang = lang_match.group(1)
        # Clean and split multi-language entries
        langs = re.split(r"[+,/&\-]", raw_lang)
        langs = [x.strip().capitalize() for x in langs if x.strip()]
        lang = ", ".join(sorted(set(langs)))
    else:
        lang = None

    # --- Extract other fields from PTT ---
    title = data.get("title")
    year = data.get("year")
    quality = data.get("resolution")
    print_type = data.get("quality") or data.get("source")
    season = data.get("seasons")[0] if data.get("seasons") else None
    episode = data.get("episodes")[0] if data.get("episodes") else None

    return {
        "title": title,
        "year": year,
        "quality": quality,
        "lang": lang,
        "print": print_type,
        "season": season,
        "episode": episode
    } 
