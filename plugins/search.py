import json
import hashlib
from html import escape
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from utils.database import get_movies_async as get_movies
import redis.asyncio as redis

# ---------------- REDIS CONFIG ---------------- #
rdb = redis.Redis(
    host="redis-12097.c74.us-east-1-4.ec2.redns.redis-cloud.com",
    port=12097,
    username="default",
    password="w6fd6o5i6YqjCaZ7XBcmQ1PJwGC39RZf",
    decode_responses=True
)

CACHE_TTL = 3600  # 1 hour
RESULTS_PER_PAGE = 10


def make_page_key(chat_id: int, query: str, page: int) -> str:
    """Unique key for Redis cache"""
    raw = f"{chat_id}:{query}:{page}"
    return "movie_cache:" + hashlib.md5(raw.encode()).hexdigest()


# ---------------- CACHE HELPERS ---------------- #
async def get_cached_page(chat_id, query, page):
    key = make_page_key(chat_id, query, page)
    raw = await rdb.get(key)
    if not raw:
        return None
    return json.loads(raw)


async def set_cached_page(chat_id, query, page, data):
    key = make_page_key(chat_id, query, page)
    await rdb.setex(key, CACHE_TTL, json.dumps(data))


# ---------------- MAIN SEARCH ---------------- #
@Client.on_message(filters.group & filters.text)
async def search_movie(client, message):
    query = message.text.strip()
    chat_id = int(message.chat.id)

    if not query or query.startswith(("/", ".", "!", ",")):
        return

    # 🔍 Try cache first (page 1)
    cached = await get_cached_page(chat_id, query, 1)
    if cached:
        movies, total, pages = (
            cached["results"], cached["total"], cached["pages"]
        )
    else:
        # ❌ Not cached → Fetch from DB
        search_data = await get_movies(chat_id, query, page=1, limit=RESULTS_PER_PAGE)
        movies, total, pages = (
            search_data["results"], search_data["total"], search_data["pages"]
        )
        # Save to Redis for next time
        await set_cached_page(chat_id, query, 1, search_data)

    if not movies:
        return

    await send_results(message, query, chat_id, 1, movies, total, pages)


# ---------------- SEND RESULTS ---------------- #
async def send_results(message, query, chat_id, page, movies, total, pages, edit=False):
    text = f"<b>Results for:</b> <code>{escape(query)}</code>\n"
    text += f"📄 Page {page}/{pages} — Total: {total}\n\n"

    for i, movie in enumerate(movies, start=(page - 1) * RESULTS_PER_PAGE + 1):
        title = movie.get("title") or "Unknown"
        year = movie.get("year")
        quality = movie.get("quality")
        print_type = movie.get("print")
        lang = movie.get("lang")
        season = movie.get("season")
        episode = movie.get("episode")
        codec = movie.get("codec")
        link = movie.get("link")

        caption_parts = [title]
        if year:
            caption_parts.append(f"({year})")
        if quality:
            caption_parts.append(quality)
        if codec:
            caption_parts.append(codec)
        if print_type:
            caption_parts.append(print_type)
        if lang:
            caption_parts.append(lang)
        if season:
            caption_parts.append(f"S{str(season).zfill(2)}")
        if episode:
            caption_parts.append(f"E{str(episode).zfill(2)}")

        caption = " ".join(str(p) for p in caption_parts if p)
        text += f"{i}. <b>{escape(caption)}</b>\n"
        if link:
            text += f"<b>Link:</b> {link}\n\n"

    # Pagination buttons
    buttons = []
    row = []
    if page > 1:
        row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page|{chat_id}|{query}|{page-1}"))
    if page < pages:
        row.append(InlineKeyboardButton("Next ➡️", callback_data=f"page|{chat_id}|{query}|{page+1}"))
    if row:
        buttons.append(row)

    markup = InlineKeyboardMarkup(buttons) if buttons else None

    if edit:
        return await message.edit_text(
            text,
            reply_markup=markup,
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML
        )
    else:
        return await message.reply_text(
            text,
            reply_markup=markup,
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML
        )


# ---------------- PAGINATION HANDLER ---------------- #
@Client.on_callback_query(filters.regex(r"^page\|"))
async def pagination_handler(client, query: CallbackQuery):
    try:
        _, chat_id, search_query, page = query.data.split("|", 3)
        chat_id = int(chat_id)
        page = int(page)
    except Exception:
        return await query.answer("⚠️ Invalid data.", show_alert=True)

    # 🔍 Try Redis cache first
    cached = await get_cached_page(chat_id, search_query, page)
    if cached:
        movies, total, pages = (
            cached["results"], cached["total"], cached["pages"]
        )
    else:
        # ❌ Not cached → Fetch from MongoDB
        data = await get_movies(chat_id, search_query, page=page, limit=RESULTS_PER_PAGE)
        movies, total, pages = data["results"], data["total"], data["pages"]
        await set_cached_page(chat_id, search_query, page, data)

    if not movies:
        return await query.answer("⚠️ No more results.", show_alert=True)

    await query.answer()
    await send_results(query.message, search_query, chat_id, page, movies, total, pages, edit=True)
