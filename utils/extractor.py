import re
from PTT import parse_title

def extract_details(caption: str):
    """
    Extracts details using PTT plus custom regex for language and episode range.
    Returns dict with: title, year, quality, lang, print, season, episode
    """

    if not caption or len(caption.strip()) < 2:
        return {}

    try:
        data = parse_title(caption) or {}
    except Exception as e:
        print(f"PTT parse error: {e}")
        data = {}

    # --- Custom Language Extractor ---
    lang_match = re.search(
        r"\[([^\]]*?(?:Hin|Hindi|Tam|Tamil|Tel|Telugu|Eng|English|Kan|Kannada|Mal|Malayalam|Beng|Bengali|Mar|Marathi)[^\]]*?)\]",
        caption,
        re.IGNORECASE
    )
    if lang_match:
        raw_lang = lang_match.group(1)
        langs = re.split(r"[+,/&\-]", raw_lang)
        langs = [x.strip().capitalize() for x in langs if x.strip()]
        lang = ", ".join(sorted(set(langs)))
    else:
        lang = None

    # --- Season Extractor (if missing in PTT) ---
    season = None
    if not data.get("seasons"):
        season_match = re.search(r"(?:S|Season)\s?(\d{1,2})", caption, re.IGNORECASE)
        if season_match:
            season = int(season_match.group(1))
    else:
        season = data.get("seasons")[0]

    # --- Episode Extractor (supports range like E01-34, Ep01 to Ep12) ---
    episode = None
    episode_match = re.search(
        r"(?:E|Ep|Episode)\s*(\d{1,3})(?:\s*(?:-|to)\s*(\d{1,3}))?",
        caption,
        re.IGNORECASE
    )
    if episode_match:
        start_ep = episode_match.group(1)
        end_ep = episode_match.group(2)
        episode = f"{start_ep}-{end_ep}" if end_ep else start_ep

    # --- Other PTT fields ---
    title = data.get("title")
    year = data.get("year")
    quality = data.get("resolution")
    print_type = data.get("quality") or data.get("source")

    return {
        "title": title,
        "year": year,
        "quality": quality,
        "lang": lang,
        "print": print_type,
        "season": season,
        "episode": episode,
    }
