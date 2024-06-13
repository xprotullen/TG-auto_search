# (c) TheLx0980

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram import filters, Client, enums
from wroxen.wroxen import Wroxen
from wroxen.text import ChatMSG
from wroxen.vars import ADMIN_IDS
from wroxen.database import Database 
from wroxen.chek.search_caption_info import DATABASE, send_result_message
import logging

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
