import re

def extract_details(caption: str):
    """
    Extracts movie or series details from caption text.

    Example caption:
    "Mirage (2025) UNCUT WebRip [Hindi ORG] 480p"
    """
    if not caption:
        return {}

    text = caption.strip()

    # Title (before first '(' or '[')
    title_match = re.match(r"^(.*?)(?:\s*\(|\s*\[|$)", text)
    title = title_match.group(1).strip() if title_match else None

    # Year
    year_match = re.search(r"\((\d{4})\)", text)
    year = year_match.group(1) if year_match else None

    # Quality (480p, 720p, 1080p, 2160p, 4K)
    quality_match = re.search(r"(480p|720p|1080p|2160p|4K)", text, re.IGNORECASE)
    quality = quality_match.group(1) if quality_match else None

    # Language (inside square brackets)
    lang_match = re.search(r"\[(.*?)\]", text)
    lang = lang_match.group(1).strip() if lang_match else None

    # Print type (WebRip, HDRip, BluRay, etc.)
    print_match = re.search(r"(WebRip|HDRip|BluRay|DVDRip|Web-DL)", text, re.IGNORECASE)
    print_type = print_match.group(1) if print_match else None

    # Season / Episode detection (like S01E05 or Season 2 Episode 10)
    season_match = re.search(r"[Ss](\d{1,2})", text)
    episode_match = re.search(r"[Ee](\d{1,3})", text)
    season = season_match.group(1) if season_match else None
    episode = episode_match.group(1) if episode_match else None

    return {
        "title": title,
        "year": year,
        "quality": quality,
        "lang": lang,  # ✅ renamed from "language"
        "print": print_type,
        "season": season,
        "episode": episode
    }
