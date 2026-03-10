from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.containers import VerticalScroll, Center, Middle
from textual.widgets import Header, Footer, Input, Label, OptionList, Button
from random import choice
import json
import asyncio
import websockets

# ==========================================
# RANDOMIZED ASCII LOGO
# ==========================================
KATTO_LOGO = choice([
    # 1. The Clean Classic
    r"""
 █▄▀ ▄▀█ ▀█▀ ▀█▀ █▀█
 █ █ █▀█  █   █  █▄█
""",
    
    # 2. The Hanging & Sitting Cats
    r"""
                   |\__/|
     /\_/\        ( ' x ')
    ( o.o )       // |  |
 █▄▀ ▄▀█ ▀█▀ ▀█▀ █▀█
 █ █ █▀█  █   █  █▄█ /_/\_/\
""",
    
    # 3. The Sleeping & Stretching Cats
    r"""
     Zz.      |\_/|
   ( -_-)    ( - . - )
  /|___|\   /|___|\
 █▄▀ ▄▀█ ▀█▀ ▀█▀ █▀█ ~tail~
 █ █ █▀█  █   █  █▄█
""",
    
    # 4. The Multiple Walking Cats
    r"""
            |\_/| |\__/|
           (=^.^=)(=ò.ó=)
 █▄▀ ▄▀█ ▀█▀ ▀█▀ █▀█
 █ █ █▀█  █   █  █▄█
   \_/\_/      \_/\_/
  (> ^_^)>    (> ^_^)>
""",

    # 5. The Sorcerer Cat
    r"""
     /\___/\   "Domain Expansion..."
    ( [===] )
     \  -  / 
 █▄▀ ▄▀█ ▀█▀ ▀█▀ █▀█
 █ █ █▀█  █   █  █▄█
""",

    # 6. The Tactical Op Cat
    r"""
     /\_/\    
    (⌐■_■)  < "Rush B."
    /|___|\
 █▄▀ ▄▀█ ▀█▀ ▀█▀ █▀█
 █ █ █▀█  █   █  █▄█
"""
])
# ==========================================
# SCREEN 1: THE HOME MENU
# ==========================================
class HomeScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header()
        with Center():
            with Middle():
                yield Label(KATTO_LOGO, id="ascii-logo")
                yield Label("Welcome to Katto", id="welcome-title")
                yield Input(placeholder="Username...", id="user-input")
                yield Input(placeholder="Server IP (e.g. 127.0.0.1:8000)", id="server-input")
                yield Button("Connect", variant="success", id="connect-btn")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        user = self.query_one("#user-input").value
        server = self.query_one("#server-input").value or "127.0.0.1:8000"
        if user:
            self.app.push_screen(ChatScreen(username=user, server_url=server))

# ==========================================
# SCREEN 2: THE LIVE CHAT SCREEN
# ==========================================
class ChatScreen(Screen):
    def __init__(self, username: str, server_url: str, **kwargs):
        super().__init__(**kwargs)
        self.username = username
        self.server_url = f"ws://{server_url}/ws/{username}"
        self.websocket = None

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="chat-history"):
            yield Label(f"System: Connecting to {self.server_url}...")
        yield Input(placeholder="Type a message...", id="message-input")
        yield Footer()

    async def on_mount(self) -> None:
        self.query_one("#message-input").focus()
        # Start the background listener for incoming messages
        self.run_worker(self.listen_for_messages())

    async def listen_for_messages(self) -> None:
        """Connects to FastAPI and waits for messages."""
        try:
            async with websockets.connect(self.server_url) as ws:
                self.websocket = ws
                while True:
                    raw_data = await ws.recv()
                    data = json.loads(raw_data)
                    
                    # Add message to UI
                    chat_history = self.query_one("#chat-history")
                    sender = data.get("sender", "Unknown")
                    content = data.get("content", "")
                    
                    chat_history.mount(Label(f"[bold cyan]{sender}:[/] {content}"))
                    chat_history.scroll_end(animate=False)
        except Exception as e:
            self.query_one("#chat-history").mount(Label(f"Error: {e}"))

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        message = event.value
        event.input.value = ""
        
        if self.websocket and message.strip():
            # Send message to FastAPI server
            payload = json.dumps({"content": message})
            await self.websocket.send(payload)
# ==========================================
# THE MAIN APP CONTROLLER
# ==========================================
class katto(App):
    """The main application that manages our screens."""
    CSS = """
                /* ==========================================
                CHAT SCREEN STYLES
                ========================================== */
                
                #chat-history {
                    height: 1fr; /* '1 fraction': Takes up all available vertical space left over */
                    border: solid green;
                    padding: 1; /* Adds 1 row/column of breathing room INSIDE the green border */
                    margin: 0 2; /* SHORTHAND: 0 margin top/bottom, 2 margin left/right */
                }
                
                #message-input {
                    dock: bottom; /* Glues the input box permanently to the bottom of the screen */
                    margin: 0 2 1 2; /* SHORTHAND (Top: 0, Right: 2, Bottom: 1, Left: 2) */
                }
                
                /* This is a 'Pseudo-class'. It only applies when you are actively typing in the box! */
                #message-input:focus {
                    border: tall cyan; /* Changes the border to a cool double-line cyan when active */
                }

                /* ==========================================
                HOME SCREEN STYLES
                ========================================== */
                
                #welcome-title {
                    color: cyan;
                    text-style: bold; /* Makes the title text thicker */
                    content-align: center middle; /* Centers the actual text INSIDE the label */
                    width: 100%; /* Forces the label to span the whole menu width so it centers properly */
                    margin-bottom: 2; /* Pushes the menu box down by 2 rows so they don't touch */
                }
                
                #main-menu {
                    width: 40; /* Prevents the menu box from stretching awkwardly across your whole monitor */
                    border: solid purple;
                    padding: 1;
                    
                    /* Note: I removed your 'align: center middle' here. 
                    Because we wrapped this inside 'Center()' and 'Middle()' in your Python code, 
                    Textual is already centering the whole box perfectly on the screen for you! */
                }
                /* Add this under your Home Screen CSS section */
                    #ascii-logo {
                    color: cyan;
                    text-style: bold;
                    content-align: center middle;
                    width: 100%;
                    margin-bottom: 2; /* Gives some space before the menu */
    }
                """

    def on_mount(self) -> None:
        """When the app starts, immediately load the Home Screen."""
        self.push_screen(HomeScreen())

if __name__ == "__main__":
    app = katto()
    debug = True  # Set to True to enable debug mode (optional)
    app.run() 
    