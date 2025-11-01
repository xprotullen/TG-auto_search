import math
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from utils.database import get_movies
from html import escape

CACHE = {}  # (chat_id, query) → {"user_id": int, "data": {...}}

RESULTS_PER_PAGE = 10


@Client.on_message(filters.group & filters.text)
async def search_movie(client, message):
    query = message.text.strip()
    chat_id = int(message.chat.id)

    if not query or query.startswith(("/", ".", "!", ",")):
        return  # ignore commands or stickers

    # Fetch page 1 results
    search_data = get_movies(chat_id, query, page=1, limit=RESULTS_PER_PAGE)
    movies = search_data["results"]
    total = search_data["total"]
    pages = search_data["pages"]

    if not movies:
        return

    # Cache user_id + search data
    CACHE[(chat_id, query)] = {"user_id": message.from_user.id, "data": search_data}

    sent = await send_results(
        client, message, query, chat_id, 1, movies, total, pages
    )

    # Store message_id for validation
    CACHE[(chat_id, query)]["message_id"] = sent.id


async def send_results(client, message, query, chat_id, page, movies, total, pages, edit=False):
    """
    Send or edit search results message with inline pagination.
    """
    text = f"🎬 <b>Results for:</b> <code>{escape(query)}</code>\n"
    text += f"📄 Page {page}/{pages} — Total: {total}\n\n"

    for i, movie in enumerate(movies, start=(page - 1) * RESULTS_PER_PAGE + 1):
        title = movie.get("title") or "Unknown"
        quality = movie.get("quality") or ""
        lang = movie.get("lang") or ""   # ✅ changed from 'language' (as per new DB)
        year = movie.get("year") or ""
        link = movie.get("link") or ""

        text += f"{i}. <b>{escape(title)}</b> ({year}) {quality} {lang}\n"
        if link:
            text += f"🔗 [Link]({link})\n\n"

    # ✅ Pagination buttons only if total > RESULTS_PER_PAGE
    buttons = []
    if total > RESULTS_PER_PAGE:
        row = []
        if page > 1:
            row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page:{chat_id}:{query}:{page-1}"))
        if page < pages:
            row.append(InlineKeyboardButton("Next ➡️", callback_data=f"page:{chat_id}:{query}:{page+1}"))
        if row:
            buttons.append(row)

    markup = InlineKeyboardMarkup(buttons) if buttons else None

    if edit:
        # Edit same message
        return await message.edit_text(
            text,
            reply_markup=markup,
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML
        )
    else:
        # Send new message
        return await message.reply_text(
            text,
            reply_markup=markup,
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML
        )


@Client.on_callback_query(filters.regex(r"^page:"))
async def pagination_handler(client, query: CallbackQuery):
    """
    Handle pagination navigation — only the requester can use buttons.
    """
    _, chat_id, text, page = query.data.split(":")
    chat_id = int(chat_id)
    page = int(page)

    cached = CACHE.get((chat_id, text))
    if not cached:
        return await query.answer("⚠️ Data expired, please search again.", show_alert=True)

    # ✅ Restrict button use to same user only
    user_id = cached["user_id"]
    if query.from_user.id != user_id:
        return await query.answer("❌ You didn’t request this search!", show_alert=True)

    # Get fresh page from DB for accuracy
    data = get_movies(chat_id, text, page=page, limit=RESULTS_PER_PAGE)
    movies = data["results"]
    total = data["total"]
    pages = data["pages"]

    await query.answer()  # remove loading spinner
    await send_results(client, query.message, text, chat_id, page, movies, total, pages, edit=True)
