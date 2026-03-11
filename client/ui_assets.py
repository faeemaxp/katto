from random import choice

# ==========================================
# RANDOMIZED ASCII LOGO
# ==========================================
KATTO_LOGO = choice([
    r"""
 █▄▀ ▄▀█ ▀█▀ ▀█▀ █▀█
 █ █ █▀█  █   █  █▄█
""",
    r"""
                   |\__/|
     /\_/\        ( ' x ')
    ( o.o )       // |  |
 █▄▀ ▄▀█ ▀█▀ ▀█▀ █▀█
 █ █ █▀█  █   █  █▄█ /_/\_/\
""",
    r"""
     Zz.      |\_/|
   ( -_-)    ( - . - )
  /|___|\   /|___|\
 █▄▀ ▄▀█ ▀█▀ ▀█▀ █▀█ ~tail~
 █ █ █▀█  █   █  █▄█
""",
    r"""
            |\_/| |\__/|
           (=^.^=)(=ò.ó=)
 █▄▀ ▄▀█ ▀█▀ ▀█▀ █▀█
 █ █ █▀█  █   █  █▄█
   \_/\_/      \_/\_/
  (> ^_^)>    (> ^_^)>
""",
    r"""
     /\___/\   "Domain Expansion..."
    ( [===] )
     \  -  / 
 █▄▀ ▄▀█ ▀█▀ ▀█▀ █▀█
 █ █ █▀█  █   █  █▄█
""",
    r"""
     /\_/\    
    (⌐■_■)  < "Rush B."
    /|___|\
 █▄▀ ▄▀█ ▀█▀ ▀█▀ █▀█
 █ █ █▀█  █   █  █▄█
"""
])

# ==========================================
# COMPACT LOGO FOR SIDEBAR
# ==========================================
KATTO_MINI = "◈ KATTO"

# ==========================================
# COMMAND HELP TEXT
# ==========================================
HELP_TEXT = """[bold cyan]━━━ KATTO COMMANDS ━━━[/]
[bold green]/help[/]                 Show this help
[bold green]/join #room[/]           Switch chat room
[bold green]/rooms[/]                List available rooms
[bold green]/dm @user[/]             Open a direct message
[bold green]/friend req @user[/]    Send a friend request
[bold green]/friend accept @user[/] Accept a friend request
[bold green]/friends[/]              List your friends
[bold green]/profile[/]              View/edit your profile
[bold green]/users[/]                List online users
[bold green]/search <term>[/]        Search messages in this room
[bold green]/me <action>[/]          Emote — e.g. /me waves
[bold green]/clear[/]                Clear chat history
[bold green]/logout[/]               Return to login screen
[bold green]/quit[/]                 Exit Katto"""

# ==========================================
# ROOM TOPICS
# ==========================================
ROOM_TOPICS = {
    "#general": "General discussion & off-topic chat",
    "#random":  "Anything goes — memes, links, vibes",
    "#coding":  "Dev talk, bugs, and caffeine",
    "#music":   "Share tracks, artists & playlists",
    "#gaming":  "GGs, clips, and game nights",
}

# ==========================================
# DEFAULT ROOMS
# ==========================================
DEFAULT_ROOMS = ["#general", "#random", "#coding", "#music", "#gaming"]
