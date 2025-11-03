import re

async def ask_for_message_link_or_id(message, source_chat_id, ask_text):
    user_input = ask_text.strip()
    match = re.match(
        r"^(?:https?://)?t(?:elegram)?\.me/(?:c/)?([\w\d_]+)/(\d+)(?:\?.*)?$",
        user_input
    )

    if not match or not match.group(2):
        await message.reply("❌ Invalid link. It must include a message ID.")
        return None, None

    if match:
        part1, msg_id = match.groups()
        message_id = int(msg_id)

        if part1.isdigit():
            chat_id = int(f"-100{part1}")  # Private/supergroup chat
        else:
            chat_id = part1

    elif user_input.isdigit():
        chat_id = source_chat_id
        message_id = int(user_input)

    else:
        await message.reply("❌ Invalid input. Please send a valid message ID or link.")
        return None, None

    return chat_id, message_id
