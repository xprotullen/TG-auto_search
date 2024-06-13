# (c) @TheLx0980
# Year : 2023

import re
from pyrogram import filters, enums, Client
from bot import Wroxen as Bot
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
import logging
from html import escape

DATABASE = {}
MEDIA_FILTER = enums.MessagesFilter.VIDEO 

@Client.on_message(filters.command("add_search_cnl") & filters.reply)
async def add_channel_handler(client, message):
    chat_id = message.chat.id
    group_id = message.chat.id
    channel_id = message.reply_to_message.forward_from_chat.id

    userid = message.from_user.id if message.from_user else None
    if not userid:
        return await message.reply(f"आप एक अज्ञात व्यवस्थापक हैं।")

    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return

    st = await client.get_chat_member(chat_id, userid)
    if (
        st.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]
    ):
        return

    # जांचें कि समूह ID पहले से ही डेटाबेस में मौजूद है
    if is_group_in_database(group_id):
        # अगर चैनल ID पहले से मौजूद है, तो एक त्रुटि संदेश भेजें
        if get_channel_id(group_id) == channel_id:
            await client.send_message(
                chat_id=chat_id,
                text="समूह के लिए चैनल आईडी पहले से ही जोड़ दिया गया है।"
            )
        else:
            add_channel(group_id, channel_id)
            await client.send_message(
                chat_id=chat_id,
                text="समूह के लिए चैनल आईडी अपडेट की गई है।"
            )
    else:
        add_channel(group_id, channel_id)
        await client.send_message(
            chat_id=chat_id,
            text="चैनल आईडी को डेटाबेस में जोड़ दिया गया है।"
        )

@Client.on_message(filters.command("delete_search_cnl") & filters.group)
async def delete_channel_handler(client, message):
    chat_id = message.chat.id
    group_id = message.chat.id
    userid = message.from_user.id if message.from_user else None
    if not userid:
        return await message.reply(f"आप एक अज्ञात व्यवस्थापक हैं।")

    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return

    st = await client.get_chat_member(chat_id, userid)
    if (
        st.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]
    ):
        return
        
    if is_group_in_database(group_id):
        delete_channel(group_id)
        await client.send_message(
            chat_id=chat_id,
            text="समूह और उससे संबंधित चैनल को डेटाबेस से हटा दिया गया है।"
        )
    else:
        await client.send_message(
            chat_id=chat_id,
            text="समूह डेटाबेस में मौजूद नहीं है।"
        )



@Client.on_message(filters.group & filters.text)
async def filter(client: Client, message: Message):
    if re.findall("((^\/|^,|^!|^\.|^[\U0001F600-\U000E007F]).*)", message.text):
        return

    if len(message.text) > 2:
        query = message.text        
        group_id = message.chat.id
        channel_id = get_channel_id(group_id)

        if not channel_id:
            return
   
        msgs = []
        search_id = int(channel_id)
        async for msg in client.USER.search_messages(search_id, query=query, filter=MEDIA_FILTER):
            caption = msg.caption
            link = msg.link
            movie_name, year, quality = extract_movie_details(caption)
            movie_text = f"<b>{escape(movie_name)} ({year}) {quality}</b>\n<b>Link:</b> {link}"
            msgs.append(movie_text)

        if not msgs:
            return

        page = 1
        await send_result_message(client, message, query, msgs, page)

async def send_result_message(client, message, query, movies, page, result_message_id=None):
    total_results = len(movies)

    if total_results <= 10:
        # Less than or equal to 10 results, no need for pagination
        movies_page = movies
        reply_markup = None
    else:
        results_per_page = 10
        start_index = (page - 1) * results_per_page
        end_index = page * results_per_page
        movies_page = movies[start_index:end_index]
        reply_markup = generate_inline_keyboard(query, total_results, page)

    result_message = generate_result_message(query, movies_page, page)

    if result_message_id:
        # Edit the existing message
        await client.edit_message_text(
            chat_id=message.chat.id,
            message_id=result_message_id,
            text=result_message,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=reply_markup
        )
    else:
        # Send a new message
        sent_message = await message.reply_text(
            result_message,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=reply_markup
        )
        result_message_id = sent_message.id

    DATABASE[query] = {
        'message_id': result_message_id,
        'movies': movies,
        'page': page
    }

def generate_inline_keyboard(query, total_results, current_page):
    buttons = []

    if total_results > current_page * 10:
        next_page_button = InlineKeyboardButton(
            text='Next Page',
            callback_data=f'next_page:{query}:{current_page + 1}'
        )
        buttons.append(next_page_button)

    if current_page > 1:
        previous_page_button = InlineKeyboardButton(
            text='Previous Page',
            callback_data=f'previous_page:{query}:{current_page - 1}'
        )
        buttons.append(previous_page_button)

    inline_keyboard = [buttons]
    return InlineKeyboardMarkup(inline_keyboard) 


def generate_result_message(query, movies, page):
    start_number = (page - 1) * 10 + 1
    result_message = f"Here are the results for <b>{escape(query)}</b>:\n\n"
    for i, movie_text in enumerate(movies, start=start_number):
        result_message += f"{i}. {movie_text}\n\n"
    return result_message


def extract_movie_details(caption):
    # Movie name patterns
    name_patterns = [
        r"^([^.]*?)\s\d{4}",  # Pattern 1: Movie name followed by year (excluding ".")
        r"^([^.]*?)\s(\(\d{4}\))",  # Pattern 2: Movie name followed by (year) (excluding ".")
        r"^([^.]*?)\s\d{3,4}p",  # Pattern 3: Movie name followed by quality (excluding ".")
        r"^([^.]*?)(?=\s\d{4})",  # Pattern 20: Movie name until a space followed by 4 digits (year) (excluding ".")
    ]
    
    # Year patterns
    year_patterns = [
        r"\((\d{4})\)",  # Pattern 1: (year)
        r"(\d{4})",  # Pattern 2: year
        r"\d{2}(\d{2})\b",  # Pattern 3: last 2 digits of the year
        r"(\d{4})\b",  # Pattern 4: year
        r"(19\d{2}|20\d{2})",  # Pattern 5: year between 1900 and 2099
        r"(\d{2})(\d{2})\b",  # Pattern 6: 4-digit year split into two groups of 2 digits.
        r"\b(20[012]\d|19[5-9]\d)\b",  # Pattern 20: year between 1950 and 2099
        r"Movie :-\s(.*?)\(\d{4}\)"
    ]
    
    # Quality patterns
    quality_patterns = [
        r"\d{3,4}p",  # Pattern 1: 3 or 4 digits followed by 'p'
        r"\b(4|8|10)K\b",  # Pattern 2: 4K, 8K, 10K
        r"\b(FHD|HD|SD)\b",  # Pattern 3: FHD, HD, SD
    ]

    movie_name = "Unknown"
    year = "Unknown"
    quality = "Unknown"

    for name_pattern in name_patterns:
        movie_name_match = re.search(name_pattern, caption)
        if movie_name_match:
            movie_name = movie_name_match.group(1).replace(".", "")
            break

    for year_pattern in year_patterns:
        year_match = re.search(year_pattern, caption)
        if year_match:
            year = year_match.group(1)
            break

    for quality_pattern in quality_patterns:
        quality_match = re.search(quality_pattern, caption)
        if quality_match:
            quality = quality_match.group()
            break

    return movie_name, year, quality
