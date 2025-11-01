import math
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from utils.database import get_movies_async as get_movies
from html import escape

CACHE = {}  # (chat_id, query) → {"user_id": int, "data": {...}, "message_id": int}
RESULTS_PER_PAGE = 10
CACHE_LIMIT = 50  # avoid memory overflow


@Client.on_message(filters.group & filters.text)
async def search_movie(client, message):
    query = message.text.strip()
    chat_id = int(message.chat.id)

    if not query or query.startswith(("/", ".", "!", ",")):
        return

    # Get results from DB
    search_data = await get_movies(chat_id, query, page=1, limit=RESULTS_PER_PAGE)
    movies = search_data["results"]
    total = search_data["total"]
    pages = search_data["pages"]

    if not movies:
        return await message.reply_text("❌ No results found.")

    # Maintain limited cache
    if len(CACHE) > CACHE_LIMIT:
        CACHE.pop(next(iter(CACHE)))

    CACHE[(chat_id, query)] = {
        "user_id": message.from_user.id,
        "data": search_data,
    }

    sent = await send_results(
        message, query, chat_id, 1, movies, total, pages
    )

    CACHE[(chat_id, query)]["message_id"] = sent.id


async def send_results(message, query, chat_id, page, movies, total, pages, edit=False):
    """
    Send or edit the same message with movie search results.
    """
    text = f"🎬 <b>Results for:</b> <code>{escape(query)}</code>\n"
    text += f"📄 Page {page}/{pages} — Total: {total}\n\n"

    for i, movie in enumerate(movies, start=(page - 1) * RESULTS_PER_PAGE + 1):
        title = movie.get("title") or "Unknown"
        year = movie.get("year") or ""
        quality = movie.get("quality") or ""
        print_type = movie.get("print") or ""
        link = movie.get("link") or ""
        caption = f"{title} {year} {quality} {print_type}".strip()

        text += f"{i}. <b>{escape(caption)}</b>\n"
        if link:
            text += f"🔗 <a href='{escape(link)}'>Link</a>\n\n"

    # Pagination buttons
    buttons = []
    row = []
    if page > 1:
        row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page|{chat_id}|{query}|{page-1}"))
    if page < pages:
        row.append(InlineKeyboardButton("Next ➡️", callback_data=f"page|{chat_id}|{query}|{page+1}"))
    if row:
        buttons.append(row)

    markup = InlineKeyboardMarkup(buttons) if buttons else None

    if edit:
        return await message.edit_text(
            text,
            reply_markup=markup,
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML
        )
    else:
        return await message.reply_text(
            text,
            reply_markup=markup,
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML
        )


@Client.on_callback_query(filters.regex(r"^page\|"))
async def pagination_handler(client, query: CallbackQuery):
    try:
        _, chat_id, search_query, page = query.data.split("|", 3)
        chat_id = int(chat_id)
        page = int(page)
    except Exception:
        return await query.answer("⚠️ Invalid data.", show_alert=True)

    cached = CACHE.get((chat_id, search_query))
    if not cached:
        return await query.answer("⚠️ Data expired, please search again.", show_alert=True)

    # Restrict to same user
    if query.from_user.id != cached["user_id"]:
        return await query.answer("❌ You didn’t request this search!", show_alert=True)

    # Get new page
    data = await get_movies(chat_id, search_query, page=page, limit=RESULTS_PER_PAGE)
    movies = data["results"]
    total = data["total"]
    pages = data["pages"]

    if not movies:
        return await query.answer("⚠️ No more results.", show_alert=True)

    await query.answer()
    await send_results(query.message, search_query, chat_id, page, movies, total, pages, edit=True)
