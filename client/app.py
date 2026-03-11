from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.containers import Vertical, Horizontal, VerticalScroll, Center, Middle
from textual.widgets import Input, Label, Button, RadioButton, RadioSet, Static
from textual.widget import Widget
from textual.suggester import SuggestFromList
import json
import httpx
import websockets
import asyncio
import urllib.parse
from random import choice

from datetime import datetime
import os, json as _json
from pathlib import Path
from importlib.resources import files as _res_files
try:
    # Works when installed as a package (katto) or run from project root (python -m client.app)
    from client.ui_assets import KATTO_LOGO, KATTO_MINI, HELP_TEXT, DEFAULT_ROOMS, ROOM_TOPICS
except ImportError:
    # Works when run directly inside the client folder (python app.py)
    from ui_assets import KATTO_LOGO, KATTO_MINI, HELP_TEXT, DEFAULT_ROOMS, ROOM_TOPICS

SESSION_FILE = Path.home() / ".katto_session.json"

def load_session() -> dict:
    try:
        if SESSION_FILE.exists():
            return _json.loads(SESSION_FILE.read_text())
    except Exception:
        pass
    return {}

def save_session(username: str, server: str) -> None:
    try:
        SESSION_FILE.write_text(_json.dumps({"username": username, "server": server}))
    except Exception:
        pass

# Default server URL
DEFAULT_SERVER = "katto-server-production.up.railway.app"
TAGLINES = [
    "Connect. Converse. Collaborate.",
    "The minimalist chat experience.",
    "Simple. Secure. Speedy.",
    "Where conversations happen.",
    "Stay in the loop.",
    "Bringing people together, one message at a time."
]

tagline = choice(TAGLINES)

# ==========================================
# SCREEN 1: LOGIN / SIGN UP
# ==========================================
class LoginScreen(Screen):

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                yield Label(KATTO_LOGO, id="login-logo")
                yield Label(tagline, id="login-subtitle")
                with Vertical(id="login-card"):
                    yield Input(placeholder="Username", id="username-input")
                    yield Input(placeholder="Password", password=True, id="password-input")
                    with Horizontal(id="server-toggle"):
                        yield RadioSet(
                            RadioButton("Default Server", value=True, id="default-radio"),
                            RadioButton("Custom Server", id="custom-radio"),
                            id="server-radio-set"
                        )
                    yield Input(
                        placeholder="Server IP (e.g. 192.168.1.5:8000)",
                        id="custom-server-input"
                    )
                    with Horizontal(id="login-buttons"):
                        yield Button("Login", id="login-btn")
                        yield Button("Sign Up", id="signup-btn")
                    yield Label("", id="login-status")
                    yield Label("", id="session-hint")

    def on_mount(self) -> None:
        session = load_session()
        if session.get("username"):
            self.query_one("#username-input").value = session["username"]
            self.query_one("#session-hint").update("[dim]⚡ Session restored[/]")
            self.query_one("#password-input").focus()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        custom_input = self.query_one("#custom-server-input")
        if event.pressed.id == "custom-radio":
            custom_input.styles.display = "block"
            custom_input.focus()
        else:
            custom_input.styles.display = "none"

    def _get_server(self) -> str:
        radio_set = self.query_one("#server-radio-set", RadioSet)
        if radio_set.pressed_index == 1:
            return self.query_one("#custom-server-input").value or DEFAULT_SERVER
        return DEFAULT_SERVER

    def _get_credentials(self) -> tuple[str, str, str]:
        username = self.query_one("#username-input").value.strip()
        password = self.query_one("#password-input").value.strip()
        server = self._get_server()
        return username, password, server

    def _set_status(self, text: str, error: bool = False) -> None:
        status = self.query_one("#login-status")
        status.update(text)
        status.styles.color = "#f85149" if error else "#3fb950"

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        username, password, server = self._get_credentials()
        if not username or not password:
            self._set_status("Username and password required.", error=True)
            return

        endpoint = "login" if event.button.id == "login-btn" else "signup"
        url = f"http://{server}/{endpoint}"

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json={
                    "username": username,
                    "password": password
                })
                data = resp.json()

            if data.get("success"):
                self._set_status(data.get("message", "Success!"))
                save_session(username, server)
                self.set_timer(0.5, lambda: self.app.push_screen(
                    DashboardScreen(username=username, server_url=server)
                ))
            else:
                self._set_status(data.get("error", "Something went wrong."), error=True)
        except Exception as e:
            self._set_status(f"Connection failed: {e}", error=True)


