from pymongo import MongoClient
import os

# ---------------- CONFIG ---------------- #
MONGO_URL = os.getenv("MONGO_URL", "mongodb+srv://<username>:<password>@cluster.mongodb.net/")
DB_NAME = "MovieBotDB"

client = MongoClient(MONGO_URL)
db = client[DB_NAME]
movies_col = db["movies"]

# ---------------- SAFE INDEX CREATION ---------------- #
# Drop existing text index (if any) to prevent conflict
for idx in movies_col.list_indexes():
    if "text" in idx["name"]:
        movies_col.drop_index(idx["name"])

# Create new text index on updated fields
movies_col.create_index([
    ("title", "text"),
    ("quality", "text"),
    ("lang", "text"),  # ✅ now matches your current schema
    ("print", "text"),
    ("caption", "text")
])

print("✅ Text index recreated successfully on: title, quality, lang, print, caption")


# ---------------- FUNCTIONS ---------------- #

def save_movie(chat_id, title, year=None, quality=None, lang=None,
               print_type=None, season=None, episode=None, caption=None, link=None):
    """
    Save one movie or episode info to DB.
    """
    movie_data = {
        "chat_id": chat_id,
        "title": title.strip() if title else None,
        "year": year,
        "quality": quality,
        "lang": lang,
        "print": print_type,
        "season": season,
        "episode": episode,
        "caption": caption,
        "link": link
    }
    movies_col.insert_one(movie_data)
    return True


def delete_chat_data(chat_id: int):
    """
    Delete all movies belonging to a specific chat.
    """
    result = movies_col.delete_many({"chat_id": chat_id})
    return result.deleted_count


def get_movies(chat_id: int, query: str, page: int = 1, limit: int = 10):
    """
    Advanced natural search with pagination.
    - Splits query into words
    - Matches across title, quality, lang, print, and caption (case-insensitive)
    """
    if not query:
        return {"results": [], "total": 0, "page": 1, "pages": 1}

    words = query.split()

    regex_filters = [
        {"$or": [
            {"title": {"$regex": word, "$options": "i"}},
            {"quality": {"$regex": word, "$options": "i"}},
            {"lang": {"$regex": word, "$options": "i"}},
            {"print": {"$regex": word, "$options": "i"}},
            {"caption": {"$regex": word, "$options": "i"}}
        ]}
        for word in words
    ]

    filters = {"chat_id": chat_id, "$and": regex_filters}

    skip = (page - 1) * limit
    cursor = movies_col.find(filters).skip(skip).limit(limit)

    results = list(cursor)
    total = movies_col.count_documents(filters)

    return {
        "results": results,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }


def get_movie_by_id(movie_id):
    """
    Fetch single movie by its MongoDB _id.
    """
    from bson import ObjectId
    return movies_col.find_one({"_id": ObjectId(movie_id)})
