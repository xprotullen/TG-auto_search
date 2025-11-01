import re

def extract_details(caption: str):
    """
    Extract movie/series info from caption text.
    Returns a dictionary with structured details.
    """
    if not caption:
        return {}

    text = caption.replace("\n", " ").strip()

    # 🎬 Title
    title_match = re.search(r"^([A-Za-z0-9:’' .\-]+)", text)
    title = title_match.group(1).strip() if title_match else "Unknown"

    # 📅 Year
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    year = int(year_match.group()) if year_match else None

    # 📺 Quality
    quality_match = re.search(r"\b(480p|720p|1080p|2160p|4K)\b", text, re.I)
    quality = quality_match.group(1).lower() if quality_match else None

    # 🧾 Print Type
    print_match = re.search(r"\b(WEB[- ]?DL|BluRay|HDRip|WEB[- ]?Rip|DVDScr|CAMRip)\b", text, re.I)
    print_type = print_match.group(1) if print_match else None

    # 🗣️ Language(s)
    langs = re.findall(
        r"\b(Hindi|English|Tamil|Telugu|Malayalam|Kannada|Bengali|Marathi|Dual Audio)\b",
        text, re.I
    )
    languages = list(set(lang.capitalize() for lang in langs)) if langs else None

    # 🎞️ Season
    season_match = re.search(r"[Ss]eason\s?(\d+)|S(\d+)", text)
    season = int(season_match.group(1) or season_match.group(2)) if season_match else None

    # 📺 Episode (single or range)
    ep_match = re.search(r"[Ee]pisode[s]?\s?(\d+)(?:[-–](\d+))?", text)
    if ep_match:
        start = int(ep_match.group(1))
        end = int(ep_match.group(2)) if ep_match.group(2) else start
        episode = [start, end] if end != start else start
    else:
        episode = None

    return {
        "title": title,
        "year": year,
        "quality": quality,
        "language": languages,
        "print": print_type,
        "season": season,
        "episode": episode,
        "caption": caption
    }
