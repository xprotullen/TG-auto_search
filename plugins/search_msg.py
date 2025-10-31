import re
from pyrogram import filters, enums, Client
from pyrogram.types import CallbackQuery, Message
from search_info import DATABASE, send_result_message, extract_movie_details
from database import get_indexes

MEDIA_FILTER = enums.MessagesFilter.VIDEO 

@Client.on_message(filters.group & filters.text)
async def search_movies(client: Client, message: Message):
    if re.findall(r"(^[/!.,]|^[\U0001F600-\U000E007F])", message.text):
        return

    if len(message.text) < 3:
        return

    query = message.text
    group_id = message.chat.id
    indexed_chats = await get_indexes(group_id)

    if not indexed_chats:
        await message.reply_text("❌ No indexed chats found. Use `/index chat_id` first.", quote=True)
        return

    msgs = []
    for chat_id in indexed_chats:
        async for msg in client.USER.search_messages(chat_id, query=query, filter=MEDIA_FILTER):
            if not msg.caption:
                continue
            movie_name, year, quality = extract_movie_details(msg.caption)
            movie_text = f"<b>{movie_name} ({year}) {quality}</b>\n<b>Link:</b> {msg.link}"
            msgs.append(movie_text)

    if not msgs:
        return await message.reply_text("😞 No results found.", quote=True)

    await send_result_message(client, message, query, msgs, page=1)
