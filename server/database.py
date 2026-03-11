import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Load from environment variable for production (Render/Railway), fallback to None if missing
MONGO_URL = os.getenv("MONGO_URI")
if not MONGO_URL:
    raise ValueError("MONGO_URI environment variable is required. Check your .env file or server settings.")

client = AsyncIOMotorClient(MONGO_URL)
db = client.katto_db

# Collections
profiles = db.profiles
users = db.users  # Auth: { username, hashed_password }
messages = db.messages  # { room, sender, content, timestamp }
friends = db.friends  # { user1, user2, status: 'pending'|'accepted' }
