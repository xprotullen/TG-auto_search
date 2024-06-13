# (c) @TheLx0980
# Year : 2023

import re
from pyrogram import filters, enums, Client
from html import escape
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message
from search_info import DATABASE, send_result_message
import logging
from info import SEARCH_ID

MEDIA_FILTER = enums.MessagesFilter.VIDEO 

@Client.on_message(filters.group & filters.text)
async def filter(client: Client, message: Message):
    if re.findall("((^\/|^,|^!|^\.|^[\U0001F600-\U000E007F]).*)", message.text):
        return

    if len(message.text) > 2:
        query = message.text        
        msgs = []
        async for msg in client.USER.search_messages(SEARCH_ID, query=query, filter=MEDIA_FILTER):
            caption = msg.caption
            link = msg.link
            movie_name, year, quality = extract_movie_details(caption)
            movie_text = f"<b>{escape(movie_name)} ({year}) {quality}</b>\n<b>Link:</b> {link}"
            msgs.append(movie_text)

        if not msgs:
            return

        page = 1
        await send_result_message(client, message, query, msgs, page)

@Client.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    data = query.data
    if data.startswith('next_page:'):
        if query.message.reply_to_message.from_user.id == query.from_user.id:
            _, query_text, page = data.split(':')
        
            # Retrieve data from DATABASE
            db_entry = DATABASE.get(query_text)
            if db_entry:
                movies = db_entry['movies']
                result_message_id = db_entry['message_id']
            
                await query.answer()
                await send_result_message(client, query.message, query_text, movies, int(page), result_message_id)
            else:
                await query.answer("यह मैसेज काफी पुराना हो चुका है।")
        else:
            await query.answer("यह आपके लिए नही है!", show_alert=True)
   
    elif data.startswith('previous_page:'):
        if query.message.reply_to_message.from_user.id == query.from_user.id:
            _, query_text, page = data.split(':')
        
            # Retrieve data from DATABASE
            db_entry = DATABASE.get(query_text)
            if db_entry:
                movies = db_entry['movies']
                result_message_id = db_entry['message_id']
                await send_result_message(client, query.message, query_text, movies, int(page), result_message_id)
            else:
                await query.answer("यह मैसेज काफी पुराना हो चुका है।")
        else:
            await query.answer("यह आपके लिए नही है!", show_alert=True)
