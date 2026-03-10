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

from ui_assets import KATTO_LOGO, KATTO_MINI, HELP_TEXT, DEFAULT_ROOMS

# Default server URL
DEFAULT_SERVER = "127.0.0.1:8000"
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
            yield Button(f" @{self.username}", id="sidebar-user-btn")
            with Horizontal(id="sidebar-top-actions"):
                yield Button("🔔", id="notifications-btn", classes="icon-btn")
                yield Button("⚙", id="profile-btn", classes="icon-btn")

        with VerticalScroll(id="sidebar-scroll-area"):
            yield Label("FRIENDS & DMs", classes="sidebar-section-title")
            with Vertical(id="sidebar-dms"):
                yield Label("  Loading...", id="dms-loading", classes="sidebar-section-title")

            yield Label("ROOMS", classes="sidebar-section-title")
            for room in DEFAULT_ROOMS:
                yield Button(f"  {room}", classes="room-btn", id=f"room-{room[1:]}")
            
        with Vertical(id="sidebar-actions"):
            yield Button("✕ Quit", id="quit-btn")

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
                        card.mount(Label("No new notifications.", classes="notification-empty"))
                    for req in pending:
                        with Horizontal(classes="notification-item") as row:
                            row.mount(Label(f"Friend Request: @{req}", classes="notification-text"))
                            acc_btn = Button("Accept", id=f"accept-{req}", variant="success")
                            row.mount(acc_btn)
                            card.mount(row)
                else:
                    card.mount(Label("Failed to load notifications."))
        except Exception:
            card.mount(Label("Error connecting to server."))

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
                        await self.load_notifications() # reload
                        # Notify dashboard to update sidebar
                        dash = self.app.query_one(DashboardScreen)
                        dash.run_worker(dash.update_sidebar_dms())
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

    def compose(self) -> ComposeResult:
        with Horizontal(id="dashboard"):
            yield Sidebar(username=self.username, server_url=self.server_url, id="sidebar")
            with Vertical(id="main-content"):
                with Horizontal(id="channel-header-container"):
                    yield Label("💬", id="channel-icon")
                    yield Label(f"{self.current_room}", id="channel-name")
                with VerticalScroll(id="chat-history"):
                    pass
                
                # Autocomplete commands
                commands = ["/help", "/rooms", "/profile", "/users", "/clear", "/quit", 
                            "/friend req @", "/friend accept @", "/friends", "/dm @"]
                room_cmds = [f"/join {r}" for r in DEFAULT_ROOMS]
                
                yield Input(
                    placeholder=f"Message {self.current_room} · Type /help for commands",
                    id="message-input",
                    suggester=SuggestFromList(commands + room_cmds, case_sensitive=False)
                )

    async def on_mount(self) -> None:
        self.query_one("#message-input").focus()
        self._post_system(f"Welcome to [bold cyan]{self.current_room}[/], [bold]{self.username}[/]!")
        self._post_system("Type [bold green]/help[/] to see available commands.")
        
        # Connect to WebSocket
        self.run_worker(self._ws_listener())
        # Fetch initial room history
        self.run_worker(self._fetch_history(self.current_room))
        self.run_worker(self.update_sidebar_dms())

    async def update_sidebar_dms(self) -> None:
        data = await self._api_get(f"/friends/{self.username}")
        if data.get("success"):
            friends_list = data.get("friends", [])
            pending = data.get("pending", [])
            
            dm_container = self.query_one("#sidebar-dms")
            await dm_container.remove_children()
            
            for friend in friends_list:
                dm_container.mount(Button(f"  @{friend}", classes="dm-btn", id=f"dm-{friend}"))
            
            # Show a tiny indicator on the notifications button if pending
            notif_btn = self.query_one("#notifications-btn")
            if pending:
                notif_btn.label = f"🔔 ({len(pending)})"
                notif_btn.styles.color = "#ec4899"
            else:
                notif_btn.label = "🔔"
                notif_btn.styles.color = "#f8fafc"
                
    def open_dm(self, target: str) -> None:
        room_name = f"@{target}"
        self.current_room = room_name
        self.query_one("#channel-icon").update("👤")
        self.query_one("#channel-name").update(target)
        self.query_one("#message-input").placeholder = f"Message @{target} · Type /help for commands"
        
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
                    # Optionally clear and insert
                    for m in msgs:
                        sender = m.get("sender", "Unknown")
                        content = m.get("content", "")
                        self._post_msg(f"[bold cyan]{sender}[/]  {content}", "msg-other")
        except json.JSONDecodeError:
            self._post_system("Failed to fetch history: Invalid JSON response from server.")
        except Exception as e:
            self._post_system(f"Failed to fetch history: {e}")

    # --- WebSocket ---
    async def _ws_listener(self) -> None:
        ws_url = f"ws://{self.server_url}/ws/{self.username}"
        try:
            async with websockets.connect(ws_url) as ws:
                self.websocket = ws
                self._post_system("Connected to server!")
                while True:
                    raw = await ws.recv()
                    data = json.loads(raw)
                    sender = data.get("sender", "Unknown")
                    content = data.get("content", "")
                    room = data.get("room", "")
                    
                    if sender == "System":
                        self._post_system(content)
                    elif room == self.current_room or room == "all":
                        css = "msg-self" if sender == self.username else "msg-other"
                        self._post_msg(f"[bold magenta]{sender}[/]  {content}", css)
        except Exception as e:
            self._post_msg(f"Connection error: {e}", "msg-error")

    # --- Message helpers ---
    def _post_msg(self, text: str, css_class: str = "msg-other") -> None:
        chat = self.query_one("#chat-history")
        lbl = Label(text)
        lbl.add_class(css_class)
        chat.mount(lbl)
        chat.scroll_end(animate=False)

    def _post_system(self, text: str) -> None:
        self._post_msg(f"[dim]⟫[/] {text}", "msg-system")

    def _post_help(self) -> None:
        for line in HELP_TEXT.split("\n"):
            self._post_msg(line, "msg-help")

    # --- API Wrappers ---
    async def _api_post(self, endpoint: str, payload: dict) -> None:
        url = f"http://{self.server_url}{endpoint}"
        try:
            async with httpx.AsyncClient() as client:
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
            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
                return resp.json()
        except:
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
                self.query_one("#message-input").placeholder = (
                    f"Message {room} · Type /help for commands"
                )
                chat = self.query_one("#chat-history")
                await chat.remove_children()
                self._post_system(f"Switched to [bold cyan]{room}[/]")
                # Fetch history for new room
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
                await self._api_post("/friends/request", {"from_user": self.username, "to_user": target})
            elif subcmd == "accept":
                await self._api_post("/friends/accept", {"from_user": self.username, "to_user": target})
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
        elif btn.id == "profile-btn":
            self.app.push_screen(ProfileScreen(username=self.username, server_url=self.server_url))
        elif btn.id == "sidebar-user-btn":
            self.app.push_screen(UserProfileScreen(target_username=self.username, my_username=self.username, server_url=self.server_url))
        elif btn.id == "notifications-btn":
            self.app.push_screen(NotificationsScreen(username=self.username, server_url=self.server_url))
        elif btn.id == "quit-btn":
            self.app.exit()


# ==========================================
# THE MAIN APP CONTROLLER
# ==========================================
class Katto(App):
    """Katto — Terminal Social Chat"""
    TITLE = "Katto"
    SUB_TITLE = "Terminal Social Chat"
    CSS_PATH = "chat_ui.tcss"

    def on_mount(self) -> None:
        self.push_screen(LoginScreen())


if __name__ == "__main__":
    app = Katto()
    app.run()