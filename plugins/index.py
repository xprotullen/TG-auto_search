import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, MessagesFilter, MessageMediaType
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import RPCError
from .search import clear_redis_for_chat
from utils.database import (
    save_movie_async,
    delete_chat_data_async,
    mark_indexed_chat_async,
    unmark_indexed_chat_async,
    get_targets_for_source_async
)
from utils import extract_details, iter_messages, ask_for_message_link_or_id
from info import AUTHORIZED_USERS

INDEXING = {}
BATCH_SIZE = 50
logger = logging.getLogger(__name__)

@Client.on_message(filters.command("index"))
async def index_chat(client, message):
    """
    /index <target_chat_id> <source_chat_id>
    Example: /index -1001234 -1005678
    """
    user_id = message.from_user.id
    if user_id not in AUTHORIZED_USERS:
        return
        
    parts = message.text.split()
    if len(parts) < 3:
        return await message.reply_text("Usage: `/index target_chat_id source_chat_id`")

    target_chat_id = int(parts[1])
    source_chat_id = int(parts[2])
    source_chat_ids = source_chat_id
    user_id = message.from_user.id

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
        return await message.reply_text("❌ You must be admin in target chat to start indexing!")

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
        
    if await get_targets_for_source_async(source_chat_id):
        return await message.reply_text(
            f"⚠️ `{target_chat_id}` is already indexed from `{source_chat_id}`.\n"
            f"To reindex, run `/delete {target_chat_id} {source_chat_id}` first."
        )
        
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
        [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_index_{user_id}")]
    ])
    progress = await message.reply_text(
        f"📦 Indexing started...\nFrom `{source_chat_id}` → `{target_chat_id}`\nSkip: `{current_msg_id}`",
        reply_markup=keyboard
    )

    INDEXING[user_id] = True
    indexed = 0
    errors = 0
    unsupported = 0

    try:
        await mark_indexed_chat_async(target_chat_id, source_chat_ids)
        async for msg in iter_messages(client, source_chat_id, last_msg_id, current_msg_id):
            if not INDEXING.get(user_id):
                await progress.edit_text("🚫 Indexing cancelled.")
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
                details = extract_details(msg.caption)
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
                    caption=msg.caption,
                    link=msg.link
                )
                indexed += 1
                if indexed % BATCH_SIZE == 0:
                    await asyncio.sleep(2)
                    await progress.edit_text(
                        f"📈 Indexed: {indexed}\nUnsupported: {unsupported}\n⚠️ Failed: {errors}\n"
                        f"From `{source_chat_id}` → `{target_chat_id}`",
                        reply_markup=keyboard
                    )
            except Exception as inner_e:
                errors += 1
                logger.info(f"⚠️ Skipped: {inner_e}")

        await progress.edit_text(
            f"✅ Completed!\n📂 Indexed: <b>{indexed}</b>\nUnsupported: {unsupported}\n⚠️ Failed: <b>{errors}</b>\n"
            f"Linked `{source_chat_id}` → `{target_chat_id}`"
        )

    except Exception as e:
        await progress.edit_text(f"❌ Error: {e}")

    finally:
        INDEXING.pop(user_id, None)

@Client.on_callback_query(filters.regex(r"cancel_index_(\d+)"))
async def cancel_index_callback(client, callback_query):
    user_id = int(callback_query.matches[0].group(1))
    INDEXING[user_id] = False
    await callback_query.answer("Cancelled!", show_alert=True)
    await callback_query.message.edit_text("🚫 Indexing cancelled.")

@Client.on_message(filters.command("delete"))
async def delete_indexed_pair(client, message):
    """
    /delete <target_chat_id> <source_chat_id>
    Removes mapping & deletes records for that target.
    """
    user_id = message.from_user.id
    if user_id not in AUTHORIZED_USERS:
        return
        
    parts = message.text.split()
    if len(parts) < 3:
        return await message.reply_text("Usage: `/delete target_chat_id source_chat_id`")

    target_chat_id = int(parts[1])
    source_chat_id = int(parts[2])

    try:
        mongo_deleted = await delete_chat_data_async(target_chat_id)
        redis_deleted = await clear_redis_for_chat(target_chat_id) 
        await unmark_indexed_chat_async(target_chat_id, source_chat_id)
        await message.reply_text(
            f"🗑 MongoDB: Deleted <b>{mongo_deleted} records and</b>\n Redis: Deleted {redis_deleted} keys For `{target_chat_id}`  "
            f"and removed link with `{source_chat_id}`"
        )
    except Exception as e:
        await message.reply_text(f"❌ Error: `{e}`")
