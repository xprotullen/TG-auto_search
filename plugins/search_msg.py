# plugins/search_msg.py

import re
import asyncio
from pyrogram import filters, enums, Client
from html import escape
from pyrogram.types import CallbackQuery, Message
from search_info import DATABASE, send_result_message, extract_movie_details
from info import SEARCH_ID, ADMIN_ID
from db import cache_col

MEDIA_FILTER = enums.MessagesFilter.VIDEO 

@Client.on_message(filters.group & filters.text)
async def filter(client: Client, message: Message):
    if re.findall("((^\/|^,|^!|^\.|^[\U0001F600-\U000E007F]).*)", message.text):
        return

    query = message.text.strip().lower()
    if len(query) <= 2:
        return

    # 1️⃣ Check memory cache
    if query in DATABASE:
        data = DATABASE[query]
        return await send_result_message(client, message, query, data['movies'], data['page'])

    # 2️⃣ Check MongoDB
    mongo_data = await cache_col.find_one({"query": query})
    if mongo_data:
        DATABASE[query] = mongo_data
        return await send_result_message(client, message, query, mongo_data['movies'], mongo_data.get('page', 1))

    # 3️⃣ Search Telegram
    msgs = []
    async for msg in client.USER.search_messages(SEARCH_ID, query=query, filter=MEDIA_FILTER):
        caption = msg.caption or ""
        link = msg.link
        movie_name, year, quality = extract_movie_details(caption)
        movie_text = f"<b>{escape(movie_name)} ({year}) {quality}</b>\n<b>Link:</b> {link}"
        msgs.append(movie_text)

    if not msgs:
        return await message.reply_text("❌ No results found.")

    await send_result_message(client, message, query, msgs, 1)


@Client.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    data = query.data
    if data.startswith(("next_page:", "previous_page:")):
        _, query_text, page = data.split(":")
        page = int(page)

        db_entry = DATABASE.get(query_text) or await cache_col.find_one({"query": query_text})
        if not db_entry:
            return await query.answer("⚠️ This message is too old.")

        if query.message.reply_to_message.from_user.id != query.from_user.id:
            return await query.answer("🚫 This isn’t for you!", show_alert=True)

        await query.answer()
        await send_result_message(client, query.message, query_text, db_entry['movies'], page, db_entry.get('message_id'))


# 🔹 /index command (save all messages in DB)
@Client.on_message(filters.command("index") & filters.user(ADMIN_ID))
async def index_command(client: Client, message: Message):
    await message.reply_text("📦 Starting indexing... This might take a while.")

    total = 0
    async for msg in client.USER.search_messages(SEARCH_ID, filter=MEDIA_FILTER):
        caption = msg.caption or ""
        link = msg.link
        movie_name, year, quality = extract_movie_details(caption)
        movie_text = f"<b>{escape(movie_name)} ({year}) {quality}</b>\n<b>Link:</b> {link}"

        query_key = movie_name.lower().strip()
        if not query_key:
            continue

        DATABASE.setdefault(query_key, {"movies": [], "page": 1, "message_id": None})
        DATABASE[query_key]["movies"].append(movie_text)

        await cache_col.update_one(
            {"query": query_key},
            {"$addToSet": {"movies": movie_text}, "$set": {"page": 1}},
            upsert=True
        )

        total += 1
        if total % 100 == 0:
            await asyncio.sleep(2)

    await message.reply_text(f"✅ Indexing complete!\nTotal movies indexed: <b>{total}</b>")


# 🔹 /rebuildcache command (load from MongoDB)
@Client.on_message(filters.command("rebuildcache") & filters.user(ADMIN_ID))
async def rebuild_cache(client: Client, message: Message):
    count = 0
    async for entry in cache_col.find({}):
        DATABASE[entry["query"]] = {
            "movies": entry["movies"],
            "page": entry.get("page", 1),
            "message_id": entry.get("message_id")
        }
        count += 1

    await message.reply_text(f"🔁 Cache rebuilt from MongoDB!\nLoaded: <b>{count}</b> entries.")
