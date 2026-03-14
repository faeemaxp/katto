# Katto Server Setup Guide

## Problem: `MONGO_URI environment variable is required`

The server needs MongoDB to run. You have 3 options:

---

## Option 1: Use MongoDB Atlas Cloud (Recommended - Free)

### Step 1: Create a free MongoDB Atlas account
1. Go to https://www.mongodb.com/cloud/atlas
2. Click "Start Free"
3. Create an account with your email

### Step 2: Create a cluster
1. After login, click "Create a Deployment"
2. Select "Free" tier
3. Choose your region
4. Click "Create Deployment"

### Step 3: Get connection string
1. In the Atlas dashboard, click "Connect"
2. Choose "Drivers"
3. Select "Python" and version 4.0+
4. Copy the connection string (looks like: `mongodb+srv://username:password@cluster.mongodb.net/myapp?retryWrites=true&w=majority`)

### Step 4: Create .env file
Create a file `server/.env`:
```
MONGO_URI=mongodb+srv://YOUR_USERNAME:YOUR_PASSWORD@YOUR_CLUSTER.mongodb.net/katto_db?retryWrites=true&w=majority
```

Replace:
- `YOUR_USERNAME` - Your MongoDB username
- `YOUR_PASSWORD` - Your MongoDB password  
- `YOUR_CLUSTER` - Your cluster name

### Step 5: Start server
```powershell
cd server
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

---

## Option 2: Use MongoDB Community (Local)

### Step 1: Install MongoDB Community
1. Download from: https://www.mongodb.com/try/download/community
2. Choose Windows
3. Run the installer (use all defaults)

### Step 2: Create .env file
Create `server/.env`:
```
MONGO_URI=mongodb://127.0.0.1:27017/katto_db
```

### Step 3: Start MongoDB service
```powershell
# MongoDB automatically starts as a Windows service
# Or run manually:
mongod --dbpath "C:\data\db"
```

### Step 4: Start server
```powershell
cd server
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

---

## Option 3: Quick Test Without MongoDB

Use the test server instead (no database required):

```powershell
cd server
python test_ws.py
```

Then test with:
```powershell
python test_ws_client.py
```

This will tell you if WebSocket works on your Windows system.

---

## Quick Diagnostic

### If server won't start, check:

1. **Is .env file created?**
   ```powershell
   ls server/.env
   ```

2. **Is MONGO_URI set correctly?**
   ```powershell
   cat server/.env
   ```

3. **Can you reach MongoDB?**
   ```powershell
   # For MongoDB Atlas
   ping cluster0.xxxxx.mongodb.net
   
   # For local MongoDB
   mongosh
   ```

4. **Are ports available?**
   ```powershell
   netstat -an | findstr "8000"  # Should be empty
   netstat -an | findstr "27017" # Should show MongoDB if using local
   ```

---

## Recommended Quickstart

**For fastest setup:**

1. Create `server/.env` with MongoDB Atlas connection string
2. Run: `uvicorn main:app --host 127.0.0.1 --port 8000 --reload`
3. When server is running, test the client

**That's it!** The WebSocket issue was a red herring - it was the database connection blocking server startup.
