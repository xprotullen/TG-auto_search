import math
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from utils.database import get_movies
from html import escape

RESULTS_PER_PAGE = 10
CACHE = {}

@Client.on_message(filters.group & filters.text)
async def search_movie(client, message):
    query = message.text.strip()
    chat_id = str(message.chat.id)

    movies = get_movies(chat_id, query)
    if not movies:
        return

    CACHE[(chat_id, query)] = movies
    await send_results(client, message, query, chat_id, 1, movies)

async def send_results(client, message, query, chat_id, page, movies):
    total_pages = math.ceil(len(movies) / RESULTS_PER_PAGE)
    start = (page - 1) * RESULTS_PER_PAGE
    end = start + RESULTS_PER_PAGE
    movie_slice = movies[start:end]

    text = f"🎬 <b>Results for:</b> <code>{escape(query)}</code>\n\n"
    for i, movie in enumerate(movie_slice, start=start + 1):
        text += f"{i}. <b>{escape(movie['caption'][:50])}</b>\n🔗 [Link]({movie['link']})\n\n"

    keyboard = []
    if total_pages > 1:
        row = []
        if page > 1:
            row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page:{chat_id}:{query}:{page-1}"))
        if page < total_pages:
            row.append(InlineKeyboardButton("Next ➡️", callback_data=f"page:{chat_id}:{query}:{page+1}"))
        keyboard.append(row)

    await message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
        disable_web_page_preview=True,
        parse_mode=enums.ParseMode.HTML
    )

@Client.on_callback_query(filters.regex(r"^page:"))
async def pagination_handler(client, query: CallbackQuery):
    _, chat_id, text, page = query.data.split(":")
    page = int(page)
    movies = CACHE.get((chat_id, text))
    if not movies:
        return await query.answer("⚠️ Data expired.", show_alert=True)
    
    await query.message.delete()
    await send_results(client, query.message, text, chat_id, page, movies)