# ==========================================
# SIDEBAR WIDGET
# ==========================================
class Sidebar(Widget):
    def __init__(self, username: str, server_url: str, **kwargs):
        super().__init__(**kwargs)
        self.username = username
        self.server_url = server_url

    def compose(self) -> ComposeResult:
        with Horizontal(id="sidebar-profile-area"):
            with Vertical(id="sidebar-user-info"):
                yield Button(f" @{self.username}", id="sidebar-user-btn")
                yield Label("● Connecting...", id="ws-status-text")
            with Horizontal(id="sidebar-top-actions"):
                yield Button("🔔", id="notifications-btn", classes="icon-btn")

        with VerticalScroll(id="sidebar-scroll-area"):
            yield Label("FRIENDS & DMs", classes="sidebar-section-title")
            with Vertical(id="sidebar-dms"):
                yield Label("  Loading...", id="dms-loading", classes="sidebar-section-title")

            yield Label("ROOMS", classes="sidebar-section-title")
            for room in DEFAULT_ROOMS:
                yield Button(f"  {room}", classes="room-btn", id=f"room-{room[1:]}")

        with Horizontal(id="sidebar-footer"):
            yield Button("⚙ Settings", id="settings-tab-btn", classes="footer-tab")
            yield Button("✕ Quit",    id="quit-btn",          classes="footer-tab footer-quit")

    async def on_mount(self) -> None:
        url = f"http://{self.server_url}/profile/{self.username}"
        avatar_icon = "█▄▀"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
                data = resp.json()
                if data.get("success"):
                    avatar_name = data["profile"].get("avatar", "Classic")
                    avatar_map = {"Classic": "█▄▀", "Cat": r"/\_/\ ", "Wizard": "🧙"}
                    avatar_icon = avatar_map.get(avatar_name, avatar_icon)
        except Exception:
            pass
        self.query_one("#sidebar-user-btn").label = f"{avatar_icon} @{self.username}"


