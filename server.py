from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from motor.motor_asyncio import AsyncIOMotorClient
import json
import asyncio

# 1. DATABASE SETUP
# Note: In a real project, use: MONGO_URL = os.getenv("MONGO_URL")
MONGO_URL = "mongodb+srv://faeemscience:naeem123hasnain@cluster0.kxa6ib3.mongodb.net/"
client = AsyncIOMotorClient(MONGO_URL)
db = client.katto_db
profiles = db.profiles 

app = FastAPI()

# We use a set() instead of a list[] because it's faster for removing items
active_connections: set[WebSocket] = set()

async def broadcast(message: dict):
    """Safely sends a message to everyone, skipping dead connections."""
    message_json = json.dumps(message)
    # We create a copy of the set to avoid "size changed during iteration" errors
    for connection in list(active_connections):
        try:
            await connection.send_text(message_json)
        except Exception:
            # If sending fails, the connection is dead. Remove it.
            active_connections.remove(connection)

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await websocket.accept()
    active_connections.add(websocket)
    
    # 2. PROFILE LOGIC
    user = await profiles.find_one({"username": username})
    if not user:
        new_profile = {
            "username": username,
            "bio": "A mysterious Katto user.",
            "followers": [],
            "status": "online"
        }
        await profiles.insert_one(new_profile)

    # 3. JOIN ANNOUNCEMENT
    await broadcast({"sender": "System", "content": f"{username} joined!"})

    try:
        while True:
            # Wait for message from client
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            # 4. CHAT BROADCAST
            await broadcast({
                "sender": username, 
                "content": message_data.get("content", "")
            })

    except WebSocketDisconnect:
        active_connections.remove(websocket)
        await broadcast({"sender": "System", "content": f"{username} left."})
    except Exception as e:
        print(f"Error with {username}: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)