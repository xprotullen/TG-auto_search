# database_async.py
# Async MongoDB (motor) + umongo model + optimized search helpers
# Usage: import functions and await them inside your async bot handlers

import os
import math
import re
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from umongo import Instance, Document, fields
from pymongo import TEXT, ASCENDING
from bson import ObjectId

logger = logging.getLogger(__name__)

# ---------------- CONFIG ---------------- #
MONGO_URL = os.getenv(
    "MONGO_URL",
    "mongodb+srv://<username>:<password>@cluster.mongodb.net/?retryWrites=true&w=majority"
)
DB_NAME = os.getenv("DB_NAME", "MovieBotDB")
COLLECTION = os.getenv("COLLECTION_NAME", "movies")

# ---------------- CLIENT / UMONGO SETUP ---------------- #
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# umongo instance
instance = Instance(db)


# ---------------- MODEL ---------------- #
@instance.register
class Movie(Document):
    # store minimal necessary fields, keep types simple for indexing
    chat_id = fields.IntField(required=True)
    title = fields.StrField(allow_none=True)
    year = fields.IntField(allow_none=True)
    quality = fields.StrField(allow_none=True)
    lang = fields.ListField(fields.StrField(), allow_none=True)   # list of langs
    print = fields.StrField(attribute="print", allow_none=True)
    season = fields.IntField(allow_none=True)
    episode = fields.IntField(allow_none=True)
    caption = fields.StrField(allow_none=True)
    link = fields.StrField(allow_none=True)

    class Meta:
        collection_name = COLLECTION
        # simple indexes defined here; text index created below via motor to avoid conflicts
        indexes = [
            ("chat_id", ASCENDING),
            ("quality", ASCENDING),
            # Note: text index must be created with create_index([...], text=True)
        ]


# Ensure model is initialized
Movies = Movie.collection  # motor collection object via umongo


# ---------------- INDEX CREATION (safe) ---------------- #
async def ensure_indexes():
    """
    Create optimized indexes:
    - Single compound text index on title + caption (one text index per collection)
    - Single-field indexes for chat_id, lang (as text/normal), quality, print
    Run this once at bot startup (await ensure_indexes()).
    """
    # Drop existing text indexes safely to prevent conflicts
    async for idx in db[COLLECTION].list_indexes():
        name = idx.get("name", "")
        if "text" in name:
            try:
                await db[COLLECTION].drop_index(name)
                logger.info(f"Dropped old text index: {name}")
            except Exception:
                logger.exception("Failed to drop index %s", name)

    # Create text index on title + caption (single text index)
    try:
        await db[COLLECTION].create_index(
            [("title", TEXT), ("caption", TEXT)],
            name="movie_text_index",
            default_language="english",
            background=True,
            weights={"title": 5, "caption": 1}
        )
        logger.info("Created text index: title+caption")
    except Exception:
        logger.exception("Failed creating text index")

    # Normal indexes for faster filtering
    try:
        await db[COLLECTION].create_index("chat_id", background=True)
        await db[COLLECTION].create_index("quality", background=True)
        await db[COLLECTION].create_index("print", background=True)
        # lang as array field: index either as simple ascending or text depending on queries
        await db[COLLECTION].create_index("lang", background=True)
        logger.info("Created normal indexes: chat_id, quality, print, lang")
    except Exception:
        logger.exception("Failed creating normal indexes")


# ---------------- CRUD / SEARCH HELPERS ---------------- #
async def save_movie_async(chat_id: int, title: str = None, year: int = None,
                           quality: str = None, lang: list = None, print_type: str = None,
                           season: int = None, episode: int = None, caption: str = None,
                           link: str = None):
    """
    Save a single movie doc asynchronously.
    lang: list[str] recommended (e.g. ["Hindi", "English"])
    Returns inserted_id or None on failure.
    """
    try:
        doc = {
            "chat_id": int(chat_id),
            "title": title.strip() if title else None,
            "year": int(year) if year else None,
            "quality": quality,
            "lang": [l for l in lang] if isinstance(lang, (list, tuple)) else ([lang] if lang else None),
            "print": print_type,
            "season": int(season) if season is not None else None,
            "episode": int(episode) if episode is not None else None,
            "caption": caption,
            "link": link
        }
        res = await db[COLLECTION].insert_one(doc)
        return res.inserted_id
    except Exception:
        logger.exception("save_movie_async failed")
        return None


