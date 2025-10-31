from pyrogram import filters, Client, enums

@Client.on_message(filters.command('start'))
async def start(bot, message):
    await message.reply('Alive!!!')
