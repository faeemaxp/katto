from motor.motor_asyncio import AsyncIOMotorClient

# Note: In a real project, use: MONGO_URL = os.getenv("MONGO_URL")
MONGO_URL = "mongodb+srv://faeemscience:naeem123hasnain@cluster0.kxa6ib3.mongodb.net/"
client = AsyncIOMotorClient(MONGO_URL)
db = client.katto_db

# Collections
profiles = db.profiles
users = db.users  # Auth: { username, hashed_password }
messages = db.messages  # { room, sender, content, timestamp }
friends = db.friends  # { user1, user2, status: 'pending'|'accepted' }
