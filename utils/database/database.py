import os
import math
import re
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import TEXT
from bson import ObjectId
from info import MONGO_URL, COLLECTION_NAME, DB_NAME

logger = logging.getLogger(__name__)

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]
INDEXED_COLL = db["indexed_chats"]


async def drop_existing_indexes():
    """Drop all existing indexes safely."""
    try:
        existing = await collection.index_information()
        for name in list(existing.keys()):
            if name != "_id_":
                await collection.drop_index(name)

        existing_idx = await INDEXED_COLL.index_information()
        for name in list(existing_idx.keys()):
            if name != "_id_":
                await INDEXED_COLL.drop_index(name)

        logger.info("🧹 Dropped all old indexes successfully")
    except Exception as e:
        logger.exception(f"Failed to drop indexes: {e}")


async def ensure_indexes():
    """Ensure indexes exist with correct definitions."""
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

        await collection.create_index(
            [("chat_id", 1), ("file_unique_id", 1)],
            unique=True,
            background=True,
            name="unique_file_per_chat"
        )

        await INDEXED_COLL.create_index("target_chat", background=True)
        await INDEXED_COLL.create_index("source_chat", background=True)
        await INDEXED_COLL.create_index(
            [("target_chat", 1), ("source_chat", 1)],
            unique=True,
            background=True
        )

        logger.info("✅ Indexes ensured successfully")
    except Exception:
        logger.exception("Failed to create indexes")


async def rebuild_indexes():
    """Drop and recreate all indexes (clean rebuild)."""
    try:
        await drop_existing_indexes()
        await ensure_indexes()
        logger.info("🔄 Rebuilt all MongoDB indexes successfully")
    except Exception as e:
        logger.exception(f"Rebuild indexes failed: {e}")


def _safe_int(value):
    """Convert episodes/seasons to int or keep valid string."""
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
                return val
        return None
    except Exception:
        return None


async def save_movie_async(chat_id: int, title: str = None, year: int = None,
                           quality: str = None, lang: str = None, print_type: str = None,
                           season=None, episode=None, codec: str = None,
                           caption: str = None, link: str = None,
                           file_unique_id: str = None):

    try:
        if not file_unique_id:
            logger.warning("⚠️ Skipped: Missing file_unique_id.")
            return "error"

        existing = await collection.find_one({
            "chat_id": int(chat_id),
            "file_unique_id": file_unique_id
        })
        if existing:
            logger.info(f"⏩ Duplicate skipped ({file_unique_id}) in chat {chat_id}")
            return "duplicate"

        doc = {
            "chat_id": int(chat_id),
            "file_unique_id": file_unique_id,
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
        await collection.insert_one(clean_doc)
        logger.info(f"✅ Saved: {title or 'Untitled'} ({chat_id})")
        return "saved"

    except Exception as e:
        if "duplicate key error" in str(e).lower():
            logger.info(f"⚠️ Duplicate prevented for {file_unique_id}")
            return "duplicate"
        logger.exception("❌ save_movie_async failed")
        return "error"


async def delete_chat_data_async(chat_id: int):
    """Delete all records for a specific chat."""
    try:
        query = {"chat_id": int(chat_id)}
        count = await collection.count_documents(query)
        if count == 0:
            logger.info(f"⚠️ No records found for chat {chat_id}")
            return 0

        res = await collection.delete_many(query)
        logger.info(f"🗑️ Deleted {res.deleted_count}/{count} docs for chat {chat_id}")
        return res.deleted_count
    except Exception as e:
        logger.exception(f"❌ delete_chat_data_async failed: {e}")
        return 0


async def get_movies_async(chat_id: int, query: str, page: int = 1, limit: int = 100):
    """Full-text + regex hybrid search."""
    if not query or not query.strip():
        return {"results": [], "total": 0, "page": 1, "pages": 1}

    query = query.strip()
    words = [w for w in re.split(r"\s+", query) if w]
    skip = (page - 1) * limit

    text_filter = {"chat_id": int(chat_id), "$text": {"$search": query}}
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
            .sort([
                ("score", {"$meta": "textScore"}),
                ("season", 1),
                ("episode", 1)
            ])
            .skip(skip)
            .limit(limit)
        )
        results = await cursor.to_list(length=limit)
        total = await collection.count_documents(final_filter)
        pages = math.ceil(total / limit) or 1
        logger.info(f"🔍 Found {len(results)}/{total} results for '{query}' in chat {chat_id}")
        return {"results": results, "total": total, "page": page, "pages": pages}

    except Exception as e:
        logger.exception(f"⚠️ Text search failed ({e}), fallback to regex")
        fallback_filter = {"chat_id": int(chat_id), "$and": regex_filters}
        cursor = (
            collection.find(fallback_filter)
            .sort([("season", 1), ("episode", 1)])
            .skip(skip)
            .limit(limit)
        )
        results = await cursor.to_list(length=limit)
        total = await collection.count_documents(fallback_filter)
        pages = math.ceil(total / limit) or 1
        return {"results": results, "total": total, "page": page, "pages": pages}


async def mark_indexed_chat_async(target_chat: int, source_chat: int):
    """Link one target chat with one source."""
    try:
        await INDEXED_COLL.update_one(
            {"target_chat": target_chat, "source_chat": source_chat},
            {"$set": {"target_chat": target_chat, "source_chat": source_chat}},
            upsert=True
        )
        logger.info(f"🔗 Linked target {target_chat} with source {source_chat}")
    except Exception:
        logger.exception("mark_indexed_chat_async failed")


async def unmark_indexed_chat_async(target_chat: int, source_chat: int = None):
    """Remove mapping(s) for a target-source pair or entire target."""
    try:
        if source_chat:
            result = await INDEXED_COLL.delete_one(
                {"target_chat": target_chat, "source_chat": source_chat}
            )
            logger.info(f"❌ Unlinked target {target_chat} from source {source_chat} ({result.deleted_count} removed)")
        else:
            result = await INDEXED_COLL.delete_many({"target_chat": target_chat})
            logger.info(f"❌ Unlinked all mappings for target {target_chat} ({result.deleted_count} removed)")
    except Exception:
        logger.exception("unmark_indexed_chat_async failed")


async def is_source_linked_to_target(target_chat: int, source_chat: int):
    try:
        doc = await INDEXED_COLL.find_one(
            {"target_chat": target_chat, "source_chat": source_chat},
            {"_id": 1}
        )
        return bool(doc)
    except Exception as e:
        logger.exception("get_sources_for_target_async failed")
        return False

async def is_source_in_db(source_chat: int) -> bool:
    """Get all targets linked to a source."""
    try:
        docs = await INDEXED_COLL.find(
            {"source_chat": source_chat}, {"target_chat": 1}
        ).to_list(length=None)
        return [d["target_chat"] for d in docs]
    except Exception:
        logger.exception("is_source_in_db failed")
        return []
        
async def is_chat_linked_async(target_chat: int) -> bool:
    """Check if target chat is already linked."""
    try:
        doc = await INDEXED_COLL.find_one({"target_chat": target_chat})
        return bool(doc)
    except Exception:
        logger.exception("is_chat_linked_async failed")
        return False
