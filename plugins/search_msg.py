import re
from pyrogram import Client, filters
from pyrogram.types import Message
from database import search_movies
from search_info import send_result_message

@Client.on_message(filters.group & filters.text)
async def search_movie_handler(client: Client, message: Message):
    text = message.text.strip()

    if re.match(r"(^[/!.,]|^[\U0001F600-\U000E007F])", text):
        return

    if len(text) < 3:
        return

    results = await search_movies(message.chat.id, text)
    if not results:
        return await message.reply_text("😔 No results found in database.")

    movies = []
    for doc in results:
        movies.append(f"<b>{doc['movie_name']}</b>\n<b>Link:</b> {doc['link']}")

    await send_result_message(client, message, text, movies, page=1)
