from pymongo import MongoClient
import os
from utils import extract_details

# ---------------- CONFIG ---------------- #
MONGO_URL = os.getenv("MONGO_URL", "mongodb+srv://<username>:<password>@cluster.mongodb.net/")
DB_NAME = "MovieBotDB"

client = MongoClient(MONGO_URL)
db = client[DB_NAME]
movies_col = db["movies"]

# Create indexes for faster queries
movies_col.create_index("chat_id")
movies_col.create_index("title")
movies_col.create_index("quality")
movies_col.create_index("language")
movies_col.create_index("season")
movies_col.create_index("episode")

# ---------------- DATABASE OPS ---------------- #
def save_movie(chat_id: int, link: str, caption: str):
    """
    Extract details from caption and save to DB.
    """
    details = extract_details(caption)
    details.update({"chat_id": chat_id, "link": link})
    movies_col.insert_one(details)
    return True

def delete_chat_data(chat_id: int):
    """
    Delete all records of a chat.
    """
    result = movies_col.delete_many({"chat_id": chat_id})
    return result.deleted_count

def get_movies(chat_id: int, query: str, page: int = 1, limit: int = 10):
    """
    Natural search with pagination.
    Splits query into words and searches across title, quality, language, print, and caption.
    """
    if not query:
        return []

    words = query.split()
    regex_filters = [{"$or": [
        {"title": {"$regex": word, "$options": "i"}},
        {"quality": {"$regex": word, "$options": "i"}},
        {"language": {"$regex": word, "$options": "i"}},
        {"print": {"$regex": word, "$options": "i"}},
        {"caption": {"$regex": word, "$options": "i"}}
    ]} for word in words]

    filters = {"chat_id": chat_id, "$and": regex_filters}

    skip = (page - 1) * limit
    results = list(movies_col.find(filters).skip(skip).limit(limit))
    total = movies_col.count_documents(filters)

    return {
        "results": results,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }
