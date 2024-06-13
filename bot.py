import logging
from pyrogram import Client, enums, __version__
from info import API_HASH, APP_ID, LOGGER, BOT_TOKEN 
from pyrogram import types
from user import User

class Wroxen(Client):
    USER: User = None
    USER_ID: int = None
  
    def __init__(self):
        super().__init__(
            "wroxen",
            api_hash=API_HASH,
            api_id=APP_ID,
            plugins={
                "root": "plugins"
            },
            workers=200,
            bot_token=BOT_TOKEN,
            sleep_threshold=10
        )
        self.LOGGER = LOGGER

    async def start(self):
        await super().start()
        bot_details = await self.get_me()
        self.set_parse_mode(enums.ParseMode.HTML)
        self.LOGGER(__name__).info(
            f"@{bot_details.username}  started! "
        )
        self.USER, self.USER_ID = await User().start()
       

    async def stop(self, *args):
        await super().stop()
        self.LOGGER(__name__).info("Bot stopped. Bye.")
