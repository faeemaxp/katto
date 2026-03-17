"""
Minimal WebSocket test server to diagnose connection issues on Windows
This server does NOT require MongoDB - pure WebSocket testing.

Run: python test_ws.py
Then connect client to: ws://localhost:9000/ws/testuser
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import json
import asyncio
import uvicorn

app = FastAPI()

# Add CORS for WebSocket compatibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_connections = {}

@app.get("/health")
async def health():
    """Simple health check"""
    return {"status": "ok", "websocket_url": "ws://127.0.0.1:9000/ws/{username}"}

@app.get("/online")
async def online():
    """Return online users"""
    count = len(active_connections)
    users = list(active_connections.values())
    return {"success": True, "count": count, "users": users}

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    """WebSocket endpoint - simple test version"""
    print(f"[WS] New connection attempt from {username}")
    
    try:
        print(f"[WS] Accepting WebSocket for {username}...")
        await websocket.accept()
        print(f"[WS] ✓ WebSocket accepted for {username}")
        
        active_connections[websocket] = username
        
        # Send welcome message
        await websocket.send_text(json.dumps({
            "type": "system",
            "sender": "System",
            "content": f"Welcome {username}! WebSocket connected.",
            "room": "all"
        }))
        
        # Keep connection alive and receive messages
        while True:
            try:
                data = await websocket.receive_text()
                print(f"[WS] Received from {username}: {data[:100]}")
                
                # Echo it back
                await websocket.send_text(json.dumps({
                    "type": "echo",
                    "sender": username,
                    "content": f"Echo: {data}",
                    "room": "all"
                }))
            except Exception as e:
                print(f"[WS] Error receiving from {username}: {type(e).__name__}: {e}")
                break
                
    except WebSocketDisconnect:
        print(f"[WS] Client {username} disconnected")
        active_connections.pop(websocket, None)
    except Exception as e:
        print(f"[WS] ✗ ERROR with {username}: {type(e).__name__}: {e}")
        active_connections.pop(websocket, None)
        try:
            await websocket.close()
        except:
            pass

if __name__ == "__main__":
    print("\n" + "="*60)
    print("TEST WEBSOCKET SERVER (No Database Required)")
    print("="*60)
    print("Starting on http://127.0.0.1:9000")
    print("WebSocket endpoint: ws://127.0.0.1:9000/ws/{username}")
    print("Health check: http://127.0.0.1:9000/health")
    print("="*60 + "\n")
    
    uvicorn.run(app, host="127.0.0.1", port=9000)