async def delete_chat_data_async(chat_id: int):
    """
    Delete all documents for a chat_id.
    Returns deleted count.
    """
    try:
        res = await db[COLLECTION].delete_many({"chat_id": int(chat_id)})
        return res.deleted_count
    except Exception:
        logger.exception("delete_chat_data_async failed")
        return 0


async def get_movies_async(chat_id: int, query: str, page: int = 1, limit: int = 10):
    """
    Optimized hybrid search:
    1) Use $text full-text index (fast) to prefilter.
    2) Enforce AND-style word matching across key fields using case-insensitive regex.
    3) Return paginated results with textScore sorting.

    Suitable for large datasets (100k -> 1M+), provided indexes exist.
    """
    if not query or not query.strip():
        return {"results": [], "total": 0, "page": 1, "pages": 1}

    query = query.strip()
    words = [w for w in re.split(r"\s+", query) if w]
    skip = (page - 1) * limit

    # Step A: base fast full-text match
    base_filter = {"chat_id": int(chat_id), "$text": {"$search": query}}

    # Step B: enforce that each separate word appears in at least one of the searchable fields
    and_filters = []
    for word in words:
        # escape special regex characters in the word
        safe = re.escape(word)
        and_filters.append({
            "$or": [
                {"title": {"$regex": safe, "$options": "i"}},
                {"quality": {"$regex": safe, "$options": "i"}},
                {"lang": {"$regex": safe, "$options": "i"}},
                {"print": {"$regex": safe, "$options": "i"}},
                {"caption": {"$regex": safe, "$options": "i"}}
            ]
        })

    # final compound filter
    final_filter = {"$and": [base_filter] + and_filters} if and_filters else base_filter

    # projection: include score for sorting
    projection = {
        "score": {"$meta": "textScore"},
        "title": 1, "year": 1, "quality": 1, "lang": 1, "print": 1, "caption": 1, "link": 1
    }

    try:
        cursor = db[COLLECTION].find(final_filter, projection).sort([("score", {"$meta": "textScore"})]).skip(skip).limit(limit)
        results = await cursor.to_list(length=limit)
        total = await db[COLLECTION].count_documents(final_filter)
        pages = math.ceil(total / limit) if total else 1

        return {"results": results, "total": total, "page": page, "pages": pages}
    except Exception:
        # If $text is not supported or errors, fallback to safe regex-only query (slower)
        logger.exception("get_movies_async primary search failed, falling back to regex-only")
        # Build regex-only AND filter across fields
        regex_filters = [
            {"$or": [
                {"title": {"$regex": re.escape(w), "$options": "i"}},
                {"quality": {"$regex": re.escape(w), "$options": "i"}},
                {"lang": {"$regex": re.escape(w), "$options": "i"}},
                {"print": {"$regex": re.escape(w), "$options": "i"}},
                {"caption": {"$regex": re.escape(w), "$options": "i"}}
            ]} for w in words
        ]
        try:
            fallback_filter = {"chat_id": int(chat_id), "$and": regex_filters}
            cursor = db[COLLECTION].find(fallback_filter).skip(skip).limit(limit)
            results = await cursor.to_list(length=limit)
            total = await db[COLLECTION].count_documents(fallback_filter)
            pages = math.ceil(total / limit) if total else 1
            return {"results": results, "total": total, "page": page, "pages": pages}
        except Exception:
            logger.exception("get_movies_async fallback also failed")
            return {"results": [], "total": 0, "page": page, "pages": 1}


async def get_movie_by_id_async(movie_id: str):
    try:
        return await db[COLLECTION].find_one({"_id": ObjectId(movie_id)})
    except Exception:
        logger.exception("get_movie_by_id_async failed")
        return None
