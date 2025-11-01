import math
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

CACHE_TTL = 600  # 10 minutes
RESULTS_PER_PAGE = 10


# ---------------- REDIS CACHE HELPERS ---------------- #
def make_cache_key(chat_id: int, query: str) -> str:
    raw = f"{chat_id}:{query}"
    return hashlib.md5(raw.encode()).hexdigest()


async def cache_set(chat_id, user_id, query, data, message_id=None):
    key = make_cache_key(chat_id, query)
    value = json.dumps({
        "user_id": user_id,
        "data": data,
        "message_id": message_id
    })
    await rdb.setex(key, CACHE_TTL, value)
    return key


async def cache_get(chat_id, query):
    key = make_cache_key(chat_id, query)
    raw = await rdb.get(key)
    if not raw:
        return None
    return json.loads(raw)


async def cache_update_message_id(chat_id, query, message_id):
    cached = await cache_get(chat_id, query)
    if cached:
        cached["message_id"] = message_id
        await cache_set(chat_id, cached["user_id"], query, cached["data"], message_id)


# ---------------- MAIN SEARCH HANDLER ---------------- #
@Client.on_message(filters.group & filters.text)
async def search_movie(client, message):
    query = message.text.strip()
    chat_id = int(message.chat.id)

    if not query or query.startswith(("/", ".", "!", ",")):
        return

    # Get results from DB
    search_data = await get_movies(chat_id, query, page=1, limit=RESULTS_PER_PAGE)
    movies = search_data["results"]
    total = search_data["total"]
    pages = search_data["pages"]

    if not movies:
        return

    # Save to Redis cache
    await cache_set(chat_id, message.from_user.id, query, search_data)

    sent = await send_results(
        message, query, chat_id, 1, movies, total, pages
    )

    await cache_update_message_id(chat_id, query, sent.id)


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

    cached = await cache_get(chat_id, search_query)
    if not cached:
        return await query.answer("⚠️ Data expired, please search again.", show_alert=True)

    # Restrict to same user
    if query.from_user.id != cached["user_id"]:
        return await query.answer("❌ You didn’t request this search!", show_alert=True)

    # Get new page
    data = await get_movies(chat_id, search_query, page=page, limit=RESULTS_PER_PAGE)
    movies = data["results"]
    total = data["total"]
    pages = data["pages"]

    if not movies:
        return await query.answer("⚠️ No more results.", show_alert=True)

    await query.answer()
    await send_results(query.message, search_query, chat_id, page, movies, total, pages, edit=True)
