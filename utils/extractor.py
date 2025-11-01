import re
from PTT import parse_title

def extract_details(caption: str):
    """
    Extracts details from torrent title using Parsett (PTT) + custom regex.
    Supports: episode ranges (E01-12), 'Complete' detection, codec, etc.
    Returns: title, year, quality, lang, print, season, episode, codec
    """

    if not caption or len(caption.strip()) < 2:
        return {}

    # --- Parse via PTT ---
    try:
        data = parse_title(caption, translate_languages=True) or {}
    except Exception as e:
        print(f"[PTT Error] {e}")
        data = {}

    # --- Language Extractor ---
    lang_match = re.search(
        r"\[([^\]]*?(?:Hin|Hindi|Tam|Tamil|Tel|Telugu|Eng|English|Kan|Kannada|Mal|Malayalam|Beng|Bengali|Mar|Marathi)[^\]]*?)\]",
        caption,
        re.IGNORECASE
    )
    lang = None
    if lang_match:
        raw_lang = lang_match.group(1)
        langs = re.split(r"[+,/&\-]", raw_lang)
        langs = [x.strip().capitalize() for x in langs if x.strip()]
        lang = ", ".join(sorted(set(langs)))

    # --- Season Detection ---
    seasons = data.get("seasons", [])
    season = seasons[0] if seasons else None

    # --- Episode Detection (supports range + Complete) ---
    episode = None
    episodes = data.get("episodes", [])
    caption_lower = caption.lower()

    if "complete" in caption_lower:
        episode = "Complete"
    elif episodes:
        if len(episodes) > 1:
            episode = f"{episodes[0]}-{episodes[-1]}"
        else:
            episode = str(episodes[0])
    else:
        # Matches E01, Ep12, Episode 3-10, etc.
        ep_match = re.search(
            r"(?:E|Ep|Episode)\s*(\d{1,3})(?:\s*(?:-|to)\s*(\d{1,3}))?",
            caption,
            re.IGNORECASE,
        )
        if ep_match:
            start, end = ep_match.groups()
            episode = f"{start}-{end}" if end else start

    # --- Collect Other Details ---
    title = data.get("title")
    year = data.get("year")
    quality = data.get("resolution")
    codec = data.get("codec")
    print_type = data.get("quality") or data.get("source")

    return {
        "title": title,
        "year": year,
        "quality": quality,
        "lang": lang,
        "print": print_type,
        "season": season,
        "episode": episode,
        "codec": codec,
    }
