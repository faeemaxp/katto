# Katto Server

This is the backend server for Katto, built with FastAPI, WebSockets, and MongoDB. 

## 🚀 Easy Deployment

This repository is pre-configured to be deployed natively on [Render.com](https://render.com), [Railway.app](https://railway.app), or any Docker-compatible hosting platform.

### Option 1: Render (Recommended)
1. Fork or push this repository to your own GitHub.
2. Go to **Render.com** > New **Web Service**.
3. Connect your repository.
4. Render should automatically detect Python.
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT` (or it will auto-detect the `Procfile`)
5. Click **Advanced** and add an Environment Variable:
   - Key: `MONGO_URI`
   - Value: `your-mongodb-connection-string-here`
6. Deploy! Copy the `onrender.com` URL Render gives you into your client app (`DEFAULT_SERVER` in `app.py`).

### Option 2: Railway (Using CLI)
If you prefer deploying straight from your terminal without using GitHub:
1. Install [Railway CLI](https://docs.railway.app/guides/cli) (`npm i -g @railway/cli`)
2. Log in: `railway login`
3. Initialize the project inside the `server/` directory:
   ```bash
   cd server
   railway init
   ```
4. Set your MongoDB environment variable securely:
   ```bash
   railway variables set MONGO_URI="your-mongodb-connection-string-here"
   ```
5. Deploy the server!
   ```bash
   railway up
   ```
   *(Railway will automatically detect the Dockerfile or Python requirements and build it for you).*

### Option 3: Docker
We have included a `Dockerfile` so this runs anywhere containers run:
```bash
docker build -t katto-server .
docker run -p 8000:8000 -e MONGO_URI="your-mongo-url" katto-server
```

## 🛠️ Local Development
To run this locally for testing:
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the server
uvicorn main:app --reload

# It will now be accessible at 127.0.0.1:8000
```
