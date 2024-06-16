# (c) TheLx0980
from pyrogram import filters, Client, enums

@Client.on_message(filters.command('start') & filters.user(5163706369))
async def start(bot, message):
    await message.reply('Alive!!!')
