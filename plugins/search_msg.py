import math
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from html import escape
from database import search_movies

@Client.on_message(filters.group & filters.text)
async def movie_search(client, message):
    query = message.text.strip()
    if len(query) < 3:
        return

    page = 1
    results, total = await search_movies(query, page)

    if not results:
        return await message.reply("❌ No results found in database.")

    total_pages = math.ceil(total / 10)
    text = f"<b>🔍 Results for:</b> <code>{escape(query)}</code>\n\n"
    for i, movie in enumerate(results, start=1):
        text += f"{i}. <b>{movie['movie_name']}</b> ({movie['year']}) [{movie['quality']}]\n🔗 <a href='{movie['link']}'>Link</a>\n\n"

    if total_pages > 1:
        buttons = [[InlineKeyboardButton("Next ▶️", callback_data=f"next:{query}:{page+1}")]]
        await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)
    else:
        await message.reply(text, disable_web_page_preview=True)


@Client.on_callback_query()
async def pagination_callback(client, query):
    data = query.data
    if data.startswith("next:"):
        _, movie_query, page = data.split(":")
        page = int(page)
        results, total = await search_movies(movie_query, page)
        total_pages = math.ceil(total / 10)

        text = f"<b>🔍 Results for:</b> <code>{escape(movie_query)}</code>\n\n"
        for i, movie in enumerate(results, start=(page-1)*10+1):
            text += f"{i}. <b>{movie['movie_name']}</b> ({movie['year']}) [{movie['quality']}]\n🔗 <a href='{movie['link']}'>Link</a>\n\n"

        buttons = []
        if page > 1:
            buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"prev:{movie_query}:{page-1}"))
        if page < total_pages:
            buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"next:{movie_query}:{page+1}"))

        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([buttons]), disable_web_page_preview=True)


    elif data.startswith("prev:"):
        _, movie_query, page = data.split(":")
        page = int(page)
        results, total = await search_movies(movie_query, page)
        total_pages = math.ceil(total / 10)

        text = f"<b>🔍 Results for:</b> <code>{escape(movie_query)}</code>\n\n"
        for i, movie in enumerate(results, start=(page-1)*10+1):
            text += f"{i}. <b>{movie['movie_name']}</b> ({movie['year']}) [{movie['quality']}]\n🔗 <a href='{movie['link']}'>Link</a>\n\n"

        buttons = []
        if page > 1:
            buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"prev:{movie_query}:{page-1}"))
        if page < total_pages:
            buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"next:{movie_query}:{page+1}"))

        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([buttons]), disable_web_page_preview=True)
