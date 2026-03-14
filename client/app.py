from textual.app import App, ComposeResult
from textual import work, log
from textual.screen import Screen
from textual.containers import Vertical, Horizontal, VerticalScroll, Center, Middle
from textual.widgets import Input, Label, Button, RadioButton, RadioSet, Static
from textual.widget import Widget
from textual.suggester import SuggestFromList
import json
import urllib.request
import urllib.error
import asyncio
import sys
import re
import urllib.parse
from random import choice
import ssl
import os
import time

# Initialize sys.modules for websocket to help with Windows compatibility
os.environ.setdefault("WEBSOCKET_CLIENT_PREFER_MIN_ONE", "0")

import websocket

# Windows-specific: Use selector event loop policy for better compatibility
# (asyncio.set_event_loop_policy is deprecated in Python 3.16+, but still needed for Windows)
try:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
except AttributeError:
    # Fallback for future Python versions where this is removed
    pass

def _get_http_url(server: str, endpoint: str) -> str:
    scheme = "http" if "localhost" in server or re.match(r"^\d{1,3}\.", server) else "https"
    return f"{scheme}://{server}/{endpoint.lstrip('/')}"

def _get_ws_url(server: str, endpoint: str) -> str:
    scheme = "ws" if "localhost" in server or re.match(r"^\d{1,3}\.", server) else "wss"
    return f"{scheme}://{server}/{endpoint.lstrip('/')}"

from datetime import datetime
import os, json as _json
from pathlib import Path
from importlib.resources import files as _res_files

SESSION_FILE = Path.home() / ".katto_session.json"
try:
    # Works when installed as a package (katto) or run from project root (python -m client.app)
    from client.ui_assets import KATTO_LOGO, KATTO_MINI, HELP_TEXT, DEFAULT_ROOMS, ROOM_TOPICS
except ImportError:
    # Works when run directly inside the client folder (python app.py)
    from ui_assets import KATTO_LOGO, KATTO_MINI, HELP_TEXT, DEFAULT_ROOMS, ROOM_TOPICS

def load_session() -> dict:
    """Load session from file, return empty dict if failed."""
    try:
        if SESSION_FILE.exists():
            return _json.loads(SESSION_FILE.read_text())
    except Exception as e:
        log(f"Session: Failed to load session: {e}")
    return {}

def save_session(username: str, server: str) -> None:
    """Save session to file, log errors but don't crash."""
    try:
        SESSION_FILE.write_text(_json.dumps({"username": username, "server": server}))
    except Exception as e:
        log(f"Session: Failed to save session: {e}")

