# 🐾 Katto
**Terminal Social Chat**

Bringing people together, one message at a time. A modern, Discord-like chat application built entirely for the terminal using Textual.

![Katto Banner](docs/assets/banner_placeholder.png) <!-- Replace this with a wide screenshot of the main chat dashboard -->

## ✨ Features
- **Modern TUI:** Beautiful, interactive interface that feels like a modern web app but lives in your terminal.
- **Global & Private Rooms:** Chat in `#general`, `#coding`, `#gaming`, etc.
- **Direct Messaging:** Send DMs privately to other users.
- **Friend System:** Send friend requests, accept/decline, and see who is online.
- **Live Updates:** See when other users are typing and get real-time message updates via WebSockets.
- **Slash Commands:** Fully powered by `/commands` for easy navigation and power use.

---

## 🚀 Installation Guide

### Option 1: The Easy Way (Use `pipx`)
If you just want to run the app as a command-line tool, we recommend using [pipx](https://pypa.github.io/pipx/).

```bash
# Install directly from the repository
pipx install git+https://github.com/your-username/katto.git

# Run it!
katto
```

### Option 2: Clone and Install
If you want to look at the code or contribute to it:

```bash
# 1. Clone the repository
git clone https://github.com/your-username/katto.git
cd katto

# 2. Install using pip
pip install -e .

# 3. Launch the app
katto
```

---

## 📸 Screenshots

| Login Screen | Dashboard / Chat |
| :---: | :---: |
| ![Login Placeholder](docs/assets/login_placeholder.png) | ![Chat Placeholder](docs/assets/chat_placeholder.png) |
| *Log in or create a new account* | *Live chat in #general* |

| Friends & DMs | Command Palette |
| :---: | :---: |
| ![Friends Placeholder](docs/assets/friends_placeholder.png) | ![Commands Placeholder](docs/assets/commands_placeholder.png) |
| *Send friend requests and private messages* | *Navigate quickly via /commands* |

*(Note: Replace the placeholder image links above with actual screenshots of your application)*

---

## 💬 Command Reference
Type `/help` anywhere in the app to see all available commands.

- `/join #room` — Switch to a public room (e.g. `/join #coding`)
- `/rooms` — See a list of all available rooms
- `/users` — See who is currently online
- `/dm @username` — Open a private chat with someone
- `/friend req @username` — Send a friend request
- `/friend accept @username` — Accept a friend request
- `/friends` — View your friend list and pending requests
- `/profile` — View/edit your settings and profile status
- `/me <action>` — Send a roleplay/action message (e.g. `* panda smiles`)
- `/search <term>` — Search current chat history
- `/clear` — Clear your local chat view
- `/quit` / `/logout` — Exit the app

---

## 🛠️ For Developers: Running the Server

Katto is a client-server application. By default, the client tries to connect to the cloud server, but you can also run your own server locally.

**Requirements:**
- Python 3.11+
- MongoDB

1. Navigate to the `server/` directory.
2. Ensure you have the backend dependencies installed (`pip install -r requirements.txt` / `fastapi`, `uvicorn`, `motor`, etc.).
3. Start the local server:
```bash
uvicorn main:app --reload
```
4. Update `DEFAULT_SERVER = "127.0.0.1:8000"` in `client/app.py` or log in using the local IP.

---

## 📜 License
Distributed under the MIT License. See `LICENSE` for more information.
