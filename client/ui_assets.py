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
[bold green]/dm @user message[/]    Send a direct message
[bold green]/friend req @user[/]    Send a friend request
[bold green]/friend accept @user[/] Accept a friend request
[bold green]/friends[/]              List your friends
[bold green]/profile[/]              Show your profile
[bold green]/users[/]                List online users
[bold green]/clear[/]                Clear chat history
[bold green]/quit[/]                 Exit Katto"""

# ==========================================
# DEFAULT ROOMS
# ==========================================
DEFAULT_ROOMS = ["#general", "#random", "#coding", "#music", "#gaming"]
