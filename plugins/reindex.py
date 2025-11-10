from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, MessageMediaType, MessagesFilter
from pyrogram.errors import RPCError, FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
import logging
from .search import clear_redis_for_chat
from info import AUTHORIZED_USERS
from utils.database import (
    delete_chat_data_async,
    mark_indexed_chat_async,
    save_movie_async,
    rebuild_indexes,
    is_source_linked_to_target
)
from utils import extract_details

logger = logging.getLogger(__name__)

REINDEXING = {}
BATCH_SIZE = 50


@Client.on_message(filters.command("reindex"))
async def reindex_chat(client, message):
    user_id = message.from_user.id
    if user_id not in AUTHORIZED_USERS:
        return
        
    if REINDEXING.get(user_id):
        return await message.reply_text("⚠️ Reindexing already running! Please wait or cancel it first.")
        
            
    parts = message.text.split()
    if len(parts) < 3:
        return await message.reply_text("Usage: `/reindex target_chat_id source_chat_id`")

    target_chat_id = int(parts[1])
    source_chat_id = int(parts[2])
     
    if not str(target_chat_id).startswith("-100"):
        target_chat_id = f"-100{target_chat_id}"
    if not str(source_chat_id).startswith("-100"):
        source_chat_id = f"-100{source_chat_id}"

    try:
        target_chat_id = int(target_chat_id)
        source_chat_id = int(source_chat_id)
    except ValueError:
        return await message.reply_text("❌ Invalid chat ID. Must be numbers like -1001234567890")

    try:
        target_chat = await client.get_chat(target_chat_id)
    except Exception as e:
        return await message.reply_text(f"❌ Cannot access target chat: Make sure bot is admin in source chat and target chat id is correct {e}")

    try:
        source = await client.get_chat(source_chat_id)
    except Exception as e:
        return await message.reply_text(f"❌ Cannot access source chat: Make sure bot is admin in source chat and source chat id is correct {e}")

    if not await is_source_linked_to_target(target_chat_id, source_chat_id):
        return await message.reply_text(
            f"These Chat are not indexed, First Index using /index command"
        )
        
    async def check_admin(chat_id, who):
        try:
            member = await client.get_chat_member(chat_id, who)
            return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
        except Exception:
            return False

    if not await check_admin(target_chat_id, "me"):
        return await message.reply_text("❌ Bot must be admin in target chat!")

    if not await check_admin(target_chat_id, user_id):
        return await message.reply_text("❌ You must be admin in target chat!")

    if not await check_admin(source_chat_id, "me"):
        return await message.reply_text("❌ Bot must be admin in source chat!")

    try:
        userbot_member = await client.USER.get_chat_member(source_chat_id, "me")
        if userbot_member.status not in [
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
            ChatMemberStatus.MEMBER
        ]:
            return await message.reply_text("❌ Userbot must be at least a member in source chat!")
    except Exception as e:
        return await message.reply_text(f"⚠️ Userbot can't access source chat: {e}")
        
    prompt = await message.reply("📩 Forward the last message from the channel/group or send a message link:")
    user_msg = await client.listen(chat_id=message.chat.id, user_id=message.from_user.id)
    await prompt.delete()

    last_msg_id = None
    forward_origin = getattr(user_msg, "forward_origin", None)
    if forward_origin and getattr(forward_origin, "chat", None):
        forward_chat = getattr(forward_origin.chat, "sender_chat", None) or forward_origin.chat
        if forward_chat.id != source_chat_id:
            return await message.reply_text("❌ Message must be from the same source chat!")
        last_msg_id = getattr(forward_origin, "message_id", None)
        if not last_msg_id:
            return await message.reply("No Message ID Found")
    elif getattr(user_msg, "text", None) and user_msg.text.startswith("https://t.me"):
        try:
            parts = user_msg.text.rstrip("/").split("/")
            msg_id = int(parts[-1])
            chat_part = parts[-2]
            if chat_part.isnumeric():
                chat_id_from_link = int("-100" + chat_part)
            else:
                chat = await client.get_chat(chat_part)
                chat_id_from_link = chat.id

            if chat_id_from_link != source_chat_id:
                return await message.reply_text("❌ t.me link must point to the same source chat!")

            last_msg_id = msg_id
        except Exception:
            return await message.reply_text("❌ Invalid t.me link format!")
    else:
        return await message.reply_text("❌ Invalid input! Must forward a message or provide a t.me link.")
    
    s = await message.reply_text("✏️ Enter number of messages to skip from start (0 for none):")
    skip_msg = await client.listen(chat_id=message.chat.id, user_id=user_id)
    await s.delete()

    try:
        start_msg_id = int(skip_msg.text)
    except ValueError:
        return await message.reply_text("❌ Invalid number!")
        
    await message.reply_text(f"🗑️ Deleting old MongoDB and Redis data for `{target_chat_id}`...")
    deleted_mongo = await delete_chat_data_async(chat_id=target_chat_id)
    deleted_redis = await clear_redis_for_chat(target_chat_id)
    await message.reply_text(f"✅ Deleted {deleted_mongo} Mongo docs and {deleted_redis} Redis keys.")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_reindex_{user_id}")]
    ])
    progress = await message.reply_text(
        f"♻️ Reindexing started...\nFrom `{source_chat_id}` → `{target_chat_id}`",
        reply_markup=keyboard
    )

    REINDEXING[user_id] = True

    indexed = 0
    duplicates = 0
    errors = 0
    unsupported = 0

    try:
        async for msg in client.USER.search_messages(
            source_chat_id,
            filter=MessagesFilter.EMPTY,
            offset=0
        ):
            if not REINDEXING.get(user_id):
                await progress.edit_text("🚫 Indexing cancelled.")
                return
                
            if msg.id < start_msg_id or msg.id > last_msg_id:
                continue

            if not msg.media or msg.media not in [MessageMediaType.VIDEO, MessageMediaType.DOCUMENT]:
                unsupported += 1
                continue

            msg_caption = (
                msg.caption
                or getattr(msg.video, "file_name", None)
                or getattr(msg.document, "file_name", None)
            )
            if not msg_caption:
                unsupported += 1
                continue

            file_uid = (
                getattr(msg.video, "file_unique_id", None)
                or getattr(msg.document, "file_unique_id", None)
            )

            try:
                details = extract_details(msg_caption)
                result = await save_movie_async(
                    chat_id=target_chat_id,
                    title=details.get("title"),
                    year=details.get("year"),
                    quality=details.get("quality"),
                    lang=details.get("lang"),
                    print_type=details.get("print"),
                    season=details.get("season"),
                    episode=details.get("episode"),
                    codec=details.get("codec"),
                    caption=msg_caption,
                    link=msg.link,
                    file_unique_id=file_uid
                )

                if result == "saved":
                    indexed += 1
                elif result == "duplicate":
                    duplicates += 1
                else:
                    errors += 1

                total = indexed + duplicates + errors + unsupported
                if total % BATCH_SIZE == 0:
                    await asyncio.sleep(2)
                    await progress.edit_text(
                        f"📈 Reindexing Progress\n"
                        f"✅ Indexed: {indexed}\n"
                        f"⏩ Duplicates: {duplicates}\n"
                        f"⚠️ Unsupported: {unsupported}\n"
                        f"❌ Failed: {errors}\n"
                        f"From `{source_chat_id}` → `{target_chat_id}`",
                        reply_markup=keyboard
                    )

            except FloodWait as fw:
                await asyncio.sleep(fw.value)
            except Exception as inner_e:
                errors += 1
                logger.warning(f"⚠️ Skipped message due to error: {inner_e}")

        await rebuild_indexes()
        await mark_indexed_chat_async(target_chat_id, source_chat_id)

        await progress.edit_text(
            f"✅ Reindex Completed!\n\n"
            f"📂 Indexed: {indexed}\n"
            f"⏩ Duplicates: {duplicates}\n"
            f"⚠️ Unsupported: {unsupported}\n"
            f"❌ Failed: {errors}\n"
            f"🔗 `{source_chat_id}` → `{target_chat_id}`"
        )

    except Exception as e:
        await progress.edit_text(f"❌ Error during reindex: {e}")
        logger.exception(e)

    finally:
        REINDEXING.pop(user_id, None)


@Client.on_callback_query(filters.regex(r"cancel_reindex_(\d+)"))
async def cancel_reindex_callback(client, callback_query):
    user_id = int(callback_query.matches[0].group(1))
    REINDEXING[user_id] = False
    await callback_query.answer("Cancelled!", show_alert=True)
    await callback_query.message.edit_text("🚫 Indexing cancelled.")
