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
    rebuild_indexes
)
from utils import extract_details, iter_messages, ask_for_message_link_or_id

logger = logging.getLogger(__name__)

REINDEXING = {}
BATCH_SIZE = 50


@Client.on_message(filters.command("reindex"))
async def reindex_chat(client, message):
    """
    /reindex <target_chat_id> <source_chat_id>
    Example: /reindex -1001234 -1005678
    """
    user_id = message.from_user.id
    if user_id not in AUTHORIZED_USERS:
        return

    parts = message.text.split()
    if len(parts) < 3:
        return await message.reply_text("Usage: `/reindex target_chat_id source_chat_id`")

    target_chat_id = int(parts[1])
    source_chat_id = int(parts[2])

    try:
        bot_member = await client.get_chat_member(target_chat_id, "me")
    except RPCError as e:
        return await message.reply_text(f"⚠️ Telegram Error (target): {e}")
    except Exception as e:
        return await message.reply_text(f"❌ Unexpected error in target chat: {e}")
    if bot_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
        return await message.reply_text("❌ Bot must be admin in target chat!")

    try:
        user_member = await client.get_chat_member(target_chat_id, user_id)
    except RPCError as e:
        return await message.reply_text(f"⚠️ Telegram Error (target user): {e}")
    except Exception as e:
        return await message.reply_text(f"❌ Unexpected error checking user in target chat: {e}")
    if user_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
        return await message.reply_text("❌ You must be admin in target chat to start reindexing!")

    try:
        bot_member_source = await client.get_chat_member(source_chat_id, "me")
    except RPCError as e:
        return await message.reply_text(f"⚠️ Telegram Error (source): {e}")
    except Exception as e:
        return await message.reply_text(f"❌ Unexpected error in source chat: {e}")
    if bot_member_source.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
        return await message.reply_text("❌ Bot must be admin in source chat to fetch messages!")

    try:
        userbot_member = await client.USER.get_chat_member(source_chat_id, "me")
    except RPCError as e:
        return await message.reply_text(f"⚠️ Telegram Error (userbot): {e}")
    except Exception as e:
        return await message.reply_text(f"❌ Userbot can't access source chat: {e}")
    if userbot_member.status not in [
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
        ChatMemberStatus.MEMBER
    ]:
        return await message.reply_text("❌ Userbot must be at least a member in source chat!")

    await message.reply_text(f"🗑️ Deleting old MongoDB and Redis data for `{target_chat_id}`...")
    deleted_mongo = await delete_chat_data_async(chat_id=target_chat_id)
    deleted_redis = await clear_redis_for_chat(target_chat_id)
    await message.reply_text(f"✅ Deleted {deleted_mongo} Mongo docs and {deleted_redis} Redis keys.")

    prompt = await message.reply("✏️ Please send a Start <b>message ID</b>or <b>message link</b>: where u wana start indexing")
    reply = await client.listen(chat_id=message.chat.id, user_id=message.from_user.id)
    await prompt.delete()
    try:
        first_c, current_msg_id = await ask_for_message_link_or_id(message, source_chat_id, reply.text)
    except Exception as e:
        return await message.reply("Error {e}!")

    prompt = await message.reply("✏️ Please send a Last <b>message ID</b>or <b>message link</b>: where u wana stop indexing")
    reply = await client.listen(chat_id=message.chat.id, user_id=message.from_user.id)
    await prompt.delete()
    try:
        source_chat_id, last_msg_id = await ask_for_message_link_or_id(message, source_chat_id, reply.text)
    except Exception as e:
        return await message.reply("Error {e}!")
    
    if first_c != source_chat_id:
        return await message.reply("You Send Two Different Chat Link, Try again and send same chat link")
           
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_reindex_{user_id}")]
    ])
    progress = await message.reply_text(
        f"♻️ Reindexing started...\nFrom `{source_chat_id}` → `{target_chat_id}`\nSkip: `{current_msg_id}`",
        reply_markup=keyboard
    )

    REINDEXING[user_id] = True
    indexed = 0
    errors = 0
    unsupported = 0
    count = 0
    try:
        async for msg in client.iter_messages(source_chat_id, last_msg_id, current_msg_id):
            if not REINDEXING.get(user_id):
                await progress.edit_text("🚫 Reindex cancelled.")
                return

            if msg.empty:
                unsupported += 1
                continue

            if not msg.media:
                unsupported += 1
                continue
                
            if msg.media not in [MessageMediaType.VIDEO, MessageMediaType.DOCUMENT]:
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

            try:
                details = extract_details(msg_caption)
                await save_movie_async(
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
                    link=msg.link
                )
                indexed += 1
                if indexed % BATCH_SIZE == 0:
                    await asyncio.sleep(2)
                    await progress.edit_text(
                        f"♻️ Reindexing...\n✅ Indexed: {indexed}\n⚠️ Unsupported: {unsupported}\n❌ Failed: {errors}\n"
                        f"From `{source_chat_id}` → `{target_chat_id}`",
                        reply_markup=keyboard
                    )    
            except FloodWait as e:
                await asyncio.sleep(e.value)
                continue       
            except Exception as e:
                errors += 1
                logger.warning(f"⚠️ Save failed: {e}")
                continue

        await rebuild_indexes()
        await mark_indexed_chat_async(target_chat_id, source_chat_id)

        await progress.edit_text(
            f"✅ Reindex Completed!\n\n"
            f"📂 Indexed: {indexed}\n⚠️ Unsupported: {unsupported}\n❌ Failed: {errors}\n"
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
