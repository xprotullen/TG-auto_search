import logging
from pyrogram import Client, enums, __version__
from info import API_HASH, APP_ID, LOGGER, BOT_TOKEN 
from user import User
from utils.database import ensure_indexes
from plugins.newpost import register_userbot_handlers
from typing import Union, Optional, AsyncGenerator
from pyrogram import types

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

    async def start(self, *args, **kwargs):
        await super().start(*args, **kwargs)
        bot_details = await self.get_me()
        self.set_parse_mode(enums.ParseMode.HTML)
        self.LOGGER(__name__).info(
            f"🤖 @{bot_details.username} started successfully!"
        )
        
        await ensure_indexes()

        self.USER, self.USER_ID = await User().start()
        self.LOGGER(__name__).info("✅ Userbot started successfully!")

        try:
            register_userbot_handlers(self.USER)
            self.LOGGER(__name__).info("📌 Userbot message handlers registered.")
        except Exception as e:
            self.LOGGER(__name__).error(f"Failed to register userbot handlers: {e}")

    async def stop(self, *args, **kwargs):
        await super().stop(*args, **kwargs)
        self.LOGGER(__name__).info("🛑 Bot stopped. Bye.")

    async def iter_messages(self, chat_id: Union[int, str], limit: int, offset: int = 0) -> Optional[AsyncGenerator["types.Message", None]]:
        """Iterate through a chat sequentially.
        This convenience method does the same as repeatedly calling :meth:`~pyrogram.Client.get_messages` in a loop, thus saving
        you from the hassle of setting up boilerplate code. It is useful for getting the whole chat messages with a
        single call.
        Parameters:
            chat_id (``int`` | ``str``):
                Unique identifier (int) or username (str) of the target chat.
                For your personal cloud (Saved Messages) you can simply use "me" or "self".
                For a contact that exists in your Telegram address book you can use his phone number (str).
                
            limit (``int``):
                Identifier of the last message to be returned.
                
            offset (``int``, *optional*):
                Identifier of the first message to be returned.
                Defaults to 0.
        Returns:
            ``Generator``: A generator yielding :obj:`~pyrogram.types.Message` objects.
        Example:
            .. code-block:: python
                for message in app.iter_messages("pyrogram", 1, 15000):
                    print(message.text)
        """
        current = offset
        while True:
            new_diff = min(200, limit - current)
            if new_diff <= 0:
                return
            messages = await self.get_messages(chat_id, list(range(current, current+new_diff+1)))
            for message in messages:
                yield message
                current += 1
