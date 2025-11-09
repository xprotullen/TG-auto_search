import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, MessagesFilter, MessageMediaType, ChatType
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import RPCError, FloodWait
from .search import clear_redis_for_chat
from utils.database import (
    save_movie_async,
    delete_chat_data_async,
    mark_indexed_chat_async,
    unmark_indexed_chat_async,
    is_source_linked_to_target
)
from utils import extract_details
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
        
    if INDEXING.get(user_id):
        return await message.reply_text("⚠️ Indexing already in progress! Please wait or cancel it first.")
            
    parts = message.text.split()
    if len(parts) < 3:
        return await message.reply_text("Usage: `/index target_chat_id source_chat_id`")

    target_chat_id = parts[1]
    source_chat_id = parts[2]
    
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

    if target_chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return await message.reply_text("Target Chat Must Be A Group.")
        
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
        
    if await is_source_linked_to_target(target_chat_id, source_chat_id):
        return await message.reply_text(
            f"⚠️ `{target_chat_id}` is already indexed from `{source_chat_id}`.\n"
            f"To reindex, run `/delete {target_chat_id} {source_chat_id}` first."
        )
        
    prompt = await message.reply("📩 Forward the last message from the channel or send a message link:")
    user_msg = await client.listen(chat_id=message.chat.id, user_id=message.from_user.id)
    await prompt.delete()

    last_msg_id = None
    if getattr(user_msg, "forward_from_chat", None):
        if user_msg.forward_from_chat.id != source_chat_id:
            return await message.reply_text("❌ Message must be from the same source chat!")
        last_msg_id = user_msg.forward_from_message_id
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

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_index_{user_id}")]
    ])
    progress = await message.reply_text(
        f"📦 Indexing started...\nFrom `{source_chat_id}` → `{target_chat_id}`",
        reply_markup=keyboard
    )

    INDEXING[user_id] = True
    indexed = 0
    errors = 0
    unsupported = 0
    skipped_uid = 0
    duplicates = 0

    try:
        async for msg in client.USER.search_messages(
            source_chat_id,
            filter=MessagesFilter.EMPTY,
            offset=0
        ):
            try:
                if not INDEXING.get(user_id):
                    await progress.edit_text("🚫 Indexing cancelled.")
                    return

                if msg.id < start_msg_id or msg.id > last_msg_id:
                    continue

                if not msg.media or msg.media not in [MessageMediaType.VIDEO, MessageMediaType.DOCUMENT]:
                    unsupported += 1
                    continue

                caption = (
                    msg.caption
                    or getattr(msg.video, "file_name", None)
                    or getattr(msg.document, "file_name", None)
                )
                if not caption:
                    unsupported += 1
                    continue

                file_uid = (
                    getattr(msg.video, "file_unique_id", None)
                    or getattr(msg.document, "file_unique_id", None)
                )

                if not file_uid:
                    skipped_uid += 1
                    continue

                details = extract_details(caption)
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
                    caption=caption,
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
                        f"📈 Indexing Progress\n"
                        f"✅ Indexed: {indexed}\n"
                        f"⏩ Duplicates: {duplicates}\n"
                        f"❎ Skipped (no UID): {skipped_uid}\n"                       
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

        await mark_indexed_chat_async(target_chat_id, source_chat_id)
        await progress.edit_text(
            f"✅ Completed!\n\n📂 Indexed: <b>{indexed}</b>\n⏩ Duplicates: <b>{duplicates}</b>\n"
            f"❎ Skipped (no UID): <b>{skipped_uid}</b>\nUnsupported: {unsupported}\n⚠️ Failed: <b>{errors}</b>\n"
            f"Linked `{source_chat_id}` → `{target_chat_id}`"
        )

    except Exception as e:
        await progress.edit_text(f"❌ Error during indexing: {e}")
        logger.exception(e)

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
            f"🗑 MongoDB: Deleted <b>{mongo_deleted} records</b>\n"
            f"🧹 Redis: Deleted {redis_deleted} keys\n"
            f"🔗 Unlinked `{source_chat_id}` → `{target_chat_id}`"
        )
    except Exception as e:
        await message.reply_text(f"❌ Error: `{e}`")
