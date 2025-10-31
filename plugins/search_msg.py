import re
import logging
from html import escape
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message
from search_info import DATABASE, send_result_message, extract_movie_details
from database import database

# Setup logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@Client.on_message(filters.group & filters.text)
async def filter(client: Client, message: Message):
    """Handle text messages in groups and search for movies."""

    # Ignore commands or emoji-only messages
    if re.findall(r"((^\/|^,|^!|^\.|^[\U0001F600-\U000E007F]).*)", message.text):
        return

    if len(message.text) <= 2:
        return

    query = message.text.strip()

    # 1️⃣ First, check in the local database
    db_movies = await database.search_movies(message.chat.id, query)

    if db_movies:
        msgs = []
        for movie in db_movies:
            movie_text = (
                f"<b>{escape(movie.get('movie_name', 'Unknown'))} "
                f"({movie.get('year', 'Unknown')}) "
                f"{movie.get('quality', '')}</b>\n"
                f"<b>Link:</b> {movie.get('message_link', '')}"
            )
            msgs.append(movie_text)

        page = 1
        await send_result_message(client, message, query, msgs, page)
        return

    # 2️⃣ If not found in database, search in source chat
    group_data = await database.get_group(message.chat.id)
    if not group_data:
        return

    source_chat_id = group_data.get("source_chat_id")
    if not source_chat_id:
        return

    msgs = []
    try:
        async for msg in client.USER.search_messages(
            source_chat_id,
            query=query,
            filter=enums.MessagesFilter.VIDEO
        ):
            caption = msg.caption or ""
            link = msg.link
            movie_name, year, quality = extract_movie_details(caption)
            movie_text = (
                f"<b>{escape(movie_name)} ({year}) {quality}</b>\n"
                f"<b>Link:</b> {link}"
            )
            msgs.append(movie_text)

        if not msgs:
            return

        page = 1
        await send_result_message(client, message, query, msgs, page)

    except Exception as e:
        logger.error(f"Error while searching in source chat: {e}")


@Client.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    """Handle pagination callback buttons."""
    data = query.data

    # ⏭ Next Page
    if data.startswith('next_page:'):
        if query.message.reply_to_message.from_user.id == query.from_user.id:
            _, query_text, page = data.split(':')
            db_entry = DATABASE.get(query_text)

            if db_entry:
                movies = db_entry['movies']
                result_message_id = db_entry['message_id']

                await query.answer()
                await send_result_message(
                    client, query.message, query_text, movies, int(page), result_message_id
                )
            else:
                await query.answer("यह मैसेज काफी पुराना हो चुका है।")
        else:
            await query.answer("यह आपके लिए नहीं है!", show_alert=True)

    # ⏮ Previous Page
    elif data.startswith('previous_page:'):
        if query.message.reply_to_message.from_user.id == query.from_user.id:
            _, query_text, page = data.split(':')
            db_entry = DATABASE.get(query_text)

            if db_entry:
                movies = db_entry['movies']
                result_message_id = db_entry['message_id']

                await query.answer()
                await send_result_message(
                    client, query.message, query_text, movies, int(page), result_message_id
                )
            else:
                await query.answer("यह मैसेज काफी पुराना हो चुका है।")
        else:
            await query.answer("यह आपके लिए नहीं है!", show_alert=True)
