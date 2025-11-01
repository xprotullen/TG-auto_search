import json
import hashlib
from html import escape
from bson import ObjectId
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

CACHE_TTL = 3600         # Cache for 1 hour
RESULTS_PER_PAGE = 10    # Results per page
MAX_RESULTS = 200        # Max results stored per search


# ---------------- JSON ENCODER (Fix ObjectId) ---------------- #
class JSONEncoder(json.JSONEncoder):
    """Make ObjectId JSON serializable."""
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        return super().default(o)


# ---------------- UTILITIES ---------------- #
def make_cache_key(chat_id: int, query: str) -> str:
    """Unique Redis key for user's query."""
    raw = f"{chat_id}:{query.strip().lower()}"
    return "movie_search:" + hashlib.md5(raw.encode()).hexdigest()


async def get_cached_results(chat_id: int, query: str):
    key = make_cache_key(chat_id, query)
    raw = await rdb.get(key)
    return json.loads(raw) if raw else None


async def set_cached_results(chat_id: int, query: str, results: list):
    """Cache search results in Redis with JSON-safe encoding."""
    key = make_cache_key(chat_id, query)
    payload = json.dumps({"results": results, "total": len(results)}, cls=JSONEncoder)
    await rdb.setex(key, CACHE_TTL, payload)


# ---------------- SEARCH HANDLER ---------------- #
@Client.on_message(filters.group & filters.text)
async def search_movie(client, message):
    query = message.text.strip()
    chat_id = int(message.chat.id)
    user_id = message.from_user.id

    # Ignore bot commands or empty queries
    if not query or query.startswith(("/", ".", "!", ",")):
        return

    # 1️⃣ Try Redis cache first
    cache_data = await get_cached_results(chat_id, query)
    if cache_data:
        results = cache_data["results"]
        total = cache_data["total"]
        source = "Redis ⚡"
    else:
        # 2️⃣ Fetch from MongoDB
        mongo_data = await get_movies(chat_id, query, page=1, limit=MAX_RESULTS)
        results = mongo_data["results"]
        total = mongo_data["total"]

        # Store results in Redis for fast pagination
        await set_cached_results(chat_id, query, results)
        source = "MongoDB 🧩"

    if not results:
        return await message.reply_text("❌ No results found.")

    pages = max(1, (len(results) + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE)

    await send_results(
        message, query, chat_id, user_id, 1, results, total, pages,
        source=source, edit=False
    )


# ---------------- SEND RESULTS ---------------- #
async def send_results(
    message, query, chat_id, user_id, page,
    all_results, total, pages, source=None, edit=False
):
    start = (page - 1) * RESULTS_PER_PAGE
    end = start + RESULTS_PER_PAGE
    movies = all_results[start:end]

    text = f"<b>Results for:</b> <code>{escape(query)}</code>\n"
    text += f"📄 Page {page}/{pages} — Total: {total}\n"
    if source:
        text += f"⚙️ Source: {source}\n\n"
    else:
        text += "\n"

    for i, movie in enumerate(movies, start=start + 1):
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
        if year: caption_parts.append(f"({year})")
        if quality: caption_parts.append(quality)
        if codec: caption_parts.append(codec)
        if print_type: caption_parts.append(print_type)
        if lang: caption_parts.append(lang)
        if season: caption_parts.append(f"S{str(season).zfill(2)}")
        if episode: caption_parts.append(f"E{str(episode).zfill(2)}")

        caption = " ".join(str(p) for p in caption_parts if p)
        text += f"{i}. <b>{escape(caption)}</b>\n"
        if link:
            text += f"<b>Link:</b> {link}\n\n"

    # Pagination buttons
    buttons = []
    row = []
    if page > 1:
        row.append(
            InlineKeyboardButton("⬅️ Prev", callback_data=f"page|{chat_id}|{query}|{page-1}|{user_id}")
        )
    if page < pages:
        row.append(
            InlineKeyboardButton("Next ➡️", callback_data=f"page|{chat_id}|{query}|{page+1}|{user_id}")
        )
    if row:
        buttons.append(row)

    markup = InlineKeyboardMarkup(buttons) if buttons else None

    if edit:
        await message.edit_text(
            text,
            reply_markup=markup,
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML
        )
    else:
        await message.reply_text(
            text,
            reply_markup=markup,
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML
        )


# ---------------- PAGINATION HANDLER ---------------- #
@Client.on_callback_query(filters.regex(r"^page\|"))
async def pagination_handler(client, query: CallbackQuery):
    try:
        _, chat_id, search_query, page, owner_id = query.data.split("|", 4)
        chat_id = int(chat_id)
        page = int(page)
        owner_id = int(owner_id)
    except Exception:
        return await query.answer("⚠️ Invalid data.", show_alert=True)

    # 🧠 Allow only the original user
    if query.from_user.id != owner_id:
        return await query.answer("⚠️ Only the original user can use these buttons!", show_alert=True)

    # 1️⃣ Fetch cached data
    cache_data = await get_cached_results(chat_id, search_query)
    if not cache_data:
        return await query.answer("⏳ Cache expired! Please search again.", show_alert=True)

    all_results = cache_data["results"]
    total = cache_data["total"]
    pages = max(1, (len(all_results) + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE)

    if page < 1 or page > pages:
        return await query.answer("⚠️ Invalid page.", show_alert=True)

    await query.answer()
    await send_results(
        query.message, search_query, chat_id, owner_id, page, all_results, total, pages, edit=True
    )
