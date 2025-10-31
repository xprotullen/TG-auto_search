# search_info.py
# message generation, pagination UI, and caption parsing utilities
import re
from html import escape
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# in-memory storage for active queries and pagination
# structure: {query_key: {"movies": [...], "message_id": int, "chat_id": int}}
ACTIVE_QUERIES = {}

def generate_result_message(query, movies, page, page_size=10):
    start_index = (page - 1) * page_size + 1
    result_message = f"यहाँ परिणाम हैं — <b>{escape(query)}</b>:\n\n"
    for i, movie_text in enumerate(movies, start=start_index):
        result_message += f"{i}. {movie_text}\n\n"
    return result_message

def generate_inline_keyboard(query_key, total_results, current_page, page_size=10):
    buttons = []
    # next
    if total_results > current_page * page_size:
        buttons.append(
            InlineKeyboardButton(text="⏭ Next", callback_data=f"next:{query_key}:{current_page+1}")
        )
    # prev
    if current_page > 1:
        buttons.append(
            InlineKeyboardButton(text="⏮ Prev", callback_data=f"prev:{query_key}:{current_page-1}")
        )
    if buttons:
        return InlineKeyboardMarkup([buttons])
    return None

def normalize_text_for_search(s: str) -> str:
    # remove repeated spaces and dots etc
    if not s:
        return ""
    s = re.sub(r"[_\-\.\+]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def extract_movie_details(caption: str):
    """
    Simple extractor - returns (movie_name, year, quality)
    You can extend this with PTT or tmdb parsing later.
    """
    if not caption:
        return ("Unknown", "Unknown", "Unknown")
    text = caption

    # name: everything before year or quality or first dot group
    name_match = re.search(r"^(.+?)(?:\s\(|\s\d{4}\b|\s\d{3,4}p\b|$)", text)
    movie_name = name_match.group(1).replace(".", " ").strip() if name_match else text.split("\n")[0]

    # year
    year_match = re.search(r"\((\d{4})\)|\b(19|20)\d{2}\b", text)
    year = year_match.group(1) if year_match else "Unknown"

    # quality
    quality_match = re.search(r"(\d{3,4}p|4K|8K|10K|FHD|HD|SD)", text, flags=re.IGNORECASE)
    quality = quality_match.group(1) if quality_match else "Unknown"

    return (movie_name.strip(), year, quality)
