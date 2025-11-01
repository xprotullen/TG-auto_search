from pymongo import MongoClient, TEXT
import os, math

# ---------------- CONFIG ---------------- #
MONGO_URL = os.getenv("MONGO_URL", "mongodb+srv://<username>:<password>@cluster.mongodb.net/")
DB_NAME = "MovieBotDB"

client = MongoClient(MONGO_URL)
db = client[DB_NAME]
movies_col = db["movies"]

# ---------------- OPTIMIZED INDEXES ---------------- #
# Drop existing text indexes to avoid conflict
for idx in movies_col.list_indexes():
    if "text" in idx["name"]:
        movies_col.drop_index(idx["name"])

# ✅ Use a single text index (MongoDB allows only one per collection)
movies_col.create_index(
    [("title", TEXT), ("caption", TEXT)],
    default_language="english",
    name="movie_text_index"
)

# ✅ Normal indexes for filters/pagination
movies_col.create_index("chat_id")
movies_col.create_index("lang")
movies_col.create_index("quality")

print("✅ Optimized indexes created: title+caption text, chat_id, lang, quality")

# ---------------- FUNCTIONS ---------------- #
def save_movie(chat_id, title, year=None, quality=None, lang=None,
               print_type=None, season=None, episode=None, caption=None, link=None):
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
    result = movies_col.delete_many({"chat_id": chat_id})
    return result.deleted_count


def get_movies(chat_id: int, query: str, page: int = 1, limit: int = 10):
    """
    Super-fast text search using MongoDB $text index.
    Works even on 5+ lakh docs efficiently.
    """
    if not query:
        return {"results": [], "total": 0, "page": 1, "pages": 1}

    skip = (page - 1) * limit

    # ⚡ Optimized search using MongoDB full-text engine
    cursor = movies_col.find(
        {"chat_id": chat_id, "$text": {"$search": query}},
        {"score": {"$meta": "textScore"}, "title": 1, "year": 1,
         "quality": 1, "lang": 1, "print": 1, "caption": 1, "link": 1}
    ).sort([("score", {"$meta": "textScore"})]).skip(skip).limit(limit)

    results = list(cursor)
    total = movies_col.count_documents({"chat_id": chat_id, "$text": {"$search": query}})
    pages = math.ceil(total / limit)

    return {"results": results, "total": total, "page": page, "pages": pages}


def get_movie_by_id(movie_id):
    from bson import ObjectId
    return movies_col.find_one({"_id": ObjectId(movie_id)})
