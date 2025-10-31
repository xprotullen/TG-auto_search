from pyrogram import Client, filters
from database import add_index, delete_index, get_indexes

# /index <chat_id>
@Client.on_message(filters.command("index") & filters.group)
async def index_command(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/index chat_id`\nExample: `/index -10083839399`", quote=True)

    chat_id = int(message.command[1])
    await add_index(message.chat.id, chat_id)
    await message.reply_text(f"✅ Chat `{chat_id}` indexed successfully for this group.", quote=True)

# /delete <chat_id> or /delete (all)
@Client.on_message(filters.command("delete") & filters.group)
async def delete_command(client, message):
    if len(message.command) < 2:
        deleted = await delete_index(message.chat.id)
        return await message.reply_text("🗑️ All indexed chats deleted for this group." if deleted else "❌ No data found.", quote=True)

    chat_id = int(message.command[1])
    deleted = await delete_index(message.chat.id, chat_id)
    await message.reply_text("🗑️ Chat removed." if deleted else "❌ Chat ID not found.", quote=True)

# /showindex — see all indexed chats for this group
@Client.on_message(filters.command("showindex") & filters.group)
async def show_indexes(client, message):
    indexes = await get_indexes(message.chat.id)
    if not indexes:
        await message.reply_text("❌ No indexed chats found. Use `/index chat_id` first.", quote=True)
    else:
        text = "📚 Indexed Chats:\n" + "\n".join([f"- `{x}`" for x in indexes])
        await message.reply_text(text, quote=True)
