# (c) TheLx0980
from pyrogram import filters, Client, enums

@Client.on_message(filters.command("help") & filters.private)
async def start(client, message):
    await message.reply("Hi, I'm Online")
