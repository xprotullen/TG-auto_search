import logging
from pyrogram import filters
from pyrogram.types import Message
from utils.database import is_source_in_db, save_movie_async
from utils import extract_details

logger = logging.getLogger(__name__)

def register_userbot_handlers(user_client):
    @user_client.on_message((filters.group | filters.channel) & (filters.document | filters.video))
    async def auto_index_new_post(client, message: Message):
        from_chat = message.chat.id
        try:
            target_chats = await is_source_in_db(from_chat)
            if not target_chats:
                return 

            msg_caption = (
                message.caption
                or getattr(message.video, "file_name", None)
                or getattr(message.document, "file_name", None)
            )
            if not msg_caption:
                return
 
            file_uid = (
                getattr(message.video, "file_unique_id", None)
                or getattr(message.document, "file_unique_id", None)
            )

            details = extract_details(msg_caption)

            for target_chat in target_chats:
                try:
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
                        caption=msg_caption,
                        link=message.link,
                        file_unique_id=file_uid
                    )
                    logger.info(f"✅ Auto-indexed post from {from_chat} → {target_chat}")
                except Exception as inner_e:
                    logger.warning(f"⚠️ Failed to save for target {target_chat}: {inner_e}")

        except Exception as e:
            logger.exception(f"⚠️ Auto-index error: {e}")
