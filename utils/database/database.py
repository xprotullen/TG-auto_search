# database_async.py
# Fully async MongoDB (motor) database helper — no umongo, optimized for large datasets (1M+ docs)

import os
import math
import re
import logging
from motor.motor_asyncio import AsyncIOMotorClient
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

# ---------------- CLIENT ---------------- #
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]


# ---------------- INDEX CREATION ---------------- #
async def ensure_indexes():
    """
    Create optimized indexes for search and speed.
    Run once at startup: await ensure_indexes()
    """
    coll = db[COLLECTION]

    try:
        # Drop old text indexes (avoid duplicates)
        async for idx in coll.list_indexes():
            if "text" in idx.get("name", ""):
                try:
                    await coll.drop_index(idx["name"])
                    logger.info(f"Dropped old text index: {idx['name']}")
                except Exception:
                    logger.exception("Failed to drop index %s", idx["name"])
    except Exception:
        logger.exception("Failed listing indexes")

    try:
        # Create fresh text index on title + caption
        await coll.create_index(
            [("title", TEXT), ("caption", TEXT)],
            name="movie_text_index",
            default_language="english",
            background=True,
            weights={"title": 5, "caption": 1}
        )
        logger.info("✅ Created text index: title + caption")

        # Single-field indexes for filtering
        await coll.create_index("chat_id", background=True)
        await coll.create_index("quality", background=True)
        await coll.create_index("print", background=True)
        await coll.create_index("lang", background=True)

        logger.info("✅ Created normal indexes: chat_id, quality, print, lang")
    except Exception:
        logger.exception("Failed creating indexes")


# ---------------- CRUD HELPERS ---------------- #
async def save_movie_async(chat_id: int, title: str = None, year: int = None,
                           quality: str = None, lang: list = None, print_type: str = None,
                           season: int = None, episode: int = None, codec: str = None,
                           caption: str = None, link: str = None):
    """
    Save one movie document.
    """
    try:
        doc = {
            "chat_id": int(chat_id),
            "title": title.strip() if title else None,
            "year": int(year) if year else None,
            "quality": quality,
            "lang": [l.strip() for l in lang] if isinstance(lang, (list, tuple)) else ([lang] if lang else None),
            "print": print_type,
            "season": int(season) if season else None,
            "episode": int(episode) if episode else None,
            "codec": codec, 
            "caption": caption,
            "link": link
        }
        res = await db[COLLECTION].insert_one(doc)
        return str(res.inserted_id)
    except Exception:
        logger.exception("save_movie_async failed")
        return None


async def delete_chat_data_async(chat_id: int):
    """
    Delete all documents for a given chat_id.
    """
    try:
        res = await db[COLLECTION].delete_many({"chat_id": int(chat_id)})
        return res.deleted_count
    except Exception:
        logger.exception("delete_chat_data_async failed")
        return 0


# ---------------- SEARCH ---------------- #
async def get_movies_async(chat_id: int, query: str, page: int = 1, limit: int = 10):
    """
    Super optimized hybrid search:
    - $text index (fast full-text)
    - AND regex match for extra precision
    - Paginated response
    """
    if not query or not query.strip():
        return {"results": [], "total": 0, "page": 1, "pages": 1}

    query = query.strip()
    words = [w for w in re.split(r"\s+", query) if w]
    skip = (page - 1) * limit
    coll = db[COLLECTION]

    base_filter = {"chat_id": int(chat_id), "$text": {"$search": query}}

    and_filters = []
    for word in words:
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

    final_filter = {"$and": [base_filter] + and_filters} if and_filters else base_filter

    projection = {
        "score": {"$meta": "textScore"},
        "title": 1, "year": 1, "quality": 1, "lang": 1, "print": 1, "caption": 1, "link": 1
    }

    try:
        cursor = coll.find(final_filter, projection)\
                     .sort([("score", {"$meta": "textScore"})])\
                     .skip(skip)\
                     .limit(limit)
        results = await cursor.to_list(length=limit)
        total = await coll.count_documents(final_filter)
        pages = math.ceil(total / limit) if total else 1

        return {"results": results, "total": total, "page": page, "pages": pages}
    except Exception:
        logger.exception("get_movies_async primary search failed, using regex fallback")
        # Regex-only fallback (slow)
        regex_filters = [
            {"$or": [
                {"title": {"$regex": re.escape(w), "$options": "i"}},
                {"quality": {"$regex": re.escape(w), "$options": "i"}},
                {"lang": {"$regex": re.escape(w), "$options": "i"}},
                {"print": {"$regex": re.escape(w), "$options": "i"}},
                {"caption": {"$regex": re.escape(w), "$options": "i"}}
            ]} for w in words
        ]
        fallback_filter = {"chat_id": int(chat_id), "$and": regex_filters}
        cursor = coll.find(fallback_filter).skip(skip).limit(limit)
        results = await cursor.to_list(length=limit)
        total = await coll.count_documents(fallback_filter)
        pages = math.ceil(total / limit) if total else 1
        return {"results": results, "total": total, "page": page, "pages": pages}


async def get_movie_by_id_async(movie_id: str):
    """Fetch single movie by ObjectId."""
    try:
        return await db[COLLECTION].find_one({"_id": ObjectId(movie_id)})
    except Exception:
        logger.exception("get_movie_by_id_async failed")
        return None

# ---------------- INDEXED CHAT MAPPING (for auto-sync) ---------------- #
INDEXED_COLL = db["indexed_chats"]


async def mark_indexed_chat_async(target_chat: int, source_chat: int):
    """
    Map one target chat to a source chat.
    Agar same mapping hai to upsert karega (replace karega duplicate nahi).
    """
    try:
        await INDEXED_COLL.update_one(
            {"target_chat": target_chat, "source_chat": source_chat},
            {"$set": {"target_chat": target_chat, "source_chat": source_chat}},
            upsert=True
        )
        logger.info(f"Linked target {target_chat} with source {source_chat}")
    except Exception:
        logger.exception("mark_indexed_chat_async failed")


async def unmark_indexed_chat_async(target_chat: int, source_chat: int):
    """
    Remove one mapping between target and source.
    """
    try:
        await INDEXED_COLL.delete_one({"target_chat": target_chat, "source_chat": source_chat})
        logger.info(f"Unlinked target {target_chat} from source {source_chat}")
    except Exception:
        logger.exception("unmark_indexed_chat_async failed")


async def get_targets_for_source_async(source_chat: int):
    """
    Return all target_chat IDs linked to given source chat.
    """
    try:
        docs = await INDEXED_COLL.find({"source_chat": source_chat}, {"target_chat": 1}).to_list(length=None)
        return [d["target_chat"] for d in docs]
    except Exception:
        logger.exception("get_targets_for_source_async failed")
        return []


async def get_sources_for_target_async(target_chat: int):
    """
    Return all source_chat IDs linked to given target chat.
    (Useful if you want to check what sources a target depends on)
    """
    try:
        docs = await INDEXED_COLL.find({"target_chat": target_chat}, {"source_chat": 1}).to_list(length=None)
        return [d["source_chat"] for d in docs]
    except Exception:
        logger.exception("get_sources_for_target_async failed")
        return []