# Default server URL
# Use localhost:8000 for local development, change to production URL for deployment
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
            try:
                self.query_one("#username-input").value = session["username"]
                self.query_one("#session-hint").update("[dim]⚡ Session restored[/]")
                self.query_one("#password-input").focus()
            except Exception as e:
                log(f"LoginScreen: Failed to restore session: {e}")

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
        """Update login status safely."""
        try:
            status = self.query_one("#login-status")
            status.update(text)
            status.styles.color = "#f85149" if error else "#3fb950"
        except Exception as e:
            log(f"LoginScreen: Failed to update status: {e}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        username, password, server = self._get_credentials()
        if not username or not password:
            self._set_status("Username and password required.", error=True)
            return

        self._perform_auth(username, password, server, event.button.id == "login-btn")

    @work
    async def _perform_auth(self, username: str, password: str, server: str, is_login: bool) -> None:
        endpoint = "login" if is_login else "signup"
        url = _get_http_url(server, endpoint)

        payload = json.dumps({"username": username, "password": password}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        
        try:
            # Run blocking HTTP request in a separate thread so Textual stays highly responsive
            resp = await asyncio.to_thread(urllib.request.urlopen, req, timeout=5.0)
            data = json.loads(resp.read().decode("utf-8"))

            if not isinstance(data, dict):
                self._set_status("Server returned invalid response.", error=True)
                return

            if data.get("success"):
                self._set_status(data.get("message", "Success!"))
                save_session(username, server)
                # Use set_timer to safely push screen from async context
                self.set_timer(0.5, lambda: self.app.push_screen(
                    DashboardScreen(username=username, server_url=server)
                ))
            else:
                self._set_status(data.get("error", "Authentication failed."), error=True)
        except urllib.error.URLError as e:
            log(f"LoginScreen: URLError - {e}")
            self._set_status("Server not responding. Is it running?", error=True)
        except json.JSONDecodeError as e:
            log(f"LoginScreen: JSON decode error - {e}")
            self._set_status("Server returned invalid response.", error=True)
        except asyncio.TimeoutError:
            log("LoginScreen: Request timeout")
            self._set_status("Request timeout. Server is slow.", error=True)
        except Exception as e:
            log(f"LoginScreen: Unexpected error - {type(e).__name__}: {e}")
            self._set_status(f"Error: {type(e).__name__}", error=True)


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

    def on_mount(self) -> None:
        self._load_avatar()

    @work
    async def _load_avatar(self) -> None:
        url = _get_http_url(self.server_url, f"profile/{self.username}")
        avatar_icon = "█▄▀"
        try:
            resp = await asyncio.to_thread(urllib.request.urlopen, url, timeout=5.0)
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("success"):
                avatar_name = data["profile"].get("avatar", "Classic")
                avatar_map = {"Classic": "█▄▀", "Cat": r"/\_/\ ", "Wizard": "🧙"}
                avatar_icon = avatar_map.get(avatar_name, avatar_icon)
        except Exception as e:
            log(f"Sidebar: Failed to load avatar: {e}")
        
        # Safe DOM mutation
        if self.is_mounted:
            try:
                btn = self.query_one("#sidebar-user-btn")
                btn.label = f"{avatar_icon} @{self.username}"
            except Exception as e:
                log(f"Sidebar: Failed to update avatar button: {e}")


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

    def on_mount(self) -> None:
        self._load_profile()

    @work
    async def _load_profile(self) -> None:
        """Fetch current profile to populate bio."""
        url = _get_http_url(self.server_url, f"profile/{self.username}")
        try:
            resp = await asyncio.to_thread(urllib.request.urlopen, url, timeout=5.0)
            data = json.loads(resp.read().decode("utf-8"))
            
            if not self.is_mounted:
                return
            
            if data.get("success"):
                bio = data["profile"].get("bio", "")
                try:
                    self.query_one("#profile-bio").value = bio
                except Exception as e:
                    log(f"ProfileScreen: Failed to set bio: {e}")
        except json.JSONDecodeError as e:
            log(f"ProfileScreen: Failed to parse profile JSON: {e}")
        except Exception as e:
            log(f"ProfileScreen: Failed to load profile: {e}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-profile-btn":
            self.app.pop_screen()
            return

        if event.button.id == "save-profile-btn":
            if event.button.disabled:
                return  # already saving, prevent double-submit
            # Disable button immediately to prevent double-click
            event.button.disabled = True
            bio = self.query_one("#profile-bio").value.strip()
            password = self.query_one("#profile-password").value.strip()
            radio = self.query_one("#avatar-radio-set", RadioSet)
            avatar_map = {0: "Classic", 1: "Cat", 2: "Wizard"}
            avatar = avatar_map.get(radio.pressed_index, "Classic")
            self._save_profile(bio, password, avatar)

    @work
    async def _save_profile(self, bio: str, password: str, avatar: str) -> None:
        url = _get_http_url(self.server_url, "profile/update")
        payload = json.dumps({
            "username": self.username,
            "bio": bio if bio else None,
            "password": password if password else None,
            "avatar": avatar
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        
        try:
            resp = await asyncio.to_thread(urllib.request.urlopen, req, timeout=5.0)
            data = json.loads(resp.read().decode("utf-8"))

            if not self.is_mounted:
                return

            try:
                status = self.query_one("#profile-status")
            except Exception:
                return

            if data.get("success"):
                status.update("✓ Profile saved!")
                status.styles.color = "#3fb950"
                
                # Disable save button to prevent double-submit
                try:
                    self.query_one("#save-profile-btn").disabled = True
                except Exception:
                    pass
                
                # Pop back after a short delay
                def _do_pop():
                    if not self.is_mounted:
                        return
                    # Refresh sidebar avatar on the dashboard behind us
                    try:
                        sidebar = self.app.query_one(Sidebar)
                        sidebar._load_avatar()
                    except Exception as e:
                        log(f"ProfileScreen: Failed to refresh sidebar avatar: {e}")
                    self.app.pop_screen()
                
                self.set_timer(1.0, _do_pop)
            else:
                status.update(data.get("error", "Failed to save profile."))
                status.styles.color = "#f85149"
                # Re-enable save button so user can retry
                try:
                    self.query_one("#save-profile-btn").disabled = False
                except Exception:
                    pass
        except json.JSONDecodeError as e:
            log(f"ProfileScreen: JSON decode error: {e}")
            if self.is_mounted:
                try:
                    status = self.query_one("#profile-status")
                    status.update("Server returned invalid response.")
                    status.styles.color = "#f85149"
                except Exception:
                    pass
        except asyncio.TimeoutError:
            log("ProfileScreen: Request timeout")
            if self.is_mounted:
                try:
                    status = self.query_one("#profile-status")
                    status.update("Request timeout. Try again.")
                    status.styles.color = "#f85149"
                except Exception:
                    pass
        except Exception as e:
            log(f"ProfileScreen: Unexpected error: {type(e).__name__}: {e}")
            if self.is_mounted:
                try:
                    status = self.query_one("#profile-status")
                    status.update(f"Error: {type(e).__name__}")
                    status.styles.color = "#f85149"
                except Exception:
                    pass

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

    def on_mount(self) -> None:
        self._load_user_profile()

    @work
    async def _load_user_profile(self) -> None:
        url = _get_http_url(self.server_url, f"profile/{self.target_username}")
        try:
            resp = await asyncio.to_thread(urllib.request.urlopen, url, timeout=5.0)
            data = json.loads(resp.read().decode("utf-8"))
            
            if not self.is_mounted:
                return
                
            if data.get("success"):
                bio = data["profile"].get("bio", "No bio provided.")
                avatar = data["profile"].get("avatar", "Classic")
                friends_count = data["profile"].get("friends_count", 0)
                try:
                    self.query_one("#other-profile-bio").update(f"Bio: {bio}")
                    self.query_one("#other-profile-avatar").update(f"Avatar: {avatar}")
                    self.query_one("#other-profile-friends").update(f"Friends: {friends_count}")
                except Exception as e:
                    log(f"UserProfileScreen: Failed to update profile widgets: {e}")
            else:
                try:
                    self.query_one("#other-profile-bio").update("User not found.")
                except Exception:
                    pass
        except json.JSONDecodeError as e:
            log(f"UserProfileScreen: JSON decode error: {e}")
            if self.is_mounted:
                try:
                    self.query_one("#other-profile-bio").update("Invalid server response.")
                except Exception:
                    pass
        except Exception as e:
            log(f"UserProfileScreen: Failed to load profile: {type(e).__name__}: {e}")
            if self.is_mounted:
                try:
                    self.query_one("#other-profile-bio").update("Failed to load profile.")
                except Exception:
                    pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-profile-btn":
            self.app.pop_screen()
        elif event.button.id == "add-friend-btn":
            self._send_friend_request()
        elif event.button.id == "message-user-btn":
            self.app.pop_screen()
            # Send an event up or just handle via main dashboard
            try:
                self.app.query_one(DashboardScreen).open_dm(self.target_username)
            except Exception:
                pass

    @work
    async def _send_friend_request(self) -> None:
        url = _get_http_url(self.server_url, "friends/request")
        payload = json.dumps({
            "from_user": self.my_username,
            "to_user": self.target_username
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        
        try:
            resp = await asyncio.to_thread(urllib.request.urlopen, req, timeout=5.0)
            data = json.loads(resp.read().decode("utf-8"))
            
            if not self.is_mounted:
                return
            
            try:
                status = self.query_one("#other-profile-status")
                if data.get("success"):
                    status.update("Friend request sent!")
                    status.styles.color = "#10b981"
                else:
                    status.update(data.get("error", "Failed to send request."))
                    status.styles.color = "#ef4444"
            except Exception as e:
                log(f"UserProfileScreen: Failed to update status: {e}")
        except json.JSONDecodeError as e:
            log(f"UserProfileScreen: JSON decode error: {e}")
        except Exception as e:
            log(f"UserProfileScreen: Failed to send friend request: {type(e).__name__}: {e}")
            if self.is_mounted:
                try:
                    self.query_one("#other-profile-status").update("Error connecting.")
                except Exception:
                    pass

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

    def on_mount(self) -> None:
        self.load_notifications()

    @work
    async def load_notifications(self) -> None:
        url = _get_http_url(self.server_url, f"friends/{self.username}")
        data = {}
        error_msg = None
        
        try:
            resp = await asyncio.to_thread(urllib.request.urlopen, url, timeout=5.0)
            data = json.loads(resp.read().decode("utf-8"))
        except json.JSONDecodeError as e:
            error_msg = f"Invalid server response: {e}"
            log(f"NotificationsScreen: JSON decode error: {e}")
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)[:50]}"
            log(f"NotificationsScreen: Failed to load notifications: {type(e).__name__}: {e}")

        # All DOM mutations happen synchronously after the async fetch
        if not self.is_mounted:
            return
        
        try:
            card = self.query_one("#notifications-card")
        except Exception as e:
            log(f"NotificationsScreen: Card widget not found: {e}")
            return

        card.remove_children()

        if error_msg:
            card.mount(Label(f"Error: {error_msg}", classes="notification-empty"))
            return

        if data.get("success"):
            pending = data.get("pending", [])
            if not pending:
                card.mount(Label("No new notifications.", classes="notification-empty"))
            else:
                for req in pending:
                    try:
                        row = Horizontal(classes="notification-item")
                        row.mount(Label(f"Friend Request: @{req}", classes="notification-text"))
                        row.mount(Button("Accept",  id=f"accept-{req}",  classes="notif-accept-btn"))
                        row.mount(Button("Decline", id=f"decline-{req}", classes="notif-decline-btn"))
                        card.mount(row)
                    except Exception as e:
                        log(f"NotificationsScreen: Failed to mount notification for {req}: {e}")
        else:
            card.mount(Label("Failed to load notifications.", classes="notification-empty"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-notifications-btn":
            self.app.pop_screen()
        elif event.button.id and event.button.id.startswith("accept-"):
            target = event.button.id[7:]
            self._accept_friend_request(target)
        elif event.button.id and event.button.id.startswith("decline-"):
            target = event.button.id[8:]
            self._decline_friend_request(target)

    @work
    async def _accept_friend_request(self, target: str) -> None:
        url = _get_http_url(self.server_url, "friends/accept")
        payload = json.dumps({
            "from_user": self.username,
            "to_user": target
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        try:
            resp = await asyncio.to_thread(urllib.request.urlopen, req, timeout=5.0)
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("success"):
                await self.load_notifications()
                try:
                    dash = self.app.query_one(DashboardScreen)
                    dash.update_sidebar_dms()
                except Exception:
                    pass
        except Exception:
            pass

    @work
    async def _decline_friend_request(self, target: str) -> None:
        url = _get_http_url(self.server_url, "friends/decline")
        payload = json.dumps({
            "from_user": self.username,
            "to_user": target
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        try:
            await asyncio.to_thread(urllib.request.urlopen, req, timeout=5.0)
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
        self._ws_running = False  # flag to stop WS listener cleanly

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

    def on_mount(self) -> None:
        self.query_one("#message-input").focus()
        topic = ROOM_TOPICS.get(self.current_room, "")
        self.query_one("#channel-topic").update(topic)
        self._post_system(f"Welcome to [bold cyan]{self.current_room}[/], [bold]{self.username}[/]!")
        self._post_system("Type [bold green]/help[/] to see available commands.")

        # Connect to WebSocket
        self._ws_listener()
        # Fetch initial room history and DM list
        self._fetch_history(self.current_room)
        self.update_sidebar_dms()
        # Fetch initial online count
        self._refresh_online_count()

    @work
    async def _refresh_online_count(self) -> None:
        data = await self._api_get("/online")
        if data.get("success"):
            count = data.get("count", 0)
            try:
                self.query_one("#channel-online-count").update(f"─ {count} online")
            except Exception:
                pass

    @work
    async def _check_server_health(self) -> bool:
        """Check if server is responding before WebSocket connection."""
        try:
            log("Health: Checking server availability...")
            data = await self._api_get("/online")
            if data.get("success"):
                log("Health: Server is responding")
                return True
            else:
                log("Health: Server not responding properly")
                return False
        except Exception as e:
            log(f"Health: Server check failed: {e}")
            return False

    @work
    async def update_sidebar_dms(self) -> None:
        """Safely update sidebar DM list."""
        log("Dashboard: update_sidebar_dms worker started")
        
        # Fetch data asynchronously first — no DOM access here
        data = await self._api_get(f"/friends/{self.username}")
        log(f"Dashboard: Sidebar data received success={data.get('success')}")
        
        if not data.get("success"):
            log("Dashboard: Friends endpoint returned failure")
            return
        
        if not self.is_mounted:
            log("Dashboard: Screen unmounted before updating DMs")
            return

        friends_list = data.get("friends", [])
        pending = data.get("pending", [])

        # All DOM mutations are synchronous (non-awaited) — safe in @work
        try:
            dm_container = self.query_one("#sidebar-dms")
        except Exception as e:
            log(f"Dashboard: Failed to get DM container: {e}")
            return

        try:
            dm_container.remove_children()
        except Exception as e:
            log(f"Dashboard: Failed to clear DM container: {e}")
            return

        try:
            if friends_list:
                for friend in friends_list:
                    try:
                        dm_container.mount(Button(f"  @{friend}", classes="dm-btn", id=f"dm-{friend}"))
                    except Exception as e:
                        log(f"Dashboard: Failed to mount DM button for {friend}: {e}")
            else:
                dm_container.mount(Label("  No friends yet.", classes="sidebar-section-title"))
        except Exception as e:
            log(f"Dashboard: Failed to populate DM list: {e}")

        # Update bell badge
        try:
            notif_btn = self.query_one("#notifications-btn")
            if pending:
                notif_btn.label = f"🔔 {len(pending)}"
                notif_btn.styles.color = "#ec4899"
            else:
                notif_btn.label = "🔔"
                notif_btn.styles.color = "#94a3b8"
        except Exception as e:
            log(f"Dashboard: Failed to update notification badge: {e}")

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
        self._fetch_history(real_dm_room)

    @work
    async def _fetch_history(self, room: str) -> None:
        log(f"Dashboard: fetching history for {room}")
        encoded_room = urllib.parse.quote(room)
        try:
            data = await self._api_get(f"messages/{encoded_room}")
            log(f"Dashboard: history status success={data.get('success')}")
            
            if not data:
                log("Dashboard: Empty response from messages endpoint")
                if self.is_mounted:
                    self._post_system("Failed to fetch history: Server returned empty response")
                return
            
            if not self.is_mounted:
                log(f"Dashboard: Screen unmounted before processing history for {room}")
                return
            
            try:
                chat = self.query_one("#chat-history")
            except Exception as e:
                log(f"Dashboard: Chat history widget not found: {e}")
                return

            if data.get("success"):
                msgs = data.get("messages", [])
                if not msgs:
                    self._post_empty_state()
                    return
                    
                labels = []
                for m in msgs:
                    try:
                        sender = m.get("sender", "Unknown")
                        content = m.get("content", "")
                        ts_str = m.get("timestamp", "")
                        
                        # MongoDB returns ISO formatted dates
                        if ts_str:
                            # Replace Z with +00:00 for python fromisoformat
                            ts_str = ts_str.replace("Z", "+00:00")
                            now = datetime.fromisoformat(ts_str)
                        else:
                            now = datetime.now()
                    except Exception as e:
                        log(f"Dashboard: Failed to parse message timestamp: {e}")
                        now = datetime.now()
                        
                    # Show timestamp if > 2 minutes since last message
                    if not self.last_msg_time or (now - self.last_msg_time).total_seconds() > 120:
                        try:
                            labels.append(Label(now.strftime("%H:%M"), classes="msg-timestamp"))
                        except Exception as e:
                            log(f"Dashboard: Failed to create timestamp label: {e}")
                        self.last_msg_time = now
                    
                    try:
                        labels.append(Label(f"[bold cyan]{sender}[/]  {content}", classes="msg-other"))
                    except Exception as e:
                        log(f"Dashboard: Failed to create message label: {e}")
                
                try:
                    chat.mount_all(labels)
                    chat.scroll_end(animate=False)
                except Exception as e:
                    log(f"Dashboard: Failed to mount message labels: {e}")
            else:
                error = data.get("error", "Unknown error")
                self._post_system(f"Failed to fetch history: {error}")
                
        except json.JSONDecodeError as e:
            log(f"Dashboard: JSON decode error in history: {e}")
            self._post_system("Failed to fetch history: Invalid JSON response from server.")
        except Exception as e:
            log(f"Dashboard: Unexpected error in fetch_history: {type(e).__name__}: {e}")
            self._post_system(f"Failed to fetch history: {type(e).__name__}")

    def _post_empty_state(self) -> None:
        chat = self.query_one("#chat-history")
        lbl = Label("No messages yet — say hello! 👋")
        lbl.add_class("msg-empty")
        chat.mount(lbl)
        chat.scroll_end(animate=False)

    # --- WebSocket ---
    @work
    async def _ws_listener(self) -> None:
        self._ws_running = True
        ws_url = _get_ws_url(self.server_url, f"ws/{self.username}")
        log(f"WS: Target URL: {ws_url}")
        
        # Retry connection up to 3 times
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries and self._ws_running:
            if retry_count > 0:
                log(f"WS: Retry attempt {retry_count}/{max_retries}")
                self._post_system(f"Reconnecting... (attempt {retry_count+1})")
                await asyncio.sleep(2)  # Wait before retry
            
            log(f"WS: Attempting connection to {ws_url} (attempt {retry_count + 1})")
            
            def run_ws_sync():
                ws = None
                try:
                    log("WS: Creating WebSocket object...")
                    ws = websocket.WebSocket(ping_interval=30, ping_timeout=10)
                    
                    # Windows-specific: Setup SSL context for local connections
                    sslopt = None
                    if "localhost" in self.server_url or re.match(r"^\d{1,3}\.", self.server_url):
                        # Local development: skip SSL verification
                        sslopt = {
                            "cert_reqs": ssl.CERT_NONE, 
                            "check_hostname": False
                        }
                        log(f"WS: Using local SSL options (no verification)")
                    
                    log(f"WS: Calling ws.connect() with 15s timeout...")
                    # Connect with longer timeout
                    if sslopt:
                        ws.connect(ws_url, timeout=15, sslopt=sslopt)
                    else:
                        ws.connect(ws_url, timeout=15)
                    
                    log(f"WS: Connection established!")
                    return "connected", ws
                except websocket.WebSocketException as e:
                    log(f"WS: WebSocketException: {type(e).__name__}: {e}")
                    if ws:
                        try:
                            ws.close()
                        except:
                            pass
                    return "connection_error", str(e)
                except ConnectionRefusedError as e:
                    log(f"WS: ConnectionRefused - is server running at {self.server_url}?")
                    return "connection_error", f"Server not running at {self.server_url}"
                except TimeoutError as e:
                    log(f"WS: Timeout - server took too long to respond")
                    return "connection_error", "Server timeout (not responding)"
                except OSError as e:
                    log(f"WS: OSError: {e}")
                    return "connection_error", f"Network error: {e}"
                except Exception as e:
                    log(f"WS: Unexpected {type(e).__name__}: {e}")
                    if ws:
                        try:
                            ws.close()
                        except:
                            pass
                    return "connection_error", f"{type(e).__name__}: {e}"

            try:
                status, result = await asyncio.to_thread(run_ws_sync)
            except Exception as e:
                log(f"WS: Thread execution error: {type(e).__name__}: {e}")
                status = "thread_error"
                result = str(e)

            if status == "connected":
                # Connection successful - break retry loop
                ws = result
                if not ws:
                    log("WS: WebSocket result is None")
                    retry_count += 1
                    continue
                
                self.websocket = ws
                log("WS: ✓ Connected successfully!")
                self._post_system("✓ Connected to chat server")
                try:
                    self.query_one("#ws-status-text").update("● Online")
                    self.query_one("#ws-status-text").styles.color = "#10b981"
                except Exception:
                    pass
                
                self._refresh_online_count()

                # Start a worker thread to continuously read frames
                def read_frames():
                    log("WS: Frame reader starting")
                    try:
                        while self._ws_running:
                            try:
                                if not ws:
                                    log("WS: WebSocket is None, stopping reader")
                                    break
                                ws.settimeout(1.0)
                                raw = ws.recv()
                                if raw:
                                    log(f"WS: Received {len(raw)} bytes, dispatching to handler")
                                    try:
                                        # Use app's call_from_thread which is Textual's safe way
                                        self.app.call_from_thread(self._handle_ws_message, raw)
                                    except Exception as e:
                                        log(f"WS: Message dispatch error: {type(e).__name__}: {e}")
                            except websocket.WebSocketTimeoutException:
                                continue
                            except websocket.WebSocketClosedException:
                                log("WS: WebSocket closed by server")
                                break
                            except (ConnectionResetError, BrokenPipeError) as e:
                                log(f"WS: Connection closed: {type(e).__name__}")
                                break
                            except Exception as e:
                                log(f"WS: Frame read error: {type(e).__name__}: {e}")
                                time.sleep(0.5)
                    except Exception as e:
                        log(f"WS: Frame reader outer exception: {type(e).__name__}: {e}")
                    finally:
                        log("WS: Frame reader stopped")

                # Run reading in background thread
                try:
                    log("WS: Starting frame reader thread")
                    await asyncio.to_thread(read_frames)
                except Exception as e:
                    log(f"WS: Frame reader thread error: {type(e).__name__}: {e}")

                # Cleanup on disconnect - connection loop will exit
                log("WS: Cleaning up connection after disconnect")
                if self._ws_running and self.is_attached:
                    try:
                        self.query_one("#ws-status-text").update("● Offline")
                        self.query_one("#ws-status-text").styles.color = "#ef4444"
                    except Exception:
                        pass
                
                try:
                    if self.websocket:
                        self.websocket.close()
                except Exception as e:
                    log(f"WS: Error closing socket: {e}")
                finally:
                    self.websocket = None
                
                # Exit main loop
                break
            else:
                # Connection failed, prepare for retry
                log(f"WS: Connection failed: {result}")
                retry_count += 1
                
                if retry_count >= max_retries:
                    log(f"WS: Max retries ({max_retries}) reached, giving up")
                    if self._ws_running and self.is_attached:
                        self._post_msg(
                            f"❌ Cannot connect to server after {max_retries} attempts\n"
                            f"Error: {result}\n"
                            f"Make sure server is running on {self.server_url}",
                            "msg-error"
                        )
                        try:
                            self.query_one("#ws-status-text").update("● Offline")
                            self.query_one("#ws-status-text").styles.color = "#ef4444"
                        except Exception:
                            pass
                    break
                elif self._ws_running and self.is_attached:
                    self._post_system(f"⚠ Connection failed: {result}")
        
        self.websocket = None
        log("WS: Listener finished")

    def _handle_ws_message(self, raw: str) -> None:
        """Handle incoming WebSocket message safely."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            log(f"Dashboard: Failed to parse WS message JSON: {e}")
            return
        except Exception as e:
            log(f"Dashboard: Unexpected error parsing WS message: {e}")
            return
        
        try:
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
                    except Exception as e:
                        log(f"Dashboard: Failed to update typing indicator: {e}")
                return

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
            log(f"Dashboard: Error handling WS message: {type(e).__name__}: {e}")

    async def _on_unmount(self) -> None:
        """Cleanly stop the WebSocket listener when the screen is dismissed."""
        self._ws_running = False
        if self.websocket:
            try:
                self.websocket.close()
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
        except Exception as e:
            log(f"Dashboard: Failed to update room badge for {room}: {e}")

    # --- Message helpers ---
    def _post_msg(self, text: str, css_class: str = "msg-other", sender: str = "") -> None:
        """Post a message to the chat. Safe to call from async workers."""
        if not self.is_mounted:
            return
        try:
            chat = self.query_one("#chat-history")
        except Exception as e:
            log(f"Dashboard: Chat history widget not found: {e}")
            return
        
        now = datetime.now()

        # Show timestamp if > 2 minutes since last message
        if not self.last_msg_time or (now - self.last_msg_time).total_seconds() > 120:
            try:
                ts_label = Label(now.strftime("%H:%M"), classes="msg-timestamp")
                chat.mount(ts_label)
            except Exception as e:
                log(f"Dashboard: Failed to mount timestamp: {e}")

        self.last_msg_time = now

        try:
            lbl = Label(text, classes=css_class)
            chat.mount(lbl)
            chat.scroll_end(animate=False)
        except Exception as e:
            log(f"Dashboard: Failed to post message: {e}")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Send typing indicator over WS when user is typing a message (not a command)."""
        if event.input.id != "message-input":
            return
        val = event.value
        if val and not val.startswith("/") and self.websocket:
            try:
                payload = json.dumps({"type": "typing", "room": self.current_room})
                def _do_send():
                    try:
                        self.websocket.send(payload)
                    except Exception:
                        pass
                self.run_worker(asyncio.to_thread(_do_send))
            except Exception:
                pass

    def _post_system(self, text: str) -> None:
        """Post a system message."""
        self._post_msg(f"[dim]⟫[/] {text}", "msg-system")

    def _post_help(self) -> None:
        """Post help text."""
        try:
            for line in HELP_TEXT.split("\n"):
                self._post_msg(line, "msg-help")
        except Exception as e:
            log(f"Dashboard: Error posting help text: {e}")

    # --- API Wrappers ---
    async def _api_post(self, endpoint: str, json_data: dict) -> dict:
        """Make POST request safely."""
        url = _get_http_url(self.server_url, endpoint)
        payload = json.dumps(json_data).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        try:
            resp = await asyncio.to_thread(urllib.request.urlopen, req, timeout=5.0)
            return json.loads(resp.read().decode("utf-8"))
        except json.JSONDecodeError as e:
            log(f"Dashboard: JSON decode error in _api_post {endpoint}: {e}")
            return {}
        except Exception as e:
            log(f"Dashboard: API POST error {endpoint}: {type(e).__name__}: {e}")
            return {}

    async def _api_post_with_msg(self, endpoint: str, payload_data: dict) -> None:
        """Make POST request and show result as message."""
        url = _get_http_url(self.server_url, endpoint)
        payload = json.dumps(payload_data).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        try:
            resp = await asyncio.to_thread(urllib.request.urlopen, req, timeout=5.0)
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("success"):
                self._post_system(f"[bold green]Success:[/] {data.get('message')}")
            else:
                self._post_msg(f"[bold red]Error:[/] {data.get('error')}", "msg-error")
        except json.JSONDecodeError as e:
            log(f"Dashboard: JSON decode error in _api_post_with_msg {endpoint}: {e}")
            self._post_msg("[bold red]Error:[/] Invalid server response.", "msg-error")
        except Exception as e:
            log(f"Dashboard: API error in _api_post_with_msg {endpoint}: {type(e).__name__}: {e}")
            self._post_msg(f"[bold red]Error:[/] {type(e).__name__}", "msg-error")

    async def _api_get(self, endpoint: str) -> dict:
        """Make GET request safely."""
        url = _get_http_url(self.server_url, endpoint)
        try:
            resp = await asyncio.to_thread(urllib.request.urlopen, url, timeout=5.0)
            return json.loads(resp.read().decode("utf-8"))
        except json.JSONDecodeError as e:
            log(f"Dashboard: JSON decode error in _api_get {endpoint}: {e}")
            return {}
        except Exception as e:
            log(f"Dashboard: API GET error {endpoint}: {type(e).__name__}: {e}")
            return {}

    # --- Input handling ---
    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return

        if text.startswith("/"):
            self._handle_command(text)
        else:
            if self.websocket:
                self._send_message(text)
            else:
                self._post_msg("Not connected to server.", "msg-error")

    @work
    async def _send_message(self, text: str) -> None:
        """Send message via WebSocket safely."""
        if not self.websocket:
            self._post_msg("Not connected to server.", "msg-error")
            return
        
        payload = json.dumps({"content": text, "room": self.current_room})
        
        def _do_send():
            try:
                self.websocket.send(payload)
                return True, None
            except Exception as e:
                return False, e
        
        try:
            success, err = await asyncio.to_thread(_do_send)
            if not success:
                self._post_msg(f"Send failed: {err}", "msg-error")
                log(f"Dashboard: Message send failed: {err}")
        except Exception as e:
            self._post_msg(f"Send failed: {type(e).__name__}", "msg-error")
            log(f"Dashboard: Unexpected error sending message: {type(e).__name__}: {e}")

    @work
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
                try:
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
                    chat.remove_children()
                    self._post_system(f"Switched to [bold cyan]{room}[/]")
                    self._fetch_history(room)
                except Exception as e:
                    log(f"Dashboard: Error switching to {room}: {e}")
                    self._post_msg(f"Error switching to {room}", "msg-error")
            else:
                self._post_msg(f"Room '{room}' not found. Use /rooms to list.", "msg-error")

        elif cmd == "/user" or cmd == "/profile" and len(parts) >= 2:
            target = parts[1].lstrip("@")
            try:
                self.app.push_screen(UserProfileScreen(target_username=target, my_username=self.username, server_url=self.server_url))
            except Exception as e:
                log(f"Dashboard: Error opening profile for {target}: {e}")
                self._post_msg(f"Could not open profile for @{target}", "msg-error")

        elif cmd == "/dm" and len(parts) >= 2:
            target = parts[1].lstrip("@")
            try:
                self.open_dm(target)
            except Exception as e:
                log(f"Dashboard: Error opening DM with {target}: {e}")
                self._post_msg(f"Could not open DM with @{target}", "msg-error")

        elif cmd == "/friend" and len(parts) >= 3:
            subcmd = parts[1].lower()
            target = parts[2].lstrip("@")
            
            if subcmd == "req" or subcmd == "add":
                await self._api_post_with_msg("/friends/request", {"from_user": self.username, "to_user": target})
            elif subcmd == "accept":
                await self._api_post_with_msg("/friends/accept", {"from_user": self.username, "to_user": target})
                self.update_sidebar_dms()
            else:
                self._post_msg(f"Unknown friend command. Use /friend req @user or /friend accept @user", "msg-error")

        elif cmd == "/friends":
            try:
                data = await self._api_get(f"/friends/{self.username}")
                if data.get("success"):
                    friends_list = data.get("friends", [])
                    pending = data.get("pending", [])
                    self._post_system(f"[bold]Friends:[/] {', '.join(friends_list) if friends_list else 'None yet.'}")
                    if pending:
                        self._post_system(f"[bold yellow]Pending requests from:[/] {', '.join(pending)}")
                    self.update_sidebar_dms()
                else:
                    self._post_msg("Failed to fetch friends.", "msg-error")
            except Exception as e:
                log(f"Dashboard: Error fetching friends: {e}")
                self._post_msg("Failed to fetch friends.", "msg-error")

        elif cmd == "/profile":
            try:
                self.app.push_screen(ProfileScreen(username=self.username, server_url=self.server_url))
            except Exception as e:
                log(f"Dashboard: Error opening profile screen: {e}")
                self._post_msg("Could not open profile", "msg-error")

        elif cmd == "/users":
            self._post_system(f"Online: [bold]{self.username}[/] (you)")

        elif cmd == "/clear":
            try:
                chat = self.query_one("#chat-history")
                chat.remove_children()
                self._post_system("Chat cleared.")
            except Exception as e:
                log(f"Dashboard: Error clearing chat: {e}")
                self._post_msg("Error clearing chat", "msg-error")

        elif cmd == "/me" and len(parts) >= 2:
            action = " ".join(parts[1:])
            if self.websocket:
                emote_text = f"* {self.username} {action}"
                payload = json.dumps({"content": emote_text, "room": self.current_room})
                
                def _do_send():
                    try:
                        self.websocket.send(payload)
                        return True, None
                    except Exception as e:
                        return False, e
                
                try:
                    success, err = await asyncio.to_thread(_do_send)
                    if not success:
                        self._post_msg(f"Send failed: {err}", "msg-error")
                except Exception as e:
                    log(f"Dashboard: Error sending emote: {e}")
                    self._post_msg(f"Send failed: {type(e).__name__}", "msg-error")
            else:
                self._post_msg("Not connected to server.", "msg-error")

        elif cmd == "/search":
            if len(parts) < 2:
                self._post_system("Usage: /search <term>")
            else:
                term = " ".join(parts[1:]).lower()
                try:
                    chat = self.query_one("#chat-history")
                    count = 0
                    for lbl in chat.query(Label):
                        try:
                            text = str(lbl.renderable).lower()
                            if term in text:
                                lbl.styles.display = "block"
                                count += 1
                            else:
                                lbl.styles.display = "none"
                        except Exception as e:
                            log(f"Dashboard: Error searching label: {e}")
                    self._post_system(f"[bold]Search:[/] {count} result(s) for '[italic]{term}[/]'. Type /clear to reset.")
                except Exception as e:
                    log(f"Dashboard: Error searching messages: {e}")
                    self._post_msg("Error searching messages", "msg-error")

        elif cmd == "/logout":
            try:
                self.app.pop_screen()
            except Exception as e:
                log(f"Dashboard: Error logging out: {e}")

        elif cmd == "/quit":
            try:
                self.app.exit()
            except Exception as e:
                log(f"Dashboard: Error quitting: {e}")

        else:
            self._post_msg(f"Unknown command: {cmd}. Type /help", "msg-error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses safely."""
        try:
            btn = event.button
            if btn.id and btn.id.startswith("room-"):
                room_name = f"#{btn.id[5:]}"
                self._handle_command(f"/join {room_name}")
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
                self._show_online_members()
            elif btn.id == "quit-btn":
                self.app.exit()
        except Exception as e:
            log(f"Dashboard: Error handling button press: {type(e).__name__}: {e}")

    @work
    async def _show_online_members(self) -> None:
        """Fetch and display online members."""
        try:
            data = await self._api_get("/online")
            if data.get("success"):
                users = data.get("users", [])
                count = data.get("count", 0)
                self._post_system(f"[bold]👥 {count} online:[/] {', '.join(users) if users else 'None'}")
                try:
                    self.query_one("#channel-online-count").update(f"─ {count} online")
                except Exception as e:
                    log(f"Dashboard: Failed to update online count: {e}")
            else:
                self._post_system("Could not fetch online members.")
        except Exception as e:
            log(f"Dashboard: Error showing online members: {type(e).__name__}: {e}")
            self._post_system("Error fetching online members.")


# ==========================================
# THE MAIN APP CONTROLLER
# ==========================================
class Katto(App):
    """Katto — Terminal Social Chat"""
    TITLE = "Katto"
    SUB_TITLE = "Terminal Social Chat"
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
    ]
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