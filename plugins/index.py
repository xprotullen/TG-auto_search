import asyncio
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, MessagesFilter, MessageMediaType
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.handlers import MessageHandler

from utils.database import (
    save_movie_async,
    delete_chat_data_async,
    mark_indexed_chat_async,
    unmark_indexed_chat_async,
    get_targets_for_source_async
)
from utils import extract_details

INDEXING = {}
BATCH_SIZE = 50


# ---------------- /index COMMAND ---------------- #
@Client.on_message(filters.command("index"))
async def index_chat(client, message):
    """
    /index <target_chat_id> <source_chat_id>
    Example: /index -1001234 -1005678
    """
    parts = message.text.split()
    if len(parts) < 3:
        return await message.reply_text("Usage: `/index target_chat_id source_chat_id`")

    target_chat_id = int(parts[1])
    source_chat_id = int(parts[2])
    user_id = message.from_user.id

    try:
        bot_member = await client.get_chat_member(target_chat_id, "me")
        if bot_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return await message.reply_text("❌ Bot must be admin in target chat!")
    except Exception as e:
        return await message.reply_text(f"❌ Can't verify bot admin in target chat: {e}")

    # ✅ Check USER admin in target chat
    try:
        user_member = await client.get_chat_member(target_chat_id, user_id)
        if user_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return await message.reply_text("❌ You must be admin in target chat to start indexing!")
    except Exception as e:
        return await message.reply_text(f"❌ Can't verify your admin rights in target chat: {e}")

    # ✅ Check BOT admin in source chat
    try:
        bot_member_source = await client.get_chat_member(source_chat_id, "me")
        if bot_member_source.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return await message.reply_text("❌ Bot must be admin in source chat to fetch messages!")
    except Exception as e:
        return await message.reply_text(f"❌ Can't verify bot in source chat: {e}")

    # ✅ Check USERBOT member in source chat
    try:
        userbot_member = await client.USER.get_chat_member(source_chat_id, "me")
        if userbot_member.status not in [
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
            ChatMemberStatus.MEMBER
        ]:
            return await message.reply_text("❌ Userbot must be at least a member in source chat!")
    except Exception as e:
        return await message.reply_text(f"❌ Userbot can't access source chat: {e}")

    # ✅ Ask skip count
    ask_msg = await message.reply_text("⏭ Kitne messages skip karne hain? (Reply with number, or wait 30s for 0)", quote=True)
    try:
        reply_msg = await ask_user_for_reply(client, message.chat.id, user_id, timeout=30)
        # optionally delete the prompt and the reply (if you want)
        await ask_msg.delete()
        try:
            await reply_msg.delete()
        except Exception:
            pass

        # Validate reply: try to parse int
        text = (reply_msg.text or "").strip()
        try:
            skip_count = int(text)
            if skip_count < 0:
                skip_count = 0
        except Exception:
            skip_count = 0  # fallback if user sent non-int
    except asyncio.TimeoutError:
        skip_count = 0
        await ask_msg.edit_text("⚠️ No reply, skip=0 set automatically")

    # ✅ Prepare progress
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_index_{user_id}")]
    ])
    progress = await message.reply_text(
        f"📦 Indexing started...\nFrom `{source_chat_id}` → `{target_chat_id}`\nSkip: `{skip_count}`",
        reply_markup=keyboard
    )

    INDEXING[user_id] = True
    indexed = 0
    errors = 0

    try:
        async for msg in client.USER.search_messages(
            source_chat_id,
            filter=MessagesFilter.EMPTY,  # Fetch all messages
            offset=skip_count
        ):
            if not INDEXING.get(user_id):
                await progress.edit_text("🚫 Indexing cancelled.")
                return

            # We only want video or document
            if msg.media not in [MessageMediaType.VIDEO, MessageMediaType.DOCUMENT]:
                continue

            if not msg.caption:
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
                    caption=msg.caption,
                    link=msg.link
                )
                indexed += 1
                if indexed % BATCH_SIZE == 0:
                    await asyncio.sleep(2)
                    await progress.edit_text(
                        f"📈 Indexed: {indexed}\n⚠️ Failed: {errors}\n"
                        f"From `{source_chat_id}` → `{target_chat_id}`",
                        reply_markup=keyboard
                    )
            except Exception as inner_e:
                errors += 1
                print(f"⚠️ Skipped: {inner_e}")

        # ✅ Mark mapping
        await mark_indexed_chat_async(target_chat_id, source_chat_id)

        await progress.edit_text(
            f"✅ Completed!\n📂 Indexed: **{indexed}**\n⚠️ Failed: **{errors}**\n"
            f"Linked `{source_chat_id}` → `{target_chat_id}`"
        )

    except Exception as e:
        await progress.edit_text(f"❌ Error: {e}")

    finally:
        INDEXING.pop(user_id, None)


# ---------------- CANCEL INDEX ---------------- #
@Client.on_callback_query(filters.regex(r"cancel_index_(\d+)"))
async def cancel_index_callback(client, callback_query):
    user_id = int(callback_query.matches[0].group(1))
    INDEXING[user_id] = False
    await callback_query.answer("Cancelled!", show_alert=True)
    await callback_query.message.edit_text("🚫 Indexing cancelled.")


# ---------------- AUTO INDEX NEW MEDIA ---------------- #
@Client.on_message(filters.video)
async def auto_index_new_post(client, message):
    """
    When new media posted in indexed source chat → auto-save in all linked targets.
    """
    from_chat = message.chat.id
    try:
        targets = await get_targets_for_source_async(from_chat)
        if not targets:
            return  # not indexed source

        details = extract_details(message.caption or "")

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
                caption=message.caption,
                link=message.link
            )
            print(f"✅ Auto-synced new post from {from_chat} → {target_chat}")

    except Exception as e:
        print(f"⚠️ Auto index error: {e}")


# ---------------- /delete COMMAND ---------------- #
@Client.on_message(filters.command("delete"))
async def delete_indexed_pair(client, message):
    """
    /delete <target_chat_id> <source_chat_id>
    Removes mapping & deletes records for that target.
    """
    parts = message.text.split()
    if len(parts) < 3:
        return await message.reply_text("Usage: `/delete target_chat_id source_chat_id`")

    target_chat_id = int(parts[1])
    source_chat_id = int(parts[2])

    try:
        deleted = await delete_chat_data_async(target_chat_id)
        await unmark_indexed_chat_async(target_chat_id, source_chat_id)
        await message.reply_text(
            f"🗑 Deleted **{deleted}** records for `{target_chat_id}` "
            f"and removed link with `{source_chat_id}`"
        )
    except Exception as e:
        await message.reply_text(f"❌ Error: `{e}`")


async def ask_user_for_reply(client, chat_id: int, user_id: int, timeout: int = 30):
    """
    Ask the user to reply in the same chat and wait for one message from that user.
    Returns the Message object or raises asyncio.TimeoutError on timeout.
    This registers a temporary MessageHandler and removes it when done.
    """

    loop = asyncio.get_event_loop()
    fut = loop.create_future()

    async def _on_message(c, m):
        # ensure same chat and same user and it is not a command starting with /
        if m.chat and m.chat.id == chat_id and m.from_user and m.from_user.id == user_id:
            # Accept anything (you can add validation here)
            if not fut.done():
                fut.set_result(m)

    handler = MessageHandler(_on_message, filters.chat(chat_id) & filters.user(user_id))
    client.add_handler(handler)

    try:
        msg = await asyncio.wait_for(fut, timeout=timeout)
        return msg
    finally:
        # cleanup handler even on timeout / exception
        try:
            client.remove_handler(handler)
        except Exception:
            pass
