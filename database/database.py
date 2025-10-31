import logging
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
from info import DATABASE_URI, DATABASE_NAME

# Setup logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Setup MongoDB client
client = AsyncIOMotorClient(DATABASE_URI)
db = client[DATABASE_NAME]


class GroupDatabase:
    def __init__(self):
        self.groups = db["groups"]
        self.movies = db["movies"]

    async def add_group(self, group_id, source_chat_id, added_by):
        """Add a new group to the database."""
        group_data = {
            "group_id": group_id,
            "source_chat_id": source_chat_id,
            "added_by": added_by,
            "added_date": datetime.now(),
            "is_active": True
        }

        try:
            await self.groups.insert_one(group_data)
            return True
        except DuplicateKeyError:
            # If group already exists, update it
            await self.groups.update_one(
                {"group_id": group_id},
                {"$set": group_data}
            )
            return True
        except Exception as e:
            logger.error(f"Error adding group: {e}")
            return False

    async def remove_group(self, group_id):
        """Remove group and its associated movies from the database."""
        try:
            # Remove the group
            group_result = await self.groups.delete_one({"group_id": group_id})
            # Remove all movies for this group
            await self.movies.delete_many({"group_id": group_id})
            return group_result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error removing group: {e}")
            return False

    async def get_group(self, group_id):
        """Get group data."""
        return await self.groups.find_one({"group_id": group_id})

    async def add_movie(self, group_id, movie_data):
        """Add a movie to the database."""
        movie_data["group_id"] = group_id
        movie_data["added_date"] = datetime.now()

        try:
            # Create unique index to avoid duplicates
            await self.movies.create_index(
                [("movie_name", 1), ("group_id", 1)], unique=True
            )
            await self.movies.insert_one(movie_data)
            return True
        except DuplicateKeyError:
            logger.warning(f"Movie already exists: {movie_data.get('movie_name')}")
            return True
        except Exception as e:
            logger.error(f"Error adding movie: {e}")
            return False

    async def search_movies(self, group_id, query, limit=50):
        """Search movies in database with advanced regex search."""
        try:
            # Ensure text index for efficient searching
            await self.movies.create_index(
                [("movie_name", "text"), ("year", "text")]
            )

            regex_pattern = f".*{query}.*"
            search_filter = {
                "group_id": group_id,
                "$or": [
                    {"movie_name": {"$regex": regex_pattern, "$options": "i"}},
                    {"caption": {"$regex": regex_pattern, "$options": "i"}},
                    {"year": {"$regex": regex_pattern, "$options": "i"}},
                ]
            }

            cursor = self.movies.find(search_filter).limit(limit)
            movies = await cursor.to_list(length=limit)
            return movies
        except Exception as e:
            logger.error(f"Error searching movies: {e}")
            return []

    async def get_group_movies_count(self, group_id):
        """Get count of movies for a specific group."""
        return await self.movies.count_documents({"group_id": group_id})


# Global database instance
database = GroupDatabase()
