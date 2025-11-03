import logging
from pyrogram import filters
from pyrogram.types import Message
from utils.database import get_targets_for_source_async, save_movie_async
from utils.extract import extract_details

logger = logging.getLogger(__name__)

def register_userbot_handlers(user_client):
    """Attach media auto-index listener to userbot."""
    
    @user_client.on_message((filters.group | filters.channel) & (filters.document | filters.video))
    async def auto_index_new_post(client, message: Message):
        """
        Triggered whenever a new media (video/document) is posted in a linked source.
        Works for user, admin, or even other bots.
        """
        from_chat = message.chat.id
        try:
            targets = await get_targets_for_source_async(from_chat)
            if not targets:
                return  # Not a tracked source group/channel

            msg_caption = (
                message.caption
                or getattr(message.video, "file_name", None)
                or getattr(message.document, "file_name", None)
            )
            if not msg_caption:
                return

            details = extract_details(msg_caption)

            for target_chat in targets:
                await save_movie_async(
                    chat_id=target_chat,
                    title=details.get("title"),
                    year=details.get("year"),
                    quality=details.get("quality"),
                    lang=details.get("lang"),
                    print_type=details.get("print"),
                    season=details.get("season"),
                    episode=details.get("episode"),
                    codec=details.get("codec"),
                    caption=message.caption,
                    link=message.link
                )
                logger.info(f"✅ Auto-indexed post from {from_chat} → {target_chat}")

        except Exception as e:
            logger.exception(f"⚠️ Auto-index error: {e}")