# ==========================================
# SCREEN: PROFILE
# ==========================================
class ProfileScreen(Screen):
    def __init__(self, username: str, server_url: str, **kwargs):
        super().__init__(**kwargs)
        self.username = username
        self.server_url = server_url

    BINDINGS = [("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                yield Label("Profile Settings", id="profile-title")
                with Vertical(id="profile-card"):
                    yield Label(f"User: @{self.username}", id="profile-username")
                    yield Label("Bio:", classes="profile-label")
                    yield Input(placeholder="Your bio", id="profile-bio")
                    yield Label("New Password:", classes="profile-label")
                    yield Input(placeholder="Leave blank to keep current", password=True, id="profile-password")
                    yield Label("Avatar:", classes="profile-label")
                    # Simple avatar select
                    yield RadioSet(
                        RadioButton("Classic █▄▀", value=True, id="avatar-1"),
                        RadioButton(r"Cat /\_/\ ", id="avatar-2"),
                        RadioButton("Wizard 🧙", id="avatar-3"),
                        id="avatar-radio-set"
                    )
                    with Horizontal(id="profile-buttons"):
                        yield Button("Save Profile", id="save-profile-btn", variant="success")
                        yield Button("Cancel", id="cancel-profile-btn")
                    yield Label("", id="profile-status")

    async def on_mount(self) -> None:
        # Fetch current profile to populate bio
        url = f"http://{self.server_url}/profile/{self.username}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
                data = resp.json()
                if data.get("success"):
                    bio = data["profile"].get("bio", "")
                    self.query_one("#profile-bio").value = bio
        except Exception:
            pass # ignore if fail to load

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-profile-btn":
            self.app.pop_screen()
            return

        if event.button.id == "save-profile-btn":
            bio = self.query_one("#profile-bio").value.strip()
            password = self.query_one("#profile-password").value.strip()
            radio = self.query_one("#avatar-radio-set", RadioSet)
            avatar_map = {0: "Classic", 1: "Cat", 2: "Wizard"}
            avatar = avatar_map.get(radio.pressed_index, "Classic")

            url = f"http://{self.server_url}/profile/update"
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(url, json={
                        "username": self.username,
                        "bio": bio if bio else None,
                        "password": password if password else None,
                        "avatar": avatar
                    })
                    data = resp.json()

                status = self.query_one("#profile-status")
                if data.get("success"):
                    status.update("Profile saved!")
                    status.styles.color = "#3fb950"
                    self.set_timer(1.0, lambda: self.app.pop_screen())
                else:
                    status.update(data.get("error", "Failed."))
                    status.styles.color = "#f85149"
            except Exception as e:
                status = self.query_one("#profile-status")
                status.update(f"Error: {e}")
                status.styles.color = "#f85149"

# ==========================================
# SCREEN: USER PROFILE (View Others)
# ==========================================
class UserProfileScreen(Screen):
    """Screen for viewing another user's profile and sending friend requests/DMs."""
    def __init__(self, target_username: str, my_username: str, server_url: str, **kwargs):
        super().__init__(**kwargs)
        self.target_username = target_username
        self.my_username = my_username
        self.server_url = server_url

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                yield Label(f"@{self.target_username}", id="other-profile-title")
                with Vertical(id="other-profile-card"):
                    yield Label("Loading...", id="other-profile-bio", classes="profile-label")
                    yield Label("Avatar: ?", id="other-profile-avatar", classes="profile-label")
                    yield Label("Friends: ?", id="other-profile-friends", classes="profile-label")
                    
                    with Horizontal(id="other-profile-actions"):
                        if self.target_username != self.my_username:
                            yield Button("Add Friend", id="add-friend-btn", variant="primary")
                            yield Button("Message", id="message-user-btn", variant="success")
                    
                    yield Button("Close", id="close-profile-btn")
                    yield Label("", id="other-profile-status")

    async def on_mount(self) -> None:
        url = f"http://{self.server_url}/profile/{self.target_username}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
                data = resp.json()
                if data.get("success"):
                    bio = data["profile"].get("bio", "No bio provided.")
                    avatar = data["profile"].get("avatar", "Classic")
                    friends_count = data["profile"].get("friends_count", 0)
                    self.query_one("#other-profile-bio").update(f"Bio: {bio}")
                    self.query_one("#other-profile-avatar").update(f"Avatar: {avatar}")
                    try:
                        self.query_one("#other-profile-friends").update(f"Friends: {friends_count}")
                    except Exception:
                        pass
                else:
                    self.query_one("#other-profile-bio").update("User not found.")
        except Exception:
            self.query_one("#other-profile-bio").update("Failed to load profile.")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-profile-btn":
            self.app.pop_screen()
        elif event.button.id == "add-friend-btn":
            url = f"http://{self.server_url}/friends/request"
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(url, json={
                        "from_user": self.my_username,
                        "to_user": self.target_username
                    })
                    data = resp.json()
                    status = self.query_one("#other-profile-status")
                    if data.get("success"):
                        status.update("Friend request sent!")
                        status.styles.color = "#10b981"
                    else:
                        status.update(data.get("error", "Failed."))
                        status.styles.color = "#ef4444"
            except Exception as e:
                self.query_one("#other-profile-status").update("Error connecting.")
        elif event.button.id == "message-user-btn":
            self.app.pop_screen()
            # Send an event up or just handle via main dashboard
            self.app.query_one(DashboardScreen).open_dm(self.target_username)

# ==========================================
# SCREEN: NOTIFICATIONS
# ==========================================
class NotificationsScreen(Screen):
    """Screen for viewing incoming friend requests."""
    def __init__(self, username: str, server_url: str, **kwargs):
        super().__init__(**kwargs)
        self.username = username
        self.server_url = server_url

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                yield Label("Notifications & Alerts", id="notifications-title")
                with VerticalScroll(id="notifications-card"):
                    yield Label("Loading...", id="notifications-loading")
                yield Button("Close", id="close-notifications-btn")

    async def on_mount(self) -> None:
        await self.load_notifications()

    async def load_notifications(self) -> None:
        card = self.query_one("#notifications-card")
        await card.remove_children()

        url = f"http://{self.server_url}/friends/{self.username}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
                data = resp.json()
                if data.get("success"):
                    pending = data.get("pending", [])
                    if not pending:
                        await card.mount(Label("No new notifications.", classes="notification-empty"))
                    for req in pending:
                        row = Horizontal(classes="notification-item")
                        await card.mount(row)  # mount to DOM first
                        await row.mount(Label(f"Friend Request: @{req}", classes="notification-text"))
                        await row.mount(Button("Accept",  id=f"accept-{req}",  classes="notif-accept-btn"))
                        await row.mount(Button("Decline", id=f"decline-{req}", classes="notif-decline-btn"))
                else:
                    await card.mount(Label("Failed to load notifications.", classes="notification-empty"))
        except Exception as e:
            await card.mount(Label(f"Error: {e}", classes="notification-empty"))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-notifications-btn":
            self.app.pop_screen()
        elif event.button.id and event.button.id.startswith("accept-"):
            target = event.button.id[7:]
            url = f"http://{self.server_url}/friends/accept"
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(url, json={
                        "from_user": self.username,
                        "to_user": target
                    })
                    if resp.json().get("success"):
                        await self.load_notifications()
                        dash = self.app.query_one(DashboardScreen)
                        dash.run_worker(dash.update_sidebar_dms())
            except Exception:
                pass
        elif event.button.id and event.button.id.startswith("decline-"):
            target = event.button.id[8:]
            url = f"http://{self.server_url}/friends/decline"
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(url, json={
                        "from_user": self.username,
                        "to_user": target
                    })
                await self.load_notifications()
            except Exception:
                pass

# ==========================================
# SCREEN: DASHBOARD
# ==========================================
class DashboardScreen(Screen):
    def __init__(self, username: str, server_url: str, **kwargs):
        super().__init__(**kwargs)
        self.username = username
        self.server_url = server_url
        self.current_room = "#general"
        self.websocket = None
        self.last_msg_time = None
        self.unread: dict = {}  # room -> unread count
        self.typing_timer = None  # handle debounce for typing events

    BINDINGS = [("ctrl+b", "toggle_sidebar", "Toggle Sidebar")]

    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar")
        sidebar.display = not sidebar.display

    def compose(self) -> ComposeResult:
        with Horizontal(id="dashboard"):
            yield Sidebar(username=self.username, server_url=self.server_url, id="sidebar")
            with Vertical(id="main-content"):
                with Horizontal(id="channel-header-container"):
                    yield Label("💬", id="channel-icon")
                    with Vertical(id="channel-info"):
                        yield Label(f"{self.current_room}", id="channel-name")
                        yield Label("", id="channel-topic")
                    with Horizontal(id="channel-header-actions"):
                        yield Label("", id="channel-online-count")
                        yield Button("🔍", id="search-btn", classes="icon-btn")
                        yield Button("👥", id="members-btn", classes="icon-btn")
                with VerticalScroll(id="chat-history"):
                    pass
                yield Label("", id="typing-indicator")
                # Autocomplete commands
                commands = ["/help", "/rooms", "/profile", "/users", "/clear", "/quit",
                            "/logout", "/me ", "/search ", "/friend req @", "/friend accept @", "/friends", "/dm @"]
                room_cmds = [f"/join {r}" for r in DEFAULT_ROOMS]
                
                yield Input(
                    placeholder=f"Message {self.current_room} · Type /help for commands",
                    id="message-input",
                    suggester=SuggestFromList(commands + room_cmds, case_sensitive=False)
                )

    async def on_mount(self) -> None:
        self.query_one("#message-input").focus()
        topic = ROOM_TOPICS.get(self.current_room, "")
        self.query_one("#channel-topic").update(topic)
        self._post_system(f"Welcome to [bold cyan]{self.current_room}[/], [bold]{self.username}[/]!")
        self._post_system("Type [bold green]/help[/] to see available commands.")

        # Connect to WebSocket
        self.run_worker(self._ws_listener())
        # Fetch initial room history and DM list
        self.run_worker(self._fetch_history(self.current_room))
        self.run_worker(self.update_sidebar_dms())
        # Fetch initial online count
        self.run_worker(self._refresh_online_count())

    async def _refresh_online_count(self) -> None:
        data = await self._api_get("/online")
        if data.get("success"):
            count = data.get("count", 0)
            try:
                self.query_one("#channel-online-count").update(f"─ {count} online")
            except Exception:
                pass

    async def update_sidebar_dms(self) -> None:
        data = await self._api_get(f"/friends/{self.username}")
        if data.get("success"):
            friends_list = data.get("friends", [])
            pending = data.get("pending", [])

            dm_container = self.query_one("#sidebar-dms")
            await dm_container.remove_children()

            for friend in friends_list:
                await dm_container.mount(Button(f"  @{friend}", classes="dm-btn", id=f"dm-{friend}"))

            if not friends_list:
                await dm_container.mount(Label("  No friends yet.", classes="sidebar-section-title"))

            # Update bell badge
            try:
                notif_btn = self.query_one("#notifications-btn")
                if pending:
                    notif_btn.label = f"\ud83d\udd14 {len(pending)}"
                    notif_btn.styles.color = "#ec4899"
                else:
                    notif_btn.label = "\ud83d\udd14"
                    notif_btn.styles.color = "#94a3b8"
            except Exception:
                pass

    def open_dm(self, target: str) -> None:
        room_name = f"@{target}"
        self.current_room = room_name
        self.query_one("#channel-icon").update("👤")
        self.query_one("#channel-name").update(f"@{target}")
        self.query_one("#channel-topic").update("Direct Message")
        self.query_one("#channel-online-count").update("")
        self.query_one("#message-input").placeholder = f"Message @{target} · Type /help for commands"
        
        # Highlight in sidebar
        for btn in self.query("Sidebar .dm-btn"):
            btn.remove_class("active")
        try:
            self.query_one(f"#dm-{target}").add_class("active")
        except:
            pass

        chat = self.query_one("#chat-history")
        chat.remove_children()
        
        # Since standard rooms use #, DMs will just be recorded under @target (from caller's perspective, or unique hash)
        # To make it simple for Katto proto, we just use a sorted identifier for DMs
        users = sorted([self.username, target])
        real_dm_room = f"DM-{users[0]}-{users[1]}"
        self.current_room = real_dm_room
        self._post_system(f"Switched to [bold magenta]DM with @{target}[/]")
        self.run_worker(self._fetch_history(real_dm_room))

    async def _fetch_history(self, room: str) -> None:
        encoded_room = urllib.parse.quote(room)
        url = f"http://{self.server_url}/messages/{encoded_room}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    self._post_system(f"Failed to fetch history: Server returned {resp.status_code}")
                    return
                data = resp.json()
                if data.get("success"):
                    msgs = data.get("messages", [])
                    if not msgs:
                        self._post_empty_state()
                    for m in msgs:
                        sender = m.get("sender", "Unknown")
                        content = m.get("content", "")
                        self._post_msg(f"[bold cyan]{sender}[/]  {content}", "msg-other")
        except json.JSONDecodeError:
            self._post_system("Failed to fetch history: Invalid JSON response from server.")
        except Exception as e:
            self._post_system(f"Failed to fetch history: {e}")

    def _post_empty_state(self) -> None:
        chat = self.query_one("#chat-history")
        lbl = Label("No messages yet — say hello! 👋")
        lbl.add_class("msg-empty")
        chat.mount(lbl)
        chat.scroll_end(animate=False)

    # --- WebSocket ---
    async def _ws_listener(self) -> None:
        ws_url = f"ws://{self.server_url}/ws/{self.username}"
        try:
            async with websockets.connect(ws_url) as ws:
                self.websocket = ws
                self._post_system("Connected to server!")
                try:
                    self.query_one("#ws-status-text").update("● Online")
                    self.query_one("#ws-status-text").styles.color = "#10b981"
                except Exception:
                    pass
                self.run_worker(self._refresh_online_count())
                while True:
                    raw = await ws.recv()
                    data = json.loads(raw)
                    msg_type = data.get("type", "message")
                    sender = data.get("sender", "Unknown")
                    content = data.get("content", "")
                    room = data.get("room", "")

                    if msg_type == "typing":
                        typer = data.get("user", "")
                        if typer and typer != self.username and room == self.current_room:
                            try:
                                self.query_one("#typing-indicator").update(
                                    f"[dim italic]• {typer} is typing...[/]"
                                )
                                # Clear after 3 seconds
                                if self.typing_timer:
                                    self.typing_timer.stop()
                                self.typing_timer = self.set_timer(
                                    3,
                                    lambda: self.query_one("#typing-indicator").update("")
                                )
                            except Exception:
                                pass
                        continue

                    if sender == "System":
                        self._post_system(content)
                    elif room == self.current_room or room == "all":
                        css = "msg-self" if sender == self.username else "msg-other"
                        self._post_msg(f"[bold magenta]{sender}[/]  {content}", css, sender=sender)
                    elif room and room != self.current_room:
                        # Increment unread badge for the other room
                        self.unread[room] = self.unread.get(room, 0) + 1
                        self._update_room_badge(room)
        except Exception as e:
            self._post_msg(f"Connection error: {e}", "msg-error")
            try:
                self.query_one("#ws-status-text").update("● Offline")
                self.query_one("#ws-status-text").styles.color = "#ef4444"
            except Exception:
                pass

    def _update_room_badge(self, room: str) -> None:
        """Refresh the sidebar label for a room to show/clear unread count."""
        room_id = f"room-{room[1:]}"
        count = self.unread.get(room, 0)
        try:
            btn = self.query_one(f"#{room_id}")
            if count > 0:
                # superscript-style badge using unicode circled numbers
                badges = ["", "①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"]
                badge = badges[min(count, 10)]
                btn.label = f"  {room}  {badge}"
                btn.add_class("has-unread")
            else:
                btn.label = f"  {room}"
                btn.remove_class("has-unread")
        except Exception:
            pass

    # --- Message helpers ---
    def _post_msg(self, text: str, css_class: str = "msg-other", sender: str = "") -> None:
        chat = self.query_one("#chat-history")
        now = datetime.now()
        
        # Show timestamp if > 2 minutes since last message
        if not self.last_msg_time or (now - self.last_msg_time).total_seconds() > 120:
            ts_label = Label(now.strftime("%H:%M"), classes="msg-timestamp")
            chat.mount(ts_label)
        
        self.last_msg_time = now
        
        lbl = Label(text, classes=css_class)
        chat.mount(lbl)
        chat.scroll_end(animate=False)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Send typing indicator over WS when user is typing a message (not a command)."""
        if event.input.id != "message-input":
            return
        val = event.value
        if val and not val.startswith("/") and self.websocket:
            try:
                payload = json.dumps({"type": "typing", "room": self.current_room})
                self.run_worker(self.websocket.send(payload))
            except Exception:
                pass

    def _post_system(self, text: str) -> None:
        self._post_msg(f"[dim]⟫[/] {text}", "msg-system")

    def _post_help(self) -> None:
        for line in HELP_TEXT.split("\n"):
            self._post_msg(line, "msg-help")

    # --- API Wrappers ---
    async def _api_post(self, endpoint: str, json_data: dict) -> dict:
        url = f"http://{self.server_url}{endpoint}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(url, json=json_data)
                return resp.json()
        except Exception as e:
            # We don't want to spam the UI with fetch errors silently, but we can log them internally
            return {}

    async def _api_post_with_msg(self, endpoint: str, payload: dict) -> None:
        url = f"http://{self.server_url}{endpoint}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(url, json=payload)
                data = resp.json()
                if data.get("success"):
                    self._post_system(f"[bold green]Success:[/] {data.get('message')}")
                else:
                    self._post_msg(f"[bold red]Error:[/] {data.get('error')}", "msg-error")
        except Exception as e:
             self._post_msg(f"API HTTP Error: {e}", "msg-error")

    async def _api_get(self, endpoint: str) -> dict:
        url = f"http://{self.server_url}{endpoint}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                return resp.json()
        except Exception:
             return {}

    # --- Input handling ---
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return

        if text.startswith("/"):
            await self._handle_command(text)
        else:
            if self.websocket:
                payload = json.dumps({"content": text, "room": self.current_room})
                try:
                    await self.websocket.send(payload)
                except Exception as e:
                    self._post_msg(f"Send failed: {e}", "msg-error")
            else:
                self._post_msg("Not connected to server.", "msg-error")

    async def _handle_command(self, text: str) -> None:
        parts = text.split()
        cmd = parts[0].lower()

        if cmd == "/help":
            self._post_help()

        elif cmd == "/rooms":
            self._post_system("Available rooms:")
            for room in DEFAULT_ROOMS:
                marker = "→" if room == self.current_room else " "
                self._post_system(f"  {marker} {room}")

        elif cmd == "/join" and len(parts) >= 2:
            room = parts[1] if parts[1].startswith("#") else f"#{parts[1]}"
            if room in DEFAULT_ROOMS:
                self.current_room = room
                self.query_one("#channel-icon").update("💬")
                self.query_one("#channel-name").update(room)
                self.query_one("#channel-topic").update(ROOM_TOPICS.get(room, ""))
                self.query_one("#message-input").placeholder = (
                    f"Message {room} · Type /help for commands"
                )

                # Clear unread badge for this room
                self.unread[room] = 0
                self._update_room_badge(room)

                # Highlight in sidebar
                for btn in self.query("Sidebar .room-btn"):
                    btn.remove_class("active")
                self.query_one(f"#room-{room[1:]}").add_class("active")

                chat = self.query_one("#chat-history")
                await chat.remove_children()
                self._post_system(f"Switched to [bold cyan]{room}[/]")
                self.run_worker(self._fetch_history(room))
            else:
                self._post_msg(f"Room '{room}' not found. Use /rooms to list.", "msg-error")

        elif cmd == "/user" or cmd == "/profile" and len(parts) >= 2:
            target = parts[1].lstrip("@")
            self.app.push_screen(UserProfileScreen(target_username=target, my_username=self.username, server_url=self.server_url))

        elif cmd == "/dm" and len(parts) >= 2:
            target = parts[1].lstrip("@")
            self.open_dm(target)

        elif cmd == "/friend" and len(parts) >= 3:
            subcmd = parts[1].lower()
            target = parts[2].lstrip("@")
            
            if subcmd == "req" or subcmd == "add":
                await self._api_post_with_msg("/friends/request", {"from_user": self.username, "to_user": target})
            elif subcmd == "accept":
                await self._api_post_with_msg("/friends/accept", {"from_user": self.username, "to_user": target})
                self.run_worker(self.update_sidebar_dms())
            else:
                 self._post_msg(f"Unknown friend command. Use /friend req @user or /friend accept @user", "msg-error")

        elif cmd == "/friends":
            data = await self._api_get(f"/friends/{self.username}")
            if data.get("success"):
                friends_list = data.get("friends", [])
                pending = data.get("pending", [])
                self._post_system(f"[bold]Friends:[/] {', '.join(friends_list) if friends_list else 'None yet.'}")
                if pending:
                    self._post_system(f"[bold yellow]Pending requests from:[/] {', '.join(pending)}")
                self.run_worker(self.update_sidebar_dms())
            else:
                 self._post_msg("Failed to fetch friends.", "msg-error")

        elif cmd == "/profile":
            self.app.push_screen(ProfileScreen(username=self.username, server_url=self.server_url))

        elif cmd == "/users":
            self._post_system(f"Online: [bold]{self.username}[/] (you)")

        elif cmd == "/clear":
            chat = self.query_one("#chat-history")
            await chat.remove_children()
            self._post_system("Chat cleared.")

        elif cmd == "/me" and len(parts) >= 2:
            action = " ".join(parts[1:])
            if self.websocket:
                emote_text = f"* {self.username} {action}"
                payload = json.dumps({"content": emote_text, "room": self.current_room})
                try:
                    await self.websocket.send(payload)
                except Exception as e:
                    self._post_msg(f"Send failed: {e}", "msg-error")
            else:
                self._post_msg("Not connected to server.", "msg-error")

        elif cmd == "/search":
            if len(parts) < 2:
                self._post_system("Usage: /search <term>")
            else:
                term = " ".join(parts[1:]).lower()
                chat = self.query_one("#chat-history")
                count = 0
                for lbl in chat.query(Label):
                    text = str(lbl.renderable).lower()
                    if term in text:
                        lbl.styles.display = "block"
                        count += 1
                    else:
                        lbl.styles.display = "none"
                self._post_system(f"[bold]Search:[/] {count} result(s) for '[italic]{term}[/]'. Type /clear to reset.")

        elif cmd == "/logout":
            self.app.pop_screen()

        elif cmd == "/quit":
            self.app.exit()

        else:
            self._post_msg(f"Unknown command: {cmd}. Type /help", "msg-error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn = event.button
        if btn.id and btn.id.startswith("room-"):
            room_name = f"#{btn.id[5:]}"
            self.run_worker(self._handle_command(f"/join {room_name}"))
        elif btn.id and btn.id.startswith("dm-"):
            target = btn.id[3:]
            self.open_dm(target)
        elif btn.id == "settings-tab-btn":
            self.app.push_screen(ProfileScreen(username=self.username, server_url=self.server_url))
        elif btn.id == "sidebar-user-btn":
            self.app.push_screen(UserProfileScreen(target_username=self.username, my_username=self.username, server_url=self.server_url))
        elif btn.id == "notifications-btn":
            self.app.push_screen(NotificationsScreen(username=self.username, server_url=self.server_url))
        elif btn.id == "search-btn":
            self._post_system("[bold]Search:[/] Type /search <term> to filter messages.")
            self.query_one("#message-input").value = "/search "
            self.query_one("#message-input").focus()
        elif btn.id == "members-btn":
            self.run_worker(self._show_online_members())
        elif btn.id == "quit-btn":
            self.app.exit()

    async def _show_online_members(self) -> None:
        data = await self._api_get("/online")
        if data.get("success"):
            users = data.get("users", [])
            count  = data.get("count", 0)
            self._post_system(f"[bold]👥 {count} online:[/] {', '.join(users) if users else 'None'}")
            try:
                self.query_one("#channel-online-count").update(f"─ {count} online")
            except Exception:
                pass
        else:
            self._post_system("Could not fetch online members.")


# ==========================================
# THE MAIN APP CONTROLLER
# ==========================================
class Katto(App):
    """Katto — Terminal Social Chat"""
    TITLE = "Katto"
    SUB_TITLE = "Terminal Social Chat"
    # Works both when running from source (python app.py)
    # and when installed as a package (pipx / pip install)
    try:
        CSS_PATH = str(_res_files("client") / "chat_ui.tcss")
    except Exception:
        CSS_PATH = str(Path(__file__).parent / "chat_ui.tcss")

    def on_mount(self) -> None:
        self.push_screen(LoginScreen())


def main() -> None:
    """Console script entry point — called by the `katto` command."""
    Katto().run()


if __name__ == "__main__":
    main()