import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.getenv("MONGO_URI")
if not MONGO_URL:
    raise ValueError(
        "MONGO_URI environment variable is required. "
        "Check your .env file or server settings."
    )

client = AsyncIOMotorClient(MONGO_URL)
db     = client.katto_db

# Collections
users          = db.users           # { username, hashed_password }
profiles       = db.profiles        # { username, bio, avatar, status }
messages       = db.messages        # { room, sender, content, timestamp }
friends        = db.friends         # { user1, user2, status, action_user }
voice_sessions = db.voice_sessions  # { room, participants:[{username,joined_at,left_at,duration_s}],
                                    #   started_at, ended_at }