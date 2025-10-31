# main.py
import asyncio
from pyrogram import Client
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from info import BOT_TOKEN, API_ID, API_HASH, USER_SESSION, AUTO_INDEX_INTERVAL_HOURS
from index_handler import index_chat_auto
import index_handler  # to ensure functions available (and route decorators loaded)
import delete_handler
import search_msg  # decorator handlers loaded
from database import init_db

# create bot client
bot = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# optional user client (for searching messages across chats using user account)
USER = None
if USER_SESSION:
    USER = Client("movie_user", api_id=API_ID, api_hash=API_HASH, session_string=USER_SESSION)

# attach USER to bot object for convenience (used in index_handler)
async def start_clients():
    await bot.start()
    if USER:
        await USER.start()
        # attach as attribute so handlers can use client.USER
        bot.USER = USER
    else:
        bot.USER = bot  # fallback - but bot may have restricted search

    print("Clients started")

    # start scheduler for auto-index
    scheduler = AsyncIOScheduler()
    # run every AUTO_INDEX_INTERVAL_HOURS hours
    scheduler.add_job(lambda: asyncio.create_task(index_chat_auto(bot)), "interval", hours=AUTO_INDEX_INTERVAL_HOURS)
    scheduler.start()
    print("Scheduler started")

    # keep running
    await asyncio.get_event_loop().create_future()

if __name__ == "__main__":
    asyncio.run(start_clients())
