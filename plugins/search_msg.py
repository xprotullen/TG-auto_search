# search_msg.py
import re
from pyrogram import Client, filters, enums
from pyrogram.types import CallbackQuery
from html import escape
from aiocache import cached, Cache
from info import CACHE_TTL, PAGE_SIZE
from database import movies_collection
from search_info import generate_result_message, generate_inline_keyboard, ACTIVE_QUERIES, normalize_text_for_search

# ensure simple memory cache
cache = Cache(Cache.MEMORY)

def build_query_regex(query_text: str):
    # Advanced search: treat spaces as .* and escape special chars
    q = re.escape(query_text.strip())
    if " " in query_text:
        # allow fuzzy match on spaces
        q = ".*".join([re.escape(part) for part in query_text.split()])
    pattern = f"{q}"
    return {"$regex": pattern, "$options": "i"}

@cached(ttl=CACHE_TTL, cache=Cache.MEMORY)
async def cached_db_search(query_text: str, limit=100):
    regex = build_query_regex(query_text)
    cursor = movies_collection.find({"$or": [{"movie_name": regex}, {"caption": regex}]})
    # sort recent first
    cursor = cursor.sort([("_id", -1)]).limit(limit)
    docs = await cursor.to_list(length=limit)
    return docs

@Client.on_message(filters.group & filters.text)
async def search_handler(client: Client, message):
    text = message.text.strip()
    if not text or len(text) < 3:
        return
    if re.match(r"^[/\.\,!]", text):  # ignore commands or emoji-starting
        return

    query_text = normalize_text_for_search(text)
    docs = await cached_db_search(query_text, limit=200)
    if not docs:
        return  # no result; you can add fallback to user.search_messages if desired

    # prepare display strings
    movies = []
    for d in docs:
        name = d.get("movie_name") or d.get("caption", "Unknown")
        year = d.get("year", "Unknown")
        quality = d.get("quality", "")
        link = d.get("link", "N/A")
        movies.append(f"<b>{escape(name)}</b> ({escape(str(year))}) {escape(str(quality))}\n<b>Link:</b> {escape(str(link))}")

    # store into ACTIVE_QUERIES with a key (use message id + chat id as key to avoid collisions)
    query_key = f"{message.chat.id}:{message.id}"
    ACTIVE_QUERIES[query_key] = {"movies": movies, "message_id": None, "chat_id": message.chat.id}

    # send first page
    page = 1
    page_movies = movies[(page-1)*PAGE_SIZE : page*PAGE_SIZE]
    text_msg = generate_result_message(query_text, page_movies, page, page_size=PAGE_SIZE)
    markup = generate_inline_keyboard(query_key, len(movies), page, page_size=PAGE_SIZE)

    sent = await message.reply_text(text_msg, parse_mode=enums.ParseMode.HTML, reply_markup=markup)
    # store message id for callbacks editing
    ACTIVE_QUERIES[query_key]["message_id"] = sent.id
    ACTIVE_QUERIES[query_key]["query_text"] = query_text

@Client.on_callback_query()
async def callback_handler(client: Client, cq: CallbackQuery):
    data = cq.data or ""
    if not data:
        return
    action, query_key, page_str = data.split(":", 2)
    page = int(page_str)
    entry = ACTIVE_QUERIES.get(query_key)
    if not entry:
        await cq.answer("यह संदेश बहुत पुराना है।", show_alert=True)
        return

    movies = entry["movies"]
    total = len(movies)
    page_movies = movies[(page-1)*PAGE_SIZE : page*PAGE_SIZE]

    text_msg = generate_result_message(entry.get("query_text", ""), page_movies, page, page_size=PAGE_SIZE)
    markup = generate_inline_keyboard(query_key, total, page, page_size=PAGE_SIZE)

    try:
        await client.edit_message_text(
            chat_id=entry["chat_id"],
            message_id=entry["message_id"],
            text=text_msg,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=markup
        )
        await cq.answer()
    except Exception as e:
        await cq.answer("कोई त्रुटि हुई।", show_alert=True)
