import math
import time
import hashlib
from html import escape
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from utils.database import get_movies_async as get_movies


# ---------------- CONFIG ---------------- #
RESULTS_PER_PAGE = 10
CACHE_LIMIT = 50          # Max cached searches
CACHE_TTL = 600           # 10 minutes expiration

# Cache structure:
# key (str) → {
#   "chat_id": int,
#   "user_id": int,
#   "query": str,
#   "data": dict,
#   "page": int,
#   "time": float,
#   "message_id": int
# }
CACHE = {}


# ---------------- HELPERS ---------------- #
def _make_key(chat_id: int, user_id: int, query: str) -> str:
    """Create a short unique key for this user's search."""
    raw = f"{chat_id}:{user_id}:{query}"
    return hashlib.md5(raw.encode()).hexdigest()[:10]


def _cleanup_cache():
    """Remove old or excess cache entries."""
    now = time.time()

    # Expire old ones
    for k, v in list(CACHE.items()):
        if now - v["time"] > CACHE_TTL:
            CACHE.pop(k, None)

    # Keep size under limit
    while len(CACHE) > CACHE_LIMIT:
        CACHE.pop(next(iter(CACHE)))


# ---------------- SEARCH HANDLER ---------------- #
@Client.on_message(filters.group & filters.text)
async def search_movie(client, message):
    query = message.text.strip()
    chat_id = int(message.chat.id)
    user_id = message.from_user.id

    # Ignore bot commands or empty text
    if not query or query.startswith(("/", ".", "!", ",")):
        return

    # Fetch results from DB
    search_data = await get_movies(chat_id, query, page=1, limit=RESULTS_PER_PAGE)
    movies = search_data["results"]
    total = search_data["total"]
    pages = search_data["pages"]

    if not movies:
        return await message.reply_text(f"No results found for <code>{escape(query)}</code>.")

    # Clean old cache
    _cleanup_cache()

    key = _make_key(chat_id, user_id, query)
    CACHE[key] = {
        "chat_id": chat_id,
        "user_id": user_id,
        "query": query,
        "data": search_data,
        "page": 1,
        "time": time.time(),
    }

    sent = await send_results(
        message, query, chat_id, 1, movies, total, pages, key, edit=False
    )

    CACHE[key]["message_id"] = sent.id


# ---------------- RENDER RESULTS ---------------- #
async def send_results(message, query, chat_id, page, movies, total, pages, key, edit=False):
    """Send or edit paginated movie search results."""
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

        parts = [title]
        if year:
            parts.append(f"({year})")
        if quality:
            parts.append(quality)
        if codec:
            parts.append(codec)
        if print_type:
            parts.append(print_type)
        if lang:
            parts.append(lang)
        if season:
            parts.append(f"S{str(season).zfill(2)}")
        if episode:
            parts.append(f"E{str(episode).zfill(2)}")

        caption = " ".join(str(p) for p in parts if p)
        caption = escape(caption[:150])  # truncate to avoid message limit

        text += f"{i}. <b>{caption}</b>\n"
        if link:
            text += f"<b>Link</b>: {escape(link)}\n\n"

    # Pagination buttons
    buttons = []
    row = []
    if page > 1:
        row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page|{key}|{page-1}"))
    if page < pages:
        row.append(InlineKeyboardButton("Next ➡️", callback_data=f"page|{key}|{page+1}"))
    if row:
        buttons.append(row)

    markup = InlineKeyboardMarkup(buttons) if buttons else None

    if edit:
        return await message.edit_text(
            text,
            reply_markup=markup,
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML,
        )
    else:
        return await message.reply_text(
            text,
            reply_markup=markup,
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML,
        )


# ---------------- PAGINATION CALLBACK ---------------- #
@Client.on_callback_query(filters.regex(r"^page\|"))
async def pagination_handler(client, query: CallbackQuery):
    try:
        _, key, page = query.data.split("|", 2)
        page = int(page)
    except Exception:
        return await query.answer("⚠️ Invalid data.", show_alert=True)

    cached = CACHE.get(key)
    if not cached:
        return await query.answer("⚠️ Data expired, please search again.", show_alert=True)

    # Restrict to same user
    if query.from_user.id != cached["user_id"]:
        return await query.answer("❌ You didn’t request this search!", show_alert=True)

    chat_id = cached["chat_id"]
    search_query = cached["query"]

    # Refresh DB for new page (ensures updated data)
    data = await get_movies(chat_id, search_query, page=page, limit=RESULTS_PER_PAGE)
    movies = data["results"]
    total = data["total"]
    pages = data["pages"]

    if not movies:
        return await query.answer("⚠️ No more results.", show_alert=True)

    cached["data"] = data
    cached["page"] = page
    cached["time"] = time.time()

    await query.answer()
    await send_results(
        query.message, search_query, chat_id, page, movies, total, pages, key, edit=True
    )
