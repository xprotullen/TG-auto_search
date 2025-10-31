from pymongo import MongoClient
import os

MONGO_URL = os.getenv("MONGO_URL", "mongodb+srv://<username>:<password>@cluster.mongodb.net/")
DB_NAME = "MovieBotDB"

client = MongoClient(MONGO_URL)
db = client[DB_NAME]
movies_col = db["movies"]

# ---------------- Functions ---------------- #

def save_movie(chat_id, link, caption):
    movie_data = {
        "chat_id": chat_id,
        "link": link,
        "caption": caption
    }
    movies_col.insert_one(movie_data)

def delete_chat_data(chat_id):
    result = movies_col.delete_many({"chat_id": chat_id})
    return result.deleted_count

def get_movies(chat_id: int, query: str):
    """
    Advanced natural search:
    - Splits query into words (e.g. 'mirage 480p')
    - Matches all words case-insensitively in caption
    - Returns a list of matching movie documents
    """
    if not query:
        return []

    # Split the query into separate words
    words = query.split()

    # Build AND filters for all words
    regex_filters = [{"caption": {"$regex": word, "$options": "i"}} for word in words]

    filters = {"chat_id": chat_id, "$and": regex_filters}

    results = list(movies_col.find(filters))
    return results
