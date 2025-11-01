import os
import math
import re
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import TEXT
from bson import ObjectId

logger = logging.getLogger(__name__)

# ---------------- CONFIG ---------------- #
MONGO_URL = os.getenv(
    "MONGO_URL",
    "mongodb+srv://<username>:<password>@cluster.mongodb.net/?retryWrites=true&w=majority"
)
DB_NAME = os.getenv("DB_NAME", "MovieBotDB")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "movies")

# ---------------- CLIENT ---------------- #
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]


# ---------------- INDEX CREATION ---------------- #
async def ensure_indexes():
    """Create optimized text and field indexes for speed."""
    try:
        await collection.create_index(
            [("title", TEXT), ("caption", TEXT), ("codec", TEXT)],
            name="movie_text_index",
            default_language="english",
            background=True,
            weights={"title": 5, "caption": 1, "codec": 2},
        )

        for field in ["chat_id", "quality", "lang", "print", "season", "episode", "codec"]:
            await collection.create_index(field, background=True)

        logger.info("✅ Indexes ensured successfully")
    except Exception:
        logger.exception("Failed to create indexes")


# ---------------- HELPERS ---------------- #
def _safe_int(value):
    """Convert episodes/seasons to proper int or keep valid string."""
    try:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            val = value.strip()
            if re.match(r"^\d+$", val):
                return int(val)
            if "-" in val or "complete" in val.lower():
                return val  # keep as-is for cases like "1-12" or "Complete"
        return None
    except Exception:
        return None


# ---------------- CRUD ---------------- #
async def save_movie_async(chat_id: int, title: str = None, year: int = None,
                           quality: str = None, lang: str = None, print_type: str = None,
                           season=None, episode=None, codec: str = None,
                           caption: str = None, link: str = None):
    """Save one movie record."""
    try:
        doc = {
            "chat_id": int(chat_id),
            "title": title.strip() if title else None,
            "year": int(year) if year else None,
            "quality": quality,
            "lang": lang,
            "print": print_type,
            "season": _safe_int(season),
            "episode": _safe_int(episode),
            "codec": codec.strip() if codec else None,
            "caption": caption,
            "link": link,
        }

        clean_doc = {k: v for k, v in doc.items() if v is not None}
        result = await collection.insert_one(clean_doc)
        logger.info(f"✅ Movie saved: {title}")
        return str(result.inserted_id)
    except Exception:
        logger.exception("❌ save_movie_async failed")
        return None


async def delete_chat_data_async(chat_id: int):
    """Delete all movies of a given chat."""
    try:
        res = await collection.delete_many({"chat_id": int(chat_id)})
        logger.info(f"🗑️ Deleted {res.deleted_count} docs from chat {chat_id}")
        return res.deleted_count
    except Exception:
        logger.exception("❌ delete_chat_data_async failed")
        return 0


# ---------------- SEARCH ---------------- #
async def get_movies_async(chat_id: int, query: str, page: int = 1, limit: int = 100):
    """
    Smart hybrid search:
    - Uses $text index when available
    - Falls back to regex matching for flexibility
    - Optimized for speed + compatible with Redis cache
    """
    if not query or not query.strip():
        return {"results": [], "total": 0, "page": 1, "pages": 1}

    query = query.strip()
    words = [w for w in re.split(r"\s+", query) if w]
    skip = (page - 1) * limit

    text_filter = {"chat_id": int(chat_id), "$text": {"$search": query}}

    # Fallback regex filters for non-text index fields
    regex_filters = []
    for w in words:
        safe = re.escape(w)
        regex_filters.append({
            "$or": [
                {"title": {"$regex": safe, "$options": "i"}},
                {"quality": {"$regex": safe, "$options": "i"}},
                {"lang": {"$regex": safe, "$options": "i"}},
                {"print": {"$regex": safe, "$options": "i"}},
                {"caption": {"$regex": safe, "$options": "i"}},
                {"codec": {"$regex": safe, "$options": "i"}},
                {"season": {"$regex": safe, "$options": "i"}},
                {"episode": {"$regex": safe, "$options": "i"}},
            ]
        })

    # Final combined query
    final_filter = {"$and": [text_filter] + regex_filters} if regex_filters else text_filter

    projection = {
        "score": {"$meta": "textScore"},
        "title": 1, "year": 1, "quality": 1, "lang": 1,
        "print": 1, "codec": 1, "season": 1, "episode": 1,
        "caption": 1, "link": 1
    }

    try:
        cursor = (
            collection.find(final_filter, projection)
            .sort([("score", {"$meta": "textScore"})])
            .skip(skip)
            .limit(limit)
        )

        results = await cursor.to_list(length=limit)
        total = await collection.count_documents(final_filter)
        pages = math.ceil(total / limit) if total else 1

        logger.info(f"🔍 Found {len(results)} / {total} results for '{query}' in chat {chat_id}")
        return {"results": results, "total": total, "page": page, "pages": pages}

    except Exception:
        logger.exception("⚠️ get_movies_async failed, using regex fallback")

        # Regex fallback only
        fallback_filter = {"chat_id": int(chat_id), "$and": regex_filters}
        cursor = collection.find(fallback_filter).skip(skip).limit(limit)
        results = await cursor.to_list(length=limit)
        total = await collection.count_documents(fallback_filter)
        pages = math.ceil(total / limit) if total else 1
        return {"results": results, "total": total, "page": page, "pages": pages}


async def get_movie_by_id_async(movie_id: str):
    """Fetch single movie by ObjectId."""
    try:
        return await collection.find_one({"_id": ObjectId(movie_id)})
    except Exception:
        logger.exception("get_movie_by_id_async failed")
        return None


INDEXED_COLL = db["indexed_chats"]


async def mark_indexed_chat_async(target_chat: int, source_chat: int):
    """Link one target chat with a source chat."""
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
    """Remove mapping between target and source."""
    try:
        await INDEXED_COLL.delete_one({"target_chat": target_chat, "source_chat": source_chat})
        logger.info(f"Unlinked target {target_chat} from source {source_chat}")
    except Exception:
        logger.exception("unmark_indexed_chat_async failed")


async def get_targets_for_source_async(source_chat: int):
    """Return all target_chat IDs linked to a given source chat."""
    try:
        docs = await INDEXED_COLL.find({"source_chat": source_chat}, {"target_chat": 1}).to_list(length=None)
        return [d["target_chat"] for d in docs]
    except Exception:
        logger.exception("get_targets_for_source_async failed")
        return []


async def get_sources_for_target_async(target_chat: int):
    """Return all source_chat IDs linked to a given target chat."""
    try:
        docs = await INDEXED_COLL.find({"target_chat": target_chat}, {"source_chat": 1}).to_list(length=None)
        return [d["source_chat"] for d in docs]
    except Exception:
        logger.exception("get_sources_for_target_async failed")
        return []
