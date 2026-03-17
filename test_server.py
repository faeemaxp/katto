#!/usr/bin/env python
"""
Diagnostic script to test server and database connectivity
"""
import asyncio
import httpx
import websockets
import json

DEFAULT_SERVER = "http://katto-server-production.up.railway.app"
LOCAL_SERVER = "http://localhost:8000"

async def test_server_http(url: str) -> bool:
    """Test if server responds to HTTP"""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            # Try to access the online endpoint
            response = await client.get(f"{url}/online")
            data = response.json()
            print(f"✓ HTTP connection successful: {url}")
            print(f"  Response: {data}")
            return True
    except Exception as e:
        print(f"✗ HTTP connection failed: {url}")
        print(f"  Error: {e}")
        return False

async def test_server_ws(url: str, username: str = "test_user") -> bool:
    """Test if server accepts WebSocket connections"""
    ws_url = url.replace("http://", "ws://").replace("https://", "wss://")
    try:
        async with websockets.connect(f"{ws_url}/ws/{username}", ping_interval=None) as websocket:
            print(f"✓ WebSocket connection successful: {ws_url}")
            # Try to send a simple message
            await websocket.send(json.dumps({"content": "test", "room": "#general"}))
            response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
            print(f"  Received: {response}")
            return True
    except Exception as e:
        print(f"✗ WebSocket connection failed: {ws_url}")
        print(f"  Error: {e}")
        return False

async def test_auth(url: str) -> bool:
    """Test if server accepts auth requests"""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                f"{url}/login",
                json={"username": "test", "password": "test"}
            )
            data = response.json()
            print(f"✓ Auth endpoint accessible: {url}/login")
            print(f"  Response: {data}")
            return True
    except Exception as e:
        print(f"✗ Auth endpoint failed: {url}/login")
        print(f"  Error: {e}")
        return False

async def main():
    print("=" * 60)
    print("KATTO SERVER DIAGNOSTIC TEST")
    print("=" * 60)
    print()
    
    print("Testing LOCAL server (localhost:8000):")
    print("-" * 60)
    local_http = await test_server_http(LOCAL_SERVER)
    await asyncio.sleep(0.5)
    if local_http:
        await test_auth(LOCAL_SERVER)
    print()
    
    print("Testing PRODUCTION server (Railway):")
    print("-" * 60)
    prod_http = await test_server_http(DEFAULT_SERVER)
    await asyncio.sleep(0.5)
    if prod_http:
        await test_auth(DEFAULT_SERVER)
    print()
    
    print("=" * 60)
    if local_http:
        print("✓ Local server is RUNNING")
    else:
        print("✗ Local server is NOT running")
    
    if prod_http:
        print("✓ Production server is RUNNING")
    else:
        print("✗ Production server is NOT running")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
