import logging
from pyrogram import Client, enums
from info import API_HASH, APP_ID, LOGGER, BOT_TOKEN
from user import User
from utils.database import ensure_indexes, get_restart_message, clear_restart_message
from plugins.newpost import register_userbot_handlers
from pyrogram.errors import FloodWait, MessageNotModified
import asyncio


class Wroxen(Client):
    USER: User = None
    USER_ID: int = None

    def __init__(self):
        super().__init__(
            "wroxen",
            api_hash=API_HASH,
            api_id=APP_ID,
            plugins={"root": "plugins"},
            workers=200,
            bot_token=BOT_TOKEN,
            sleep_threshold=10
        )
        self.LOGGER = LOGGER

    async def start(self, *args, **kwargs):
        await super().start(*args, **kwargs)
        bot_details = await self.get_me()
        self.set_parse_mode(enums.ParseMode.HTML)
        self.LOGGER(__name__).info(f"🤖 @{bot_details.username} started successfully!")

        await ensure_indexes()

        self.USER, self.USER_ID = await User().start()
        self.LOGGER(__name__).info("✅ Userbot started successfully!")

        try:
            register_userbot_handlers(self.USER)
            self.LOGGER(__name__).info("📌 Userbot message handlers registered.")
        except Exception as e:
            self.LOGGER(__name__).error(f"Failed to register userbot handlers: {e}")

        await self._confirm_restart()

    async def _confirm_restart(self):
        """Edit the restart message after successful restart."""
        chat_id, msg_id = await get_restart_message()
        
        if not chat_id or not msg_id:
            await clear_restart_message()
            return

        try:
            try:
                await self.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text="✅ Bot restarted successfully!"
                )
            except FloodWait as e:
                self.LOGGER(__name__).warning(f"FloodWait: sleeping {e.value}s before editing restart message")
                await asyncio.sleep(e.value)
                await self.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text="✅ Bot restarted successfully!"
                )
            except MessageNotModified:
                pass

            await clear_restart_message()

        except Exception as e:
            self.LOGGER(__name__).error(f"⚠️ Error confirming restart message: {e}", exc_info=True)

    async def stop(self, *args, **kwargs):
        await super().stop(*args, **kwargs)
        self.LOGGER(__name__).info("🛑 Bot stopped. Bye.")       
