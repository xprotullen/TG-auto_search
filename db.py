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

def get_movies(chat_id, query):
    # Case-insensitive search in captions
    return list(movies_col.find({
        "chat_id": chat_id,
        "caption": {"$regex": query, "$options": "i"}
    }))
