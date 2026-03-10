from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.containers import VerticalScroll, Center, Middle
from textual.widgets import Header, Footer, Input, Label, OptionList

# ==========================================
# SCREEN 1: THE MAIN MENU (Updated)
# ==========================================
class HomeScreen(Screen):
    """The main menu screen with arrow-key navigation."""

    def compose(self) -> ComposeResult:
        yield Header()
        with Center():
            with Middle():
                yield Label("Terminal Chat Menu", id="welcome-title")
                
                # This is the magic widget!
                yield OptionList(
                    "Join Chat Room",
                    "Settings",
                    "Exit App",
                    id="main-menu"
                )
        yield Footer()

    def on_mount(self) -> None:
        """Focus the menu automatically when the screen loads."""
        self.query_one("#main-menu").focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """This event triggers exactly when the user presses Enter on an option."""
        
        # event.option.prompt gets the text of the item they selected
        selected_text = str(event.option.prompt)
        
        if selected_text == "Join Chat Room":
            # For now, we will just pass a default username to the chat screen
            self.app.push_screen(ChatScreen(username="Guest User"))
            
        elif selected_text == "Settings":
            # You can build a settings screen later!
            self.app.notify("Settings menu coming soon...")
            
        elif selected_text == "Exit App":
            self.app.exit()

# (Keep your ChatScreen and TerminalChatApp code exactly the same as before!)

# ==========================================
# SCREEN 2: THE CHAT SCREEN (Your previous code)
# ==========================================
class ChatScreen(Screen):
    """The actual chat room screen."""
    
    # We accept the username passed from the HomeScreen
    def __init__(self, username: str, **kwargs):
        super().__init__(**kwargs)
        self.username = username

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="chat-history"):
            yield Label(f"System: Welcome to the room, {self.username}!")
        yield Input(placeholder="Type your message...", id="message-input")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#message-input").focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        message = event.value
        event.input.value = ""
        chat_history = self.query_one("#chat-history")
        
        # Use the custom username they entered!
        chat_history.mount(Label(f"{self.username}: {message}"))
        chat_history.scroll_end(animate=False)


# ==========================================
# THE MAIN APP CONTROLLER
# ==========================================
class TerminalChatApp(App):
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
                """

    def on_mount(self) -> None:
        """When the app starts, immediately load the Home Screen."""
        self.push_screen(HomeScreen())

if __name__ == "__main__":
    app = TerminalChatApp()
    debug = True  # Set to True to enable debug mode (optional)
    app.run() 
    