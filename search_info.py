# search_info.py

import re
from pyrogram import enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from html import escape
from db import cache_col

# In-memory cache for fast access
DATABASE = {}

async def send_result_message(client, message, query, movies, page, result_message_id=None):
    total_results = len(movies)
    results_per_page = 10

    if total_results <= results_per_page:
        movies_page = movies
        reply_markup = None
    else:
        start_index = (page - 1) * results_per_page
        end_index = page * results_per_page
        movies_page = movies[start_index:end_index]
        reply_markup = generate_inline_keyboard(query, total_results, page)

    result_message = generate_result_message(query, movies_page, page)

    if result_message_id:
        await client.edit_message_text(
            chat_id=message.chat.id,
            message_id=result_message_id,
            text=result_message,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=reply_markup
        )
    else:
        sent_message = await message.reply_text(
            result_message,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=reply_markup
        )
        result_message_id = sent_message.id

    # Cache in memory
    DATABASE[query] = {
        'message_id': result_message_id,
        'movies': movies,
        'page': page
    }

    # Save in MongoDB
    await cache_col.update_one(
        {"query": query},
        {"$set": {"movies": movies, "page": page, "message_id": result_message_id}},
        upsert=True
    )


def generate_inline_keyboard(query, total_results, current_page):
    buttons = []
    if total_results > current_page * 10:
        buttons.append(InlineKeyboardButton("Next Page", callback_data=f"next_page:{query}:{current_page + 1}"))
    if current_page > 1:
        buttons.append(InlineKeyboardButton("Previous Page", callback_data=f"previous_page:{query}:{current_page - 1}"))
    return InlineKeyboardMarkup([buttons]) if buttons else None


def generate_result_message(query, movies, page):
    start_number = (page - 1) * 10 + 1
    result_message = f"🎬 <b>Results for:</b> <code>{escape(query)}</code>\n\n"
    for i, movie_text in enumerate(movies, start=start_number):
        result_message += f"{i}. {movie_text}\n\n"
    return result_message


def extract_movie_details(caption):
    name_patterns = [
        r"^([^.]*?)\s\d{4}",
        r"^([^.]*?)\s(\(\d{4}\))",
        r"^([^.]*?)\s\d{3,4}p",
        r"^([^.]*?)(?=\s\d{4})",
    ]
    year_patterns = [
        r"\((\d{4})\)",
        r"(\d{4})",
        r"(19\d{2}|20\d{2})",
    ]
    quality_patterns = [
        r"\d{3,4}p",
        r"\b(4|8|10)K\b",
        r"\b(FHD|HD|SD)\b",
    ]

    movie_name, year, quality = "Unknown", "Unknown", "Unknown"

    for name_pattern in name_patterns:
        if match := re.search(name_pattern, caption):
            movie_name = match.group(1).replace(".", "").strip()
            break

    for year_pattern in year_patterns:
        if match := re.search(year_pattern, caption):
            year = match.group(1)
            break

    for quality_pattern in quality_patterns:
        if match := re.search(quality_pattern, caption):
            quality = match.group()
            break

    return movie_name, year, quality
