"""
Katto — FastAPI server
======================
Handles: auth, messages, friends, profiles, online presence,
         WebSocket chat + WebRTC signaling, voice-call session tracking.
"""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import profiles, users, messages, friends, voice_sessions

app = FastAPI(title="Katto", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AuthRequest(BaseModel):
    username: str
    password: str


class FriendRequest(BaseModel):
    from_user: str
    to_user: str


class ProfileUpdate(BaseModel):
    username: str
    bio:      Optional[str] = None
    avatar:   Optional[str] = None
    password: Optional[str] = None


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.post("/signup")
async def signup(req: AuthRequest):
    existing = await users.find_one({
        "username": {"$regex": f"^{req.username}$", "$options": "i"}
    })
    if existing:
        return {"success": False, "error": "Username already taken."}

    await users.insert_one({
        "username":        req.username,
        "hashed_password": hash_password(req.password),
    })
    await profiles.insert_one({
        "username": req.username,
        "bio":      "A mysterious Katto user.",
        "avatar":   "Classic",
        "status":   "online",
    })
    return {"success": True, "message": "Account created!"}


@app.post("/login")
async def login(req: AuthRequest):
    user = await users.find_one({
        "username": {"$regex": f"^{req.username}$", "$options": "i"}
    })
    if not user:
        return {"success": False, "error": "User not found."}
    if user["hashed_password"] != hash_password(req.password):
        return {"success": False, "error": "Wrong password."}
    return {"success": True, "message": f"Welcome back, {req.username}!"}


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

@app.get("/messages/{room}")
async def get_messages(room: str, limit: int = 50):
    cursor = messages.find({"room": room}).sort("timestamp", -1).limit(limit)
    msgs   = await cursor.to_list(length=limit)
    msgs.reverse()

    formatted = []
    for m in msgs:
        ts = m.get("timestamp")
        formatted.append({
            "sender":    m.get("sender"),
            "content":   m.get("content"),
            "room":      m.get("room"),
            "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else ts,
        })
    return {"success": True, "messages": formatted}


# ---------------------------------------------------------------------------
# Friends
# ---------------------------------------------------------------------------

@app.post("/friends/request")
async def send_friend_request(req: FriendRequest):
    if req.from_user.lower() == req.to_user.lower():
        return {"success": False, "error": "Cannot friend yourself."}

    target = await users.find_one({
        "username": {"$regex": f"^{req.to_user}$", "$options": "i"}
    })
    if not target:
        return {"success": False, "error": "User does not exist."}

    existing = await friends.find_one({"$or": [
        {"user1": {"$regex": f"^{req.from_user}$", "$options": "i"},
         "user2": {"$regex": f"^{req.to_user}$",   "$options": "i"}},
        {"user1": {"$regex": f"^{req.to_user}$",   "$options": "i"},
         "user2": {"$regex": f"^{req.from_user}$", "$options": "i"}},
    ]})
    if existing:
        return {"success": False, "error": "Friend request already exists or already friends."}

    await friends.insert_one({
        "user1":       req.from_user,
        "user2":       req.to_user,
        "status":      "pending",
        "action_user": req.from_user,
    })
    await send_to_user(req.to_user, {
        "type":      "friend_request",
        "from_user": req.from_user,
        "content":   f"New friend request from @{req.from_user}",
    })
    return {"success": True, "message": f"Friend request sent to {req.to_user}!"}


@app.post("/friends/accept")
async def accept_friend_request(req: FriendRequest):
    result = await friends.update_one(
        {"user1":  {"$regex": f"^{req.to_user}$",   "$options": "i"},
         "user2":  {"$regex": f"^{req.from_user}$", "$options": "i"},
         "status": "pending"},
        {"$set": {"status": "accepted"}},
    )
    if result.modified_count == 0:
        return {"success": False, "error": "No pending request found from that user."}

    base = {"type": "friend_accepted", "user1": req.from_user, "user2": req.to_user}
    await send_to_user(req.from_user, {**base, "content": f"You are now friends with @{req.to_user}"})
    await send_to_user(req.to_user,   {**base, "content": f"You are now friends with @{req.from_user}"})
    return {"success": True, "message": f"You are now friends with {req.to_user}!"}


@app.post("/friends/decline")
async def decline_friend_request(req: FriendRequest):
    result = await friends.delete_one({
        "user1":  {"$regex": f"^{req.to_user}$",   "$options": "i"},
        "user2":  {"$regex": f"^{req.from_user}$", "$options": "i"},
        "status": "pending",
    })
    if result.deleted_count == 0:
        return {"success": False, "error": "No pending request found."}
    return {"success": True, "message": "Friend request declined."}


@app.get("/friends/{username}")
async def get_friends(username: str):
    cursor = friends.find({"$or": [
        {"user1": {"$regex": f"^{username}$", "$options": "i"}},
        {"user2": {"$regex": f"^{username}$", "$options": "i"}},
    ]})
    friend_list      = await cursor.to_list(length=100)
    accepted         = []
    pending_incoming = []
    for f in friend_list:
        u1, u2 = f["user1"], f["user2"]
        if f["status"] == "accepted":
            accepted.append(u2 if u1.lower() == username.lower() else u1)
        elif f["status"] == "pending" and u2.lower() == username.lower():
            pending_incoming.append(u1)
    return {"success": True, "friends": accepted, "pending": pending_incoming}


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@app.get("/profile/{username}")
async def get_profile(username: str):
    profile = await profiles.find_one({
        "username": {"$regex": f"^{username}$", "$options": "i"}
    })
    if not profile:
        return {"success": False, "error": "Profile not found."}

    cursor        = friends.find({"$or": [
        {"user1": {"$regex": f"^{username}$", "$options": "i"}},
        {"user2": {"$regex": f"^{username}$", "$options": "i"}},
    ], "status": "accepted"})
    friends_count = len(await cursor.to_list(length=100))

    return {
        "success": True,
        "profile": {
            "username":      profile.get("username"),
            "bio":           profile.get("bio", "A mysterious Katto user."),
            "avatar":        profile.get("avatar", "Classic"),
            "friends_count": friends_count,
        },
    }


@app.post("/profile/update")
async def update_profile(req: ProfileUpdate):
    updates: dict = {}
    if req.bio    is not None: updates["bio"]    = req.bio
    if req.avatar is not None: updates["avatar"] = req.avatar

    if updates:
        await profiles.update_one(
            {"username": {"$regex": f"^{req.username}$", "$options": "i"}},
            {"$set": updates},
        )
    if req.password and req.password.strip():
        await users.update_one(
            {"username": {"$regex": f"^{req.username}$", "$options": "i"}},
            {"$set": {"hashed_password": hash_password(req.password)}},
        )
    return {"success": True, "message": "Profile updated successfully!"}


# ---------------------------------------------------------------------------
# Online presence
# ---------------------------------------------------------------------------

@app.get("/online")
async def get_online():
    online = _online_users()
    return {"success": True, "count": len(online), "users": online}


# ---------------------------------------------------------------------------
# Voice-call session endpoints
# ---------------------------------------------------------------------------

@app.get("/voice/sessions")
async def get_voice_sessions(limit: int = 20):
    """
    Most-recent voice sessions for the call-log panel.
    Schema per document:
      { room, participants:[{username,joined_at,left_at,duration_s}],
        started_at, ended_at }
    """
    cursor   = voice_sessions.find().sort("started_at", -1).limit(limit)
    sessions = await cursor.to_list(length=limit)

    def _fmt_ts(ts) -> Optional[str]:
        return ts.isoformat() if hasattr(ts, "isoformat") else ts

    formatted = []
    for s in sessions:
        parts = [
            {
                "username":   p.get("username"),
                "joined_at":  _fmt_ts(p.get("joined_at")),
                "left_at":    _fmt_ts(p.get("left_at")),
                "duration_s": p.get("duration_s"),
            }
            for p in s.get("participants", [])
        ]
        formatted.append({
            "session_id":   str(s["_id"]),
            "room":         s.get("room", "voice"),
            "participants": parts,
            "started_at":   _fmt_ts(s.get("started_at")),
            "ended_at":     _fmt_ts(s.get("ended_at")),
        })
    return {"success": True, "sessions": formatted}


@app.get("/voice/active")
async def get_active_voice():
    """Users currently in a voice call (ended_at is None)."""
    cursor  = voice_sessions.find({"ended_at": None})
    active  = await cursor.to_list(length=20)
    in_call = []
    for s in active:
        for p in s.get("participants", []):
            if p.get("left_at") is None:
                in_call.append({
                    "username":  p["username"],
                    "joined_at": p["joined_at"].isoformat()
                    if hasattr(p.get("joined_at"), "isoformat") else p.get("joined_at"),
                })
    return {"success": True, "in_call": in_call}


# ---------------------------------------------------------------------------
# WebSocket hub — chat + WebRTC signaling
# ---------------------------------------------------------------------------

# ws → username
active_connections: dict[WebSocket, str] = {}

# username → session ObjectId str (while in a call)
_voice_session_map: dict[str, str] = {}

# Message types routed peer-to-peer only — never broadcast, never persisted
_SIGNALING_TYPES = {
    "webrtc-offer",
    "webrtc-answer",
    "webrtc-ice-candidate",
    "webrtc-hangup",
}


def _online_users() -> list[str]:
    return list(active_connections.values())


async def broadcast(message: dict) -> None:
    payload = json.dumps(message)
    for ws in list(active_connections):
        try:
            await ws.send_text(payload)
        except Exception:
            active_connections.pop(ws, None)


async def send_to_user(username: str, message: dict) -> None:
    payload    = json.dumps(message)
    target_low = username.lower()
    for ws, user in list(active_connections.items()):
        if user.lower() == target_low:
            try:
                await ws.send_text(payload)
            except Exception:
                pass


# -- Voice DB helpers ---------------------------------------------------------

async def _voice_join(username: str, peer: str) -> None:
    """Record that username joined a voice call (with peer as the other party)."""
    now = _now()
    # Don't double-register the same user in the same session
    if username in _voice_session_map:
        return

    # Find an open session that already includes the peer
    session = await voice_sessions.find_one({
        "ended_at":                None,
        "participants.username":   peer,
    })

    if session:
        await voice_sessions.update_one(
            {"_id": session["_id"]},
            {"$push": {"participants": {
                "username":   username,
                "joined_at":  now,
                "left_at":    None,
                "duration_s": None,
            }}},
        )
        _voice_session_map[username] = str(session["_id"])
    else:
        # First caller — create a new session
        canon_room = f"voice:{'-'.join(sorted([username, peer]))}"
        result     = await voice_sessions.insert_one({
            "room":         canon_room,
            "participants": [{
                "username":   username,
                "joined_at":  now,
                "left_at":    None,
                "duration_s": None,
            }],
            "started_at": now,
            "ended_at":   None,
        })
        _voice_session_map[username] = str(result.inserted_id)


async def _voice_leave(username: str) -> None:
    """Stamp left_at + duration for username; close session if everyone left."""
    session_id = _voice_session_map.pop(username, None)
    if not session_id:
        return

    from bson import ObjectId

    now     = _now()
    session = await voice_sessions.find_one({"_id": ObjectId(session_id)})
    if not session:
        return

    new_parts = []
    for p in session.get("participants", []):
        if p["username"] == username and p.get("left_at") is None:
            joined = p.get("joined_at")
            dur    = int((now - joined).total_seconds()) if joined else None
            new_parts.append({**p, "left_at": now, "duration_s": dur})
        else:
            new_parts.append(p)

    all_left = all(p.get("left_at") is not None for p in new_parts)
    update   = {"$set": {"participants": new_parts}}
    if all_left:
        update["$set"]["ended_at"] = now

    await voice_sessions.update_one({"_id": ObjectId(session_id)}, update)

    # Push live update so every client refreshes the voice panel
    await broadcast({
        "type":       "voice_session_update",
        "session_id": session_id,
        "user_left":  username,
        "all_left":   all_left,
    })


# -- Main WebSocket endpoint --------------------------------------------------

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str) -> None:
    await websocket.accept()
    active_connections[websocket] = username
    await broadcast({"sender": "System", "content": f"{username} joined!", "room": "all"})

    try:
        while True:
            raw          = await websocket.receive_text()
            message_data = json.loads(raw)
            msg_type     = message_data.get("type", "message")

            # ------------------------------------------------------------------
            # WebRTC signaling — stamp sender, route to target only
            # ------------------------------------------------------------------
            if msg_type in _SIGNALING_TYPES:
                target = message_data.get("target", "")
                if not target:
                    continue

                message_data["from_user"] = username

                if msg_type == "webrtc-offer":
                    await _voice_join(username, target)
                    await broadcast({
                        "type":    "voice_user_joined",
                        "caller":  username,
                        "callee":  target,
                    })
                elif msg_type == "webrtc-answer":
                    # Callee accepted — record their join
                    await _voice_join(username, target)
                    await broadcast({
                        "type":    "voice_user_joined",
                        "caller":  target,
                        "callee":  username,
                    })
                elif msg_type == "webrtc-hangup":
                    await _voice_leave(username)
                    await broadcast({
                        "type":    "voice_user_left",
                        "user":    username,
                        "target":  target,
                    })

                await send_to_user(target, message_data)
                continue

            # ------------------------------------------------------------------
            # Typing indicator
            # ------------------------------------------------------------------
            if msg_type == "typing":
                await broadcast({
                    "type":   "typing",
                    "sender": "System",
                    "user":   username,
                    "room":   message_data.get("room", "#general"),
                })
                continue

            # ------------------------------------------------------------------
            # Regular chat message
            # ------------------------------------------------------------------
            room    = message_data.get("room", "#general")
            content = message_data.get("content", "")
            if content:
                await messages.insert_one({
                    "room":      room,
                    "sender":    username,
                    "content":   content,
                    "timestamp": _now(),
                })
            await broadcast({"sender": username, "content": content, "room": room})

    except WebSocketDisconnect:
        active_connections.pop(websocket, None)
        if username in _voice_session_map:
            await _voice_leave(username)
        await broadcast({"sender": "System", "content": f"{username} left.", "room": "all"})
    except Exception as exc:
        print(f"WS error ({username}): {exc}")
        active_connections.pop(websocket, None)
        if username in _voice_session_map:
            await _voice_leave(username)