#!/usr/bin/env python
"""
Integration test for Katto client
Tests the full login flow without launching the full UI
"""
import asyncio
import httpx
import json

async def test_full_flow():
    """Test signup, login, and profile fetch"""
    server = "http://localhost:8000"
    test_user = "testuser123"
    test_pass = "password123"
    
    print("=" * 60)
    print("KATTO CLIENT INTEGRATION TEST")
    print("=" * 60)
    print()
    
    # Test 1: Signup
    print("1. Testing SIGNUP...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{server}/signup",
                json={"username": test_user, "password": test_pass}
            )
            data = response.json()
            print(f"   Status: {response.status_code}")
            print(f"   Response: {data}")
            if not data.get("success"):
                print("   (User might already exist, continuing...)")
    except Exception as e:
        print(f"   ✗ ERROR: {e}")
        return False
    print()
    
    # Test 2: Login
    print("2. Testing LOGIN...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{server}/login",
                json={"username": test_user, "password": test_pass}
            )
            data = response.json()
            print(f"   Status: {response.status_code}")
            print(f"   Response: {data}")
            if not data.get("success"):
                print("   ✗ LOGIN FAILED")
                return False
    except Exception as e:
        print(f"   ✗ ERROR: {e}")
        return False
    print()
    
    # Test 3: Get profile
    print("3. Testing PROFILE FETCH...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{server}/profile/{test_user}"
            )
            data = response.json()
            print(f"   Status: {response.status_code}")
            print(f"   Response: {json.dumps(data, indent=2)}")
            if not data.get("success"):
                print("   ✗ PROFILE FETCH FAILED")
                return False
    except Exception as e:
        print(f"   ✗ ERROR: {e}")
        return False
    print()
    
    # Test 4: Get messages
    print("4. Testing MESSAGE HISTORY...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{server}/messages/%23general"
            )
            data = response.json()
            print(f"   Status: {response.status_code}")
            print(f"   Messages count: {len(data.get('messages', []))}")
            if not data.get("success"):
                print("   ✗ MESSAGE FETCH FAILED")
                return False
    except Exception as e:
        print(f"   ✗ ERROR: {e}")
        return False
    print()
    
    print("=" * 60)
    print("✓ ALL TESTS PASSED!")
    print("=" * 60)
    print()
    print("You can now run the client with:")
    print("  cd client && python app.py")
    return True

if __name__ == "__main__":
    asyncio.run(test_full_flow())
