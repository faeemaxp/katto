from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import json
import hashlib
from datetime import datetime
from typing import Optional

from database import profiles, users, messages, friends

app = FastAPI()

# ==========================================
# AUTH MODELS
# ==========================================
class AuthRequest(BaseModel):
    username: str
    password: str

class FriendRequest(BaseModel):
    from_user: str
    to_user: str

class ProfileUpdate(BaseModel):
    username: str
    bio: Optional[str] = None
    avatar: Optional[str] = None
    password: Optional[str] = None

def hash_password(password: str) -> str:
    """Simple SHA-256 hash for passwords."""
    return hashlib.sha256(password.encode()).hexdigest()

# ==========================================
# AUTH ENDPOINTS
# ==========================================
@app.post("/signup")
async def signup(req: AuthRequest):
    existing = await users.find_one({"username": req.username})
    if existing:
        return {"success": False, "error": "Username already taken."}
    
    await users.insert_one({
        "username": req.username,
        "hashed_password": hash_password(req.password)
    })
    # Also create a profile
    await profiles.insert_one({
        "username": req.username,
        "bio": "A mysterious Katto user.",
        "followers": [],
        "status": "online"
    })
    return {"success": True, "message": "Account created!"}

@app.post("/login")
async def login(req: AuthRequest):
    user = await users.find_one({"username": req.username})
    if not user:
        return {"success": False, "error": "User not found."}
    if user["hashed_password"] != hash_password(req.password):
        return {"success": False, "error": "Wrong password."}
    return {"success": True, "message": f"Welcome back, {req.username}!"}

# ==========================================
# NEW ENDPOINTS: MESSAGES, FRIENDS, PROFILE
# ==========================================

@app.get("/messages/{room}")
async def get_messages(room: str, limit: int = 50):
    # Fetch latest 50 messages for a room, sorted by timestamp ascending
    cursor = messages.find({"room": room}).sort("timestamp", -1).limit(limit)
    msgs = await cursor.to_list(length=limit)
    msgs.reverse() # We want oldest first for chat history
    
    formatted = []
    for msg in msgs:
        ts = msg.get("timestamp")
        formatted.append({
            "sender": msg.get("sender"),
            "content": msg.get("content"),
            "room": msg.get("room"),
            "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else ts
        })
    return {"success": True, "messages": formatted}

@app.post("/friends/request")
async def send_friend_request(req: FriendRequest):
    if req.from_user == req.to_user:
        return {"success": False, "error": "Cannot friend yourself."}
    
    # Check if target user exists
    target = await users.find_one({"username": req.to_user})
    if not target:
        return {"success": False, "error": "User does not exist."}
        
    existing = await friends.find_one({
        "$or": [
            {"user1": req.from_user, "user2": req.to_user},
            {"user1": req.to_user, "user2": req.from_user}
        ]
    })
    
    if existing:
        return {"success": False, "error": "Friend request already exists or already friends."}
        
    await friends.insert_one({
        "user1": req.from_user,
        "user2": req.to_user,
        "status": "pending",
        "action_user": req.from_user # who sent it
    })
    return {"success": True, "message": f"Friend request sent to {req.to_user}!"}

@app.post("/friends/accept")
async def accept_friend_request(req: FriendRequest):
    # from_user is the one accepting, to_user is the one who sent it
    result = await friends.update_one(
        {"user1": req.to_user, "user2": req.from_user, "status": "pending"},
        {"$set": {"status": "accepted"}}
    )
    if result.modified_count == 0:
        return {"success": False, "error": "No pending request found from that user."}
    return {"success": True, "message": f"You are now friends with {req.to_user}!"}

@app.get("/friends/{username}")
async def get_friends(username: str):
    cursor = friends.find({
        "$or": [{"user1": username}, {"user2": username}]
    })
    friend_list = await cursor.to_list(length=100)
    
    accepted = []
    pending_incoming = []
    for f in friend_list:
        other_user = f["user2"] if f["user1"] == username else f["user1"]
        if f["status"] == "accepted":
            accepted.append(other_user)
        elif f["status"] == "pending" and f.get("action_user") != username:
            pending_incoming.append(other_user)
            
    return {"success": True, "friends": accepted, "pending": pending_incoming}

@app.get("/profile/{username}")
async def get_profile(username: str):
    profile = await profiles.find_one({"username": username})
    if not profile:
        return {"success": False, "error": "Profile not found."}
        
    cursor = friends.find({
        "$or": [{"user1": username}, {"user2": username}],
        "status": "accepted"
    })
    friend_list = await cursor.to_list(length=100)
    friends_count = len(friend_list)

    return {
        "success": True,
        "profile": {
            "username": profile.get("username"),
            "bio": profile.get("bio", "A mysterious Katto user."),
            "avatar": profile.get("avatar", ""),
            "friends_count": friends_count,
        }
    }

@app.post("/profile/update")
async def update_profile(req: ProfileUpdate):
    updates = {}
    if req.bio is not None:
        updates["bio"] = req.bio
    if req.avatar is not None:
        updates["avatar"] = req.avatar
        
    if updates:
        await profiles.update_one({"username": req.username}, {"$set": updates})
        
    if req.password is not None and req.password.strip():
        await users.update_one(
            {"username": req.username},
            {"$set": {"hashed_password": hash_password(req.password)}}
        )
        
    return {"success": True, "message": "Profile updated successfully!"}

# ==========================================
# WEBSOCKET CHAT
# ==========================================
active_connections: set[WebSocket] = set()

async def broadcast(message: dict):
    """Safely sends a message to everyone, skipping dead connections."""
    message_json = json.dumps(message)
    for connection in list(active_connections):
        try:
            await connection.send_text(message_json)
        except Exception:
            active_connections.discard(connection)

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await websocket.accept()
    active_connections.add(websocket)

    await broadcast({"sender": "System", "content": f"{username} joined!", "room": "all"})

    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            room = message_data.get("room", "#general")
            content = message_data.get("content", "")
            
            # Save to database
            if content:
                await messages.insert_one({
                    "room": room,
                    "sender": username,
                    "content": content,
                    "timestamp": datetime.utcnow()
                })
            
            # Broadcast to everyone (clients filter by room)
            await broadcast({
                "sender": username,
                "content": content,
                "room": room
            })
    except WebSocketDisconnect:
        active_connections.discard(websocket)
        await broadcast({"sender": "System", "content": f"{username} left.", "room": "all"})
    except Exception as e:
        print(f"Error with {username}: {e}")
        active_connections.discard(websocket)
