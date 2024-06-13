# (c) TheLx0980

from pyrogram import filters, Client, enums
import logging
logger = logging.getLogger(__name__)

@Client.on_message(filters.command("help") & filters.private & filters.incoming)
async def start(client, message):
    await message.reply(
        text="Hi, I'm Online",
        disable_web_page_preview=True,
        quote=True
    )
