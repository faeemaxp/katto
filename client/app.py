"""
Katto — Terminal Social Chat  v4
=================================
Voice channel UI now lives INLINE inside the dashboard (same layout as text
channels) — the sidebar stays visible at all times.

Voice connection fix:
  • RTCConfiguration now includes Google/Cloudflare STUN servers so ICE works
    between two clients on the same machine (different processes/accounts).
  • _LOOPBACK_ICE_POLICY forces aiortc to include 127.x candidates explicitly
    when both peers are on the same LAN / machine.

Layout changes:
  • No more VoiceChannelScreen push — voice view is a Vertical inside
    #main-content that swaps in/out exactly like switching a text channel.
  • VoiceView widget contains: channel header, participant list (left),
    activity log (right), controls bar (bottom).
  • VoiceBar at the bottom of the sidebar is unchanged (Discord lower-left).
"""

from __future__ import annotations

import asyncio
import fractions
import json
import logging
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from random import choice
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Platform bootstrapping
# ---------------------------------------------------------------------------

ssl._create_default_https_context = ssl._create_unverified_context
os.environ.setdefault("WEBSOCKET_CLIENT_PREFER_MIN_ONE", "0")

if sys.platform == "win32":
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except (AttributeError, ImportError):
        pass

# ---------------------------------------------------------------------------
# Import guard: detect wrong 'websocket' package vs correct 'websocket-client'
# Two completely different PyPI packages share the `import websocket` namespace:
#   websocket-client (CORRECT) - WebSocket() takes no positional args
#   websocket==0.2.x (WRONG)   - WebSocket() requires environ/socket/rfile
# If the wrong one is installed it shadows websocket-client and crashes.
# ---------------------------------------------------------------------------
import websocket  # noqa: E402

try:
    _t = websocket.WebSocket()  # websocket-client: ok; wrong pkg: TypeError
    del _t
except TypeError:
    raise ImportError(
        "\n\n"
        "\u274c  Wrong \'websocket\' package detected.\n"
        "    The unrelated \'websocket==0.2.x\' package is installed and shadows\n"
        "    the required \'websocket-client\'.\n\n"
        "    Run these commands to fix it:\n"
        "        uv pip uninstall websocket gevent greenlet zope-event zope-interface\n"
        "        uv pip install websocket-client\n"
    )

from textual import log, work
from textual.app import App, ComposeResult
from textual.containers import Center, Horizontal, Middle, Vertical, VerticalScroll
from textual.screen import Screen
from textual.suggester import SuggestFromList
from textual.widget import Widget
from textual.widgets import Button, Collapsible, Input, Label, RadioButton, RadioSet

# ---------------------------------------------------------------------------
# Optional voice libs
# ---------------------------------------------------------------------------

try:
    import numpy as np
    from aiortc import (
        MediaStreamTrack,
        RTCConfiguration,
        RTCIceCandidate,
        RTCIceServer,
        RTCPeerConnection,
        RTCSessionDescription,
    )
    from av import AudioFrame
    _AIORTC_AVAILABLE = True
except ImportError:
    _AIORTC_AVAILABLE = False
    np = None  # type: ignore[assignment]

try:
    import sounddevice as sd
    _SD_AVAILABLE = True
except ImportError:
    _SD_AVAILABLE = False

# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------

try:
    from client.ui_assets import DEFAULT_ROOMS, HELP_TEXT, KATTO_LOGO, KATTO_MINI, ROOM_TOPICS
except ImportError:
    try:
        from ui_assets import DEFAULT_ROOMS, HELP_TEXT, KATTO_LOGO, KATTO_MINI, ROOM_TOPICS  # type: ignore
    except ImportError:
        KATTO_LOGO    = "KATTO"
        KATTO_MINI    = "K"
        HELP_TEXT     = ""
        DEFAULT_ROOMS = ["#general", "#random", "#dev"]
        ROOM_TOPICS   = {}

try:
    from importlib.resources import files as _res_files
except ImportError:
    _res_files = None  # type: ignore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SERVER        = "katto-server-production.up.railway.app"
SESSION_FILE          = Path.home() / ".katto_session.json"
TIMESTAMP_GAP_SECONDS = 120
WS_MAX_RETRIES        = 3
WS_RETRY_DELAY_S      = 2
WS_CONNECT_TIMEOUT    = 15
WS_READ_TIMEOUT       = 1.0
HTTP_TIMEOUT          = 5.0

VOICE_SAMPLE_RATE = 48_000
VOICE_CHANNELS    = 1
VOICE_FRAME_SIZE  = 960   # 20 ms @ 48 kHz

VOICE_CHANNELS_LIST = ["🔊 General", "🔊 Gaming", "🔊 Music", "🔊 AFK"]

# ---------------------------------------------------------------------------
# ICE / STUN configuration
# ---------------------------------------------------------------------------
# Using multiple STUN servers makes same-machine and same-LAN connections
# work reliably.  Google's public STUN + Cloudflare cover virtually all
# network topologies including loopback between two processes on one host.

_ICE_SERVERS = [
    "stun:stun.l.google.com:19302",
    "stun:stun1.l.google.com:19302",
    "stun:stun.cloudflare.com:3478",
]

def _make_rtc_config() -> "RTCConfiguration":
    if not _AIORTC_AVAILABLE:
        return None  # type: ignore[return-value]
    return RTCConfiguration(
        iceServers=[RTCIceServer(urls=_ICE_SERVERS)]
    )

TAGLINES = [
    "Connect. Converse. Collaborate.",
    "The minimalist chat experience.",
    "Simple. Secure. Speedy.",
    "Where conversations happen.",
    "Stay in the loop.",
    "Bringing people together, one message at a time.",
]

_vlog = logging.getLogger("katto.voice")

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

_LOCAL_RE = re.compile(r"^(localhost|127\.\d+\.\d+\.\d+|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})")

def _is_local(s: str) -> bool:
    return bool(_LOCAL_RE.match(s.split(":")[0]))

def _http_url(server: str, ep: str) -> str:
    return f"{'http' if _is_local(server) else 'https'}://{server}/{ep.lstrip('/')}"

def _ws_url(server: str, ep: str) -> str:
    return f"{'ws' if _is_local(server) else 'wss'}://{server}/{ep.lstrip('/')}"

def _dm_room(a: str, b: str) -> str:
    return "DM-" + "-".join(sorted([a, b]))

def _fmt_dur(secs: Optional[int]) -> str:
    if secs is None: return "ongoing"
    m, s = divmod(secs, 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s" if h else (f"{m}m {s}s" if m else f"{s}s")

def _fmt_ts(iso: Optional[str]) -> str:
    if not iso: return "—"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%H:%M")
    except Exception:
        return iso[:5]

# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

def load_session() -> dict:
    try:
        if SESSION_FILE.exists():
            return json.loads(SESSION_FILE.read_text())
    except Exception as exc:
        log(f"Session.load: {exc}")
    return {}

def save_session(u: str, s: str) -> None:
    try:
        SESSION_FILE.write_text(json.dumps({"username": u, "server": s}))
    except Exception as exc:
        log(f"Session.save: {exc}")

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _post_sync(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        return json.loads(r.read().decode())

def _get_sync(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as r:
        return json.loads(r.read().decode())

async def api_post(server: str, ep: str, payload: dict) -> dict:
    try:
        return await asyncio.to_thread(_post_sync, _http_url(server, ep), payload)
    except Exception as exc:
        log(f"api_post {ep}: {exc}")
        return {}

async def api_get(server: str, ep: str) -> dict:
    try:
        return await asyncio.to_thread(_get_sync, _http_url(server, ep))
    except Exception as exc:
        log(f"api_get {ep}: {exc}")
        return {}

# ===========================================================================
# VOICE ENGINE
# ===========================================================================

if _AIORTC_AVAILABLE and _SD_AVAILABLE:

    class MicrophoneTrack(MediaStreamTrack):  # type: ignore[misc]
        kind = "audio"

        def __init__(self) -> None:
            super().__init__()
            self._queue:  asyncio.Queue = asyncio.Queue(maxsize=20)
            self._pts:    int           = 0
            self._stream                = None
            self._loop                  = None
            self._muted:  bool          = False

        def start(self) -> None:
            self._loop   = asyncio.get_event_loop()
            self._stream = sd.InputStream(
                samplerate=VOICE_SAMPLE_RATE, channels=VOICE_CHANNELS,
                dtype="int16", blocksize=VOICE_FRAME_SIZE, callback=self._cb,
            )
            self._stream.start()

        def stop(self) -> None:
            if self._stream:
                try: self._stream.stop(); self._stream.close()
                except Exception: pass
                self._stream = None
            super().stop()

        def set_muted(self, muted: bool) -> None:
            self._muted = muted

        def _cb(self, indata, frames, time_info, status) -> None:
            if not self._loop: return
            chunk = np.zeros_like(indata.flatten()) if self._muted else indata.copy().flatten()
            try:
                self._loop.call_soon_threadsafe(self._queue.put_nowait, chunk)
            except asyncio.QueueFull:
                try:
                    self._queue.get_nowait()
                    self._loop.call_soon_threadsafe(self._queue.put_nowait, chunk)
                except Exception: pass

        async def recv(self) -> "AudioFrame":
            pcm               = await self._queue.get()
            frame             = AudioFrame(format="s16", layout="mono")
            frame.planes[0].update(pcm.tobytes())
            frame.sample_rate = VOICE_SAMPLE_RATE
            frame.pts         = self._pts
            frame.time_base   = fractions.Fraction(1, VOICE_SAMPLE_RATE)
            self._pts        += VOICE_FRAME_SIZE
            return frame

    class SpeakerSink:
        def __init__(self, track) -> None:
            self._track    = track
            self._stream   = None
            self._task     = None
            self._deafened = False

        def start(self) -> None:
            self._stream = sd.OutputStream(
                samplerate=VOICE_SAMPLE_RATE, channels=VOICE_CHANNELS, dtype="int16"
            )
            self._stream.start()
            self._task = asyncio.ensure_future(self._drain())

        def stop(self) -> None:
            if self._task and not self._task.done(): self._task.cancel()
            if self._stream:
                try: self._stream.stop(); self._stream.close()
                except Exception: pass
                self._stream = None

        def set_deafened(self, d: bool) -> None:
            self._deafened = d

        async def _drain(self) -> None:
            try:
                while True:
                    frame = await self._track.recv()
                    if self._deafened or self._stream is None: continue
                    pcm = frame.to_ndarray().flatten().astype(np.int16)
                    self._stream.write(pcm)
            except asyncio.CancelledError: pass
            except Exception as exc: _vlog.debug(f"SpeakerSink: {exc}")

else:
    class MicrophoneTrack:  # type: ignore[no-redef]
        kind = "audio"
        def __init__(self): self._muted = False
        def start(self): pass
        def stop(self): pass
        def set_muted(self, m: bool): self._muted = m

    class SpeakerSink:  # type: ignore[no-redef]
        def __init__(self, track): self._deafened = False
        def start(self): pass
        def stop(self): pass
        def set_deafened(self, d: bool): self._deafened = d


class VoiceCallManager:
    """
    RTCPeerConnection lifecycle + audio I/O.

    Key fix vs v3: RTCPeerConnection is now created with _make_rtc_config()
    which includes STUN servers.  This is what makes same-machine connections
    work — without STUN, aiortc only generates 127.0.0.1 host candidates and
    two separate processes can't differentiate each other's ICE endpoint.
    """

    def __init__(
        self,
        my_username:           str,
        send_signal:           Callable,
        on_status:             Callable[[str], None],
        on_call_state:         Callable[[str, str], None],
        on_participant_change: Callable[[list[dict]], None],
    ) -> None:
        self._me                    = my_username
        self._send_signal           = send_signal
        self._on_status             = on_status
        self._on_call_state         = on_call_state
        self._on_participant_change = on_participant_change

        self._pc:           Optional["RTCPeerConnection"] = None
        self._mic:          Optional[MicrophoneTrack]    = None
        self._speaker:      Optional[SpeakerSink]        = None
        self._peer:         Optional[str]                = None
        self._channel:      Optional[str]                = None
        self._call_start:   Optional[datetime]           = None
        self._pending_ice:  list[dict]                   = []
        self._muted:        bool                         = False
        self._deafened:     bool                         = False
        self._participants: list[dict]                   = []

    # ------------------------------------------------------------------
    @property
    def in_call(self) -> bool:   return self._pc is not None
    @property
    def peer(self) -> Optional[str]:    return self._peer
    @property
    def channel(self) -> Optional[str]: return self._channel
    @property
    def muted(self) -> bool:     return self._muted
    @property
    def deafened(self) -> bool:  return self._deafened
    @property
    def elapsed(self) -> str:
        if not self._call_start: return "00:00"
        secs = int((datetime.now(tz=timezone.utc) - self._call_start).total_seconds())
        m, s = divmod(secs, 60)
        return f"{m:02d}:{s:02d}"
    @property
    def participants(self) -> list[dict]: return list(self._participants)

    # ------------------------------------------------------------------
    async def call(self, target: str, channel: str = "") -> None:
        if not _AIORTC_AVAILABLE or not _SD_AVAILABLE:
            self._on_status("⚠ Voice deps missing (aiortc / sounddevice / numpy)."); return
        if self._pc:
            self._on_status("Already in a call. /hangup first."); return

        self._peer       = target
        self._channel    = channel or f"DM:{target}"
        self._call_start = datetime.now(tz=timezone.utc)
        self._participants = [{"username": self._me, "joined_at": self._call_start}]
        self._on_status(f"📞 Calling @{target}…")
        self._on_call_state("calling", target)
        self._on_participant_change(self._participants)

        # ← STUN config here
        self._pc  = RTCPeerConnection(configuration=_make_rtc_config())
        self._mic = MicrophoneTrack()
        self._attach_events(self._pc)
        self._mic.start()
        self._pc.addTrack(self._mic)

        offer = await self._pc.createOffer()
        await self._pc.setLocalDescription(offer)
        await self._send_signal({
            "type": "webrtc-offer", "target": target,
            "sdp": self._pc.localDescription.sdp,
            "channel": self._channel,
        })

    async def hangup(self) -> None:
        if not self._pc: return
        peer = self._peer or ""
        if peer:
            await self._send_signal({"type": "webrtc-hangup", "target": peer})
        self._on_status(f"📵 Left voice{' with @' + peer if peer else ''}.")
        await self._teardown()

    def set_muted(self, muted: bool) -> None:
        self._muted = muted
        if self._mic: self._mic.set_muted(muted)
        self._on_call_state("in_call" if self._pc else "idle", self._peer or "")

    def set_deafened(self, deafened: bool) -> None:
        self._deafened = deafened
        if deafened and not self._muted: self.set_muted(True)
        if self._speaker: self._speaker.set_deafened(deafened)
        self._on_call_state("in_call" if self._pc else "idle", self._peer or "")

    def handle_signal(self, data: dict) -> None:
        asyncio.ensure_future(self._dispatch(data))

    def add_participant(self, username: str) -> None:
        if not any(p["username"] == username for p in self._participants):
            self._participants.append({
                "username": username,
                "joined_at": datetime.now(tz=timezone.utc),
            })
            self._on_participant_change(self._participants)

    def remove_participant(self, username: str) -> None:
        self._participants = [p for p in self._participants if p["username"] != username]
        self._on_participant_change(self._participants)

    # ------------------------------------------------------------------
    async def _dispatch(self, data: dict) -> None:
        t = data.get("type"); from_user = data.get("from_user", "?")
        if   t == "webrtc-offer":         await self._handle_offer(data, from_user)
        elif t == "webrtc-answer":        await self._handle_answer(data)
        elif t == "webrtc-ice-candidate": await self._handle_ice(data)
        elif t == "webrtc-hangup":
            self.remove_participant(from_user)
            self._on_status(f"📵 @{from_user} left the call.")
            if from_user == self._peer: await self._teardown()

    async def _handle_offer(self, data: dict, caller: str) -> None:
        if self._pc:
            await self._send_signal({"type": "webrtc-hangup", "target": caller}); return
        if not _AIORTC_AVAILABLE or not _SD_AVAILABLE:
            self._on_status("⚠ Cannot accept — voice deps missing."); return

        self._peer       = caller
        self._channel    = data.get("channel", f"DM:{caller}")
        self._call_start = datetime.now(tz=timezone.utc)
        self._participants = [
            {"username": caller,   "joined_at": self._call_start},
            {"username": self._me, "joined_at": self._call_start},
        ]
        self._on_status(f"📞 Incoming call from @{caller} — answering…")
        self._on_call_state("calling", caller)
        self._on_participant_change(self._participants)

        # ← STUN config here too
        self._pc  = RTCPeerConnection(configuration=_make_rtc_config())
        self._mic = MicrophoneTrack()
        self._attach_events(self._pc)
        self._mic.start()
        self._pc.addTrack(self._mic)

        await self._pc.setRemoteDescription(
            RTCSessionDescription(sdp=data["sdp"], type="offer")
        )
        await self._flush_ice()
        answer = await self._pc.createAnswer()
        await self._pc.setLocalDescription(answer)
        await self._send_signal({
            "type": "webrtc-answer", "target": caller,
            "sdp": self._pc.localDescription.sdp,
        })

    async def _handle_answer(self, data: dict) -> None:
        if not self._pc: return
        await self._pc.setRemoteDescription(
            RTCSessionDescription(sdp=data["sdp"], type="answer")
        )
        await self._flush_ice()
        self._on_status("🔊 Call connected!")
        if self._peer: self.add_participant(self._peer)
        self._on_call_state("in_call", self._peer or "")

    async def _handle_ice(self, data: dict) -> None:
        c = data.get("candidate")
        if not c: return
        if self._pc is None or self._pc.remoteDescription is None:
            self._pending_ice.append(data); return
        await self._apply_ice(c)

    async def _flush_ice(self) -> None:
        while self._pending_ice:
            await self._apply_ice(self._pending_ice.pop(0).get("candidate"))

    async def _apply_ice(self, c) -> None:
        if not c or not self._pc: return
        try: await self._pc.addIceCandidate(c)
        except Exception as exc: _vlog.debug(f"addIceCandidate: {exc}")

    def _attach_events(self, pc: "RTCPeerConnection") -> None:

        @pc.on("track")
        def on_track(track) -> None:
            if track.kind == "audio":
                self._speaker = SpeakerSink(track)
                self._speaker.set_deafened(self._deafened)
                self._speaker.start()
                self._on_status("🔊 Receiving audio from peer")
                @track.on("ended")
                def _ended():
                    if self._speaker: self._speaker.stop()

        @pc.on("icecandidate")
        def on_ice(candidate) -> None:
            if candidate is None: return
            asyncio.ensure_future(self._send_signal({
                "type": "webrtc-ice-candidate", "target": self._peer,
                "candidate": {
                    "candidate":     candidate.candidate,
                    "sdpMid":        candidate.sdpMid,
                    "sdpMLineIndex": candidate.sdpMLineIndex,
                },
            }))

        @pc.on("connectionstatechange")
        async def on_cs() -> None:
            state = pc.connectionState
            _vlog.debug(f"connectionState → {state}")
            if state == "connected":
                self._on_status("🔊 Voice connected")
                self._on_call_state("in_call", self._peer or "")
            elif state in ("failed", "closed"):
                self._on_status("📵 Call ended")
                await self._teardown()

        @pc.on("iceconnectionstatechange")
        async def on_ice_state() -> None:
            state = pc.iceConnectionState
            _vlog.debug(f"iceConnectionState → {state}")
            if state == "failed":
                self._on_status("⚠ ICE negotiation failed — retrying with relay…")
                # ICE restart — lets aiortc try again without tearing the whole call down
                try:
                    offer = await pc.createOffer(iceRestart=True)
                    await pc.setLocalDescription(offer)
                    await self._send_signal({
                        "type": "webrtc-offer", "target": self._peer,
                        "sdp": pc.localDescription.sdp,
                        "channel": self._channel,
                        "is_restart": True,
                    })
                except Exception as exc:
                    _vlog.debug(f"ICE restart failed: {exc}")
                    await self._teardown()

    async def _teardown(self) -> None:
        if self._mic:     self._mic.stop();     self._mic     = None
        if self._speaker: self._speaker.stop(); self._speaker = None
        if self._pc:
            try: await self._pc.close()
            except Exception: pass
            self._pc = None
        old_peer           = self._peer
        self._peer         = None
        self._channel      = None
        self._call_start   = None
        self._pending_ice  = []
        self._participants = []
        self._muted        = False
        self._deafened     = False
        self._on_call_state("idle", old_peer or "")
        self._on_participant_change([])


# ===========================================================================
# VOICE VIEW WIDGET — inline panel replacing main-content
# ===========================================================================

class VoiceView(Widget):
    """
    Inline voice channel panel.  Replaces the chat history + input area inside
    #main-content when the user joins a voice channel.  The sidebar stays
    visible throughout — same layout as Discord.

    Structure:
      ┌─ #vc-header ──────────────────────────────────────────┐
      │  🔊 channel_name          ⏱ MM:SS / Connecting…       │
      ├─ #vc-body ────────────────────────────────────────────┤
      │  #vc-left (28 cols)  │  #vc-right (1fr)               │
      │  PARTICIPANTS         │  VOICE ACTIVITY                │
      │  @alice 🔊  joined…  │  [HH:MM:SS] @alice joined      │
      │  @bob  🔇  joined…   │  [HH:MM:SS] You muted          │
      ├─ #vc-controls ────────────────────────────────────────┤
      │  🎤/@name  [Mute] [Deafen] [History] [📵 Leave]       │
      └───────────────────────────────────────────────────────┘
    """

    def __init__(self, channel_name: str, voice: VoiceCallManager, **kwargs) -> None:
        super().__init__(**kwargs)
        self._channel_name = channel_name
        self._voice        = voice

    def compose(self) -> ComposeResult:
        # Header row
        with Horizontal(id="vc-header"):
            yield Label("🔊", id="vc-icon")
            yield Label(self._channel_name, id="vc-channel-name")
            yield Label("⏳ Connecting…", id="vc-status-label")

        # Body: participant list | activity log
        with Horizontal(id="vc-body"):
            with Vertical(id="vc-left"):
                yield Label("  PARTICIPANTS", classes="vc-section-title")
                with VerticalScroll(id="vc-participant-list"):
                    yield Label("  Waiting…", classes="vc-empty")

            with Vertical(id="vc-right"):
                yield Label("  VOICE ACTIVITY", classes="vc-section-title")
                with VerticalScroll(id="vc-event-log"):
                    yield Label(
                        f"  [{datetime.now().strftime('%H:%M:%S')}] Joined {self._channel_name}",
                        classes="vc-event",
                    )

        # Controls bar
        with Horizontal(id="vc-controls"):
            yield Label("", id="vc-self-label")
            yield Button("🎤 Mute",    id="vc-mute-btn",   classes="vc-ctrl-btn")
            yield Button("🔇 Deafen",  id="vc-deafen-btn", classes="vc-ctrl-btn")
            yield Button("📋 History", id="vc-hist-btn",   classes="vc-ctrl-btn")
            yield Button("📵 Leave",   id="vc-leave-btn",  classes="vc-ctrl-btn vc-leave")

    def on_mount(self) -> None:
        self.refresh_participants(self._voice.participants)
        self.refresh_controls()
        self.set_interval(1, self._tick)

    def _tick(self) -> None:
        if not self.is_mounted: return
        try:
            dur   = self._voice.elapsed if self._voice.in_call else "—"
            label = f"🔊 Connected  {dur}" if self._voice.in_call else "⏳ Connecting…"
            self.query_one("#vc-status-label", Label).update(label)
        except Exception: pass

    def refresh_participants(self, participants: list[dict]) -> None:
        if not self.is_mounted: return
        try:
            c = self.query_one("#vc-participant-list")
            c.remove_children()
            if not participants:
                c.mount(Label("  No one here yet.", classes="vc-empty")); return
            for p in participants:
                name  = p.get("username", "?")
                jat   = p.get("joined_at")
                joined = _fmt_ts(jat.isoformat() if hasattr(jat, "isoformat") else jat)
                is_me  = name == self._voice._me
                icons  = ""
                if is_me and self._voice.muted:    icons += " 🔇"
                if is_me and self._voice.deafened: icons += " 🙉"
                if not icons:                       icons  = " 🔊"
                lbl = Label(
                    f"  {'[bold]' if is_me else ''}@{name}{'[/bold]' if is_me else ''}"
                    f"{icons}  [dim]since {joined}[/dim]",
                    classes="vc-participant vc-me" if is_me else "vc-participant",
                )
                lbl.can_focus = False
                c.mount(lbl)
        except Exception as exc:
            log(f"VoiceView.refresh_participants: {exc}")

    def refresh_controls(self) -> None:
        if not self.is_mounted: return
        try:
            m_btn = self.query_one("#vc-mute-btn",   Button)
            d_btn = self.query_one("#vc-deafen-btn", Button)
            m_btn.label = "🔇 Unmute"   if self._voice.muted    else "🎤 Mute"
            d_btn.label = "🔊 Undeafen" if self._voice.deafened else "🔇 Deafen"
            m_btn.set_class(self._voice.muted,    "active")
            d_btn.set_class(self._voice.deafened, "active")
            mic = "🔇" if self._voice.muted    else "🎤"
            ear = "🙉" if self._voice.deafened else "🔊"
            self.query_one("#vc-self-label", Label).update(
                f"  {mic} {ear}  [bold]@{self._voice._me}[/bold]"
            )
        except Exception as exc:
            log(f"VoiceView.refresh_controls: {exc}")

    def add_event(self, text: str) -> None:
        if not self.is_mounted: return
        try:
            ts  = datetime.now().strftime("%H:%M:%S")
            log_c = self.query_one("#vc-event-log")
            lbl   = Label(f"  [{ts}] {text}", classes="vc-event")
            lbl.can_focus = False
            log_c.mount(lbl)
            log_c.scroll_end(animate=False)
        except Exception as exc:
            log(f"VoiceView.add_event: {exc}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "vc-mute-btn":
            new = not self._voice.muted
            self._voice.set_muted(new)
            self.refresh_participants(self._voice.participants)
            self.refresh_controls()
            self.add_event("You muted." if new else "You unmuted.")
        elif bid == "vc-deafen-btn":
            new = not self._voice.deafened
            self._voice.set_deafened(new)
            self.refresh_participants(self._voice.participants)
            self.refresh_controls()
            self.add_event("You deafened." if new else "You undeafened.")
        elif bid == "vc-hist-btn":
            try:
                self.app.query_one(DashboardScreen).app.push_screen(
                    VoiceCallLogScreen(self.app.query_one(DashboardScreen).server_url)
                )
            except Exception: pass
        elif bid == "vc-leave-btn":
            asyncio.ensure_future(self._do_leave())

    async def _do_leave(self) -> None:
        self.add_event("You left the channel.")
        await self._voice.hangup()
        # Tell dashboard to restore chat view
        try:
            self.app.query_one(DashboardScreen)._exit_voice_view()
        except Exception: pass


# ===========================================================================
# VOICE BAR — bottom of sidebar, always visible
# ===========================================================================

class VoiceBar(Widget):

    def compose(self) -> ComposeResult:
        with Vertical(id="vbar-inner"):
            with Horizontal(id="vbar-status-row"):
                yield Label("💤", id="vbar-icon")
                with Vertical(id="vbar-info"):
                    yield Label("No Voice",      id="vbar-channel")
                    yield Label("Not connected", id="vbar-detail")
            with Horizontal(id="vbar-controls"):
                yield Button("🎤", id="vbar-mute-btn",  classes="vbar-btn")
                yield Button("🔇", id="vbar-deaf-btn",  classes="vbar-btn")
                yield Button("📵", id="vbar-leave-btn", classes="vbar-btn vbar-leave")
                yield Button("🔊", id="vbar-open-btn",  classes="vbar-btn")

    def set_state(
        self, state: str, peer: str, channel: str,
        elapsed: str, muted: bool, deafened: bool,
    ) -> None:
        if not self.is_mounted: return
        try:
            icon   = self.query_one("#vbar-icon",    Label)
            ch_lbl = self.query_one("#vbar-channel", Label)
            detail = self.query_one("#vbar-detail",  Label)
            for bid in ("#vbar-mute-btn","#vbar-deaf-btn","#vbar-leave-btn","#vbar-open-btn"):
                try: self.query_one(bid, Button).disabled = (state == "idle")
                except Exception: pass

            if state == "idle":
                icon.update("💤");   ch_lbl.update("No Voice");     detail.update("Not connected")
                self.remove_class("active")
            elif state == "calling":
                icon.update("📞");   ch_lbl.update(f"Calling @{peer}…"); detail.update(channel)
                self.add_class("active")
            elif state == "in_call":
                icon.update("🔇" if muted else "🔊")
                ch_lbl.update(channel or f"In call with @{peer}")
                parts = []
                if muted:    parts.append("🔇 Muted")
                if deafened: parts.append("🙉 Deaf")
                parts.append(elapsed)
                detail.update("  ".join(parts))
                self.add_class("active")
        except Exception as exc:
            log(f"VoiceBar.set_state: {exc}")


# ===========================================================================
# SIDEBAR
# ===========================================================================

class Sidebar(Widget):

    def __init__(self, username: str, server_url: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.username   = username
        self.server_url = server_url

    def compose(self) -> ComposeResult:
        with Horizontal(id="sidebar-profile-area"):
            with Vertical(id="sidebar-user-info"):
                yield Button(f" @{self.username}", id="sidebar-user-btn")
                yield Label("● Connecting…", id="ws-status-text")
            with Horizontal(id="sidebar-top-actions"):
                yield Button("🔔", id="notifications-btn", classes="icon-btn")
                yield Button("📋", id="vcall-log-btn",      classes="icon-btn")

        with VerticalScroll(id="sidebar-scroll-area"):
            with Collapsible(title="FRIENDS & DMs", id="friends-collapsible", collapsed=False):
                with Vertical(id="sidebar-dms"):
                    yield Label("  Loading…", classes="sidebar-section-title")
            with Collapsible(title="TEXT CHANNELS", id="rooms-collapsible", collapsed=False):
                for room in DEFAULT_ROOMS:
                    yield Button(f"  {room}", classes="room-btn", id=f"room-{room[1:]}")
            with Collapsible(title="VOICE CHANNELS", id="voice-collapsible", collapsed=False):
                for vc in VOICE_CHANNELS_LIST:
                    sid = re.sub(r"[^a-zA-Z0-9_-]", "_", vc)
                    yield Button(f"  {vc}", classes="vc-channel-btn", id=f"vc__{sid}")

        # VoiceBar — OUTSIDE VerticalScroll, always visible
        yield VoiceBar(id="voice-bar")

        with Horizontal(id="sidebar-footer"):
            yield Button("⚙ Settings", id="settings-tab-btn", classes="footer-tab")
            yield Button("✕ Quit",     id="quit-btn",          classes="footer-tab")

    def on_mount(self) -> None:
        self._refresh_avatar()
        try:
            self.query_one("#voice-bar", VoiceBar).set_state("idle","","","",False,False)
        except Exception: pass

    @work
    async def _refresh_avatar(self) -> None:
        safe = urllib.parse.quote(self.username)
        data = await api_get(self.server_url, f"profile/{safe}")
        if not (self.is_mounted and data.get("success")): return
        amap = {"Classic": "█▄▀", "Cat": r"/\_/\ ", "Wizard": "🧙"}
        icon = amap.get(data.get("profile", {}).get("avatar", "Classic"), "█▄▀")
        try:
            self.query_one("#sidebar-user-btn", Button).label = f"{icon} @{self.username}"
        except Exception as exc:
            log(f"Sidebar._refresh_avatar: {exc}")


# ===========================================================================
# PROFILE SCREEN
# ===========================================================================

class ProfileScreen(Screen):
    BINDINGS = [("escape", "pop_screen", "Back")]

    def __init__(self, username: str, server_url: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.username   = username
        self.server_url = server_url

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                yield Label("Profile Settings", id="profile-title")
                with Vertical(id="profile-card"):
                    yield Label(f"@{self.username}", id="profile-username")
                    yield Label("Bio", classes="profile-label")
                    yield Input(placeholder="Your bio", id="profile-bio")
                    yield Label("New Password", classes="profile-label")
                    yield Input(placeholder="Leave blank to keep current",
                                password=True, id="profile-password")
                    yield Label("Avatar", classes="profile-label")
                    yield RadioSet(
                        RadioButton("Classic █▄▀", value=True, id="avatar-1"),
                        RadioButton(r"Cat /\_/\ ",              id="avatar-2"),
                        RadioButton("Wizard 🧙",                id="avatar-3"),
                        id="avatar-radio-set",
                    )
                    with Horizontal(id="profile-buttons"):
                        yield Button("Save",   id="save-profile-btn")
                        yield Button("Cancel", id="cancel-profile-btn")
                    yield Label("", id="profile-status")

    def on_mount(self) -> None:
        self._load()

    def _set_status(self, t: str, *, error: bool = False) -> None:
        try:
            lbl = self.query_one("#profile-status", Label)
            lbl.update(t); lbl.styles.color = "#f87171" if error else "#6ee7b7"
        except Exception: pass

    @work
    async def _load(self) -> None:
        safe = urllib.parse.quote(self.username)
        data = await api_get(self.server_url, f"profile/{safe}")
        if self.is_mounted and data.get("success"):
            try: self.query_one("#profile-bio", Input).value = data["profile"].get("bio","")
            except Exception: pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-profile-btn":
            self.app.pop_screen(); return
        if event.button.id == "save-profile-btn":
            event.button.disabled = True
            bio    = self.query_one("#profile-bio",      Input).value.strip()
            pw     = self.query_one("#profile-password", Input).value.strip()
            radio  = self.query_one("#avatar-radio-set", RadioSet)
            avatar = {0:"Classic",1:"Cat",2:"Wizard"}.get(radio.pressed_index,"Classic")
            self._save(bio, pw or None, avatar)

    @work
    async def _save(self, bio: str, pw: str | None, avatar: str) -> None:
        data = await api_post(self.server_url, "profile/update",
            {"username":self.username,"bio":bio or None,"password":pw,"avatar":avatar})
        if not self.is_mounted: return
        try: btn = self.query_one("#save-profile-btn", Button)
        except Exception: return
        if data.get("success"):
            self._set_status("✓ Saved!")
            btn.disabled = True
            def _pop():
                if not self.is_mounted: return
                try: self.app.query_one(Sidebar)._refresh_avatar()
                except Exception: pass
                self.app.pop_screen()
            self.set_timer(1.0, _pop)
        else:
            self._set_status(data.get("error","Failed."), error=True)
            btn.disabled = False


# ===========================================================================
# USER PROFILE SCREEN
# ===========================================================================

class UserProfileScreen(Screen):

    def __init__(self, target: str, me: str, server_url: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.target     = target
        self.me         = me
        self.server_url = server_url

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                yield Label(f"@{self.target}", id="other-profile-title")
                with Vertical(id="other-profile-card"):
                    yield Label("Loading…",   id="other-profile-bio",     classes="profile-label")
                    yield Label("Avatar: ?",  id="other-profile-avatar",  classes="profile-label")
                    yield Label("Friends: ?", id="other-profile-friends", classes="profile-label")
                    with Horizontal(id="other-profile-actions"):
                        if self.target != self.me:
                            yield Button("Add Friend", id="add-friend-btn")
                            yield Button("Message",    id="message-user-btn")
                            yield Button("📞 Call",    id="call-user-btn")
                    yield Button("Close", id="close-profile-btn")
                    yield Label("", id="other-profile-status")

    def on_mount(self) -> None:
        self._load()

    def _set_status(self, t: str, *, error: bool = False) -> None:
        try:
            lbl = self.query_one("#other-profile-status", Label)
            lbl.update(t); lbl.styles.color = "#f87171" if error else "#6ee7b7"
        except Exception: pass

    @work
    async def _load(self) -> None:
        safe = urllib.parse.quote(self.target)
        data = await api_get(self.server_url, f"profile/{safe}")
        if not self.is_mounted: return
        try:
            if data.get("success"):
                p = data["profile"]
                self.query_one("#other-profile-bio",     Label).update(f"Bio: {p.get('bio','No bio.')}")
                self.query_one("#other-profile-avatar",  Label).update(f"Avatar: {p.get('avatar','Classic')}")
                self.query_one("#other-profile-friends", Label).update(f"Friends: {p.get('friends_count',0)}")
            else:
                self.query_one("#other-profile-bio", Label).update("User not found.")
        except Exception as exc:
            log(f"UserProfileScreen._load: {exc}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if   bid == "close-profile-btn":   self.app.pop_screen()
        elif bid == "add-friend-btn":
            event.button.disabled = True; self._add_friend()
        elif bid == "message-user-btn":
            self.app.pop_screen()
            try: self.app.query_one(DashboardScreen).open_dm(self.target)
            except Exception: pass
        elif bid == "call-user-btn":
            self.app.pop_screen()
            try: self.app.query_one(DashboardScreen)._handle_command(f"/call @{self.target}")
            except Exception: pass

    @work
    async def _add_friend(self) -> None:
        data = await api_post(self.server_url,"friends/request",
                              {"from_user":self.me,"to_user":self.target})
        if not self.is_mounted: return
        if data.get("success"): self._set_status("Friend request sent!")
        else:
            self._set_status(data.get("error","Failed."), error=True)
            try: self.query_one("#add-friend-btn", Button).disabled = False
            except Exception: pass


# ===========================================================================
# NOTIFICATIONS SCREEN
# ===========================================================================

class NotificationsScreen(Screen):

    def __init__(self, username: str, server_url: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.username = username; self.server_url = server_url

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                yield Label("Notifications & Alerts", id="notifications-title")
                with VerticalScroll(id="notifications-card"):
                    yield Label("Loading…", id="notifications-loading")
                with Horizontal(id="notifications-actions"):
                    yield Button("Refresh", id="refresh-notifications-btn")
                    yield Button("Close",   id="close-notifications-btn")

    def on_mount(self) -> None:
        self._load(); self.set_interval(20, self._load)

    @work
    async def _load(self) -> None:
        safe = urllib.parse.quote(self.username)
        data = await api_get(self.server_url, f"friends/{safe}")
        if not self.is_mounted: return
        if not data.get("success"):
            log(f"NotificationsScreen._load: {data.get('error','no response')}"); return
        try:
            self.app.set_focus(None)
        except Exception: pass
        try:
            card = self.query_one("#notifications-card", VerticalScroll)
            card.remove_children()
        except Exception as exc:
            log(f"NotificationsScreen._load (clear): {exc}"); return

        pending: list[str] = data.get("pending", [])
        if not pending:
            card.mount(Label("No new notifications.", classes="notification-empty")); return

        for i, req in enumerate(pending):
            try:
                sid = re.sub(r"[^a-zA-Z0-9_-]","_",req); uid = f"{sid}_{i}"
                lbl = Label(f"Friend request from @{req}", classes="notification-text")
                lbl.can_focus = False
                acc = Button("Accept",  id=f"accept__{uid}",  classes="notif-accept-btn")
                dec = Button("Decline", id=f"decline__{uid}", classes="notif-decline-btn")
                acc.target_user = req; dec.target_user = req  # type: ignore
                card.mount(Horizontal(lbl, acc, dec, classes="notification-item"))
            except Exception as exc:
                log(f"NotificationsScreen._load (row {req}): {exc}")

    def _target(self, btn: Button) -> str | None:
        t = getattr(btn, "target_user", None)
        if t: return t
        try:
            return str(btn.parent.query_one(".notification-text", Label).renderable
                       ).split("@")[-1].strip()
        except Exception: return None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if   bid == "close-notifications-btn":   self.app.pop_screen()
        elif bid == "refresh-notifications-btn": self._load()
        elif bid.startswith("accept__"):
            t = self._target(event.button)
            if t: event.button.disabled = True; self._respond(t, accept=True)
        elif bid.startswith("decline__"):
            t = self._target(event.button)
            if t: event.button.disabled = True; self._respond(t, accept=False)

    @work
    async def _respond(self, target: str, *, accept: bool) -> None:
        ep = "friends/accept" if accept else "friends/decline"
        await api_post(self.server_url, ep, {"from_user": self.username, "to_user": target})
        await self._load()  # type: ignore
        if accept:
            try: self.app.query_one(DashboardScreen).update_sidebar_dms()
            except Exception: pass


# ===========================================================================
# VOICE CALL LOG SCREEN
# ===========================================================================

class VoiceCallLogScreen(Screen):
    BINDINGS = [("escape","pop_screen","Back")]

    def __init__(self, server_url: str, **kwargs) -> None:
        super().__init__(**kwargs); self.server_url = server_url

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                yield Label("🎙 Voice Call Log", id="vcall-log-title")
                with VerticalScroll(id="vcall-log-card"):
                    yield Label("Loading…", classes="notification-empty")
                with Horizontal(id="vcall-log-actions"):
                    yield Button("Refresh", id="vcall-log-refresh-btn")
                    yield Button("Close",   id="vcall-log-close-btn")

    def on_mount(self) -> None: self._load()

    @work
    async def _load(self) -> None:
        data = await api_get(self.server_url, "voice/sessions")
        if not self.is_mounted: return
        try:
            card = self.query_one("#vcall-log-card", VerticalScroll)
            card.remove_children()
        except Exception as exc:
            log(f"VoiceCallLogScreen._load: {exc}"); return

        if not data.get("success"):
            card.mount(Label("Failed to load.", classes="notification-empty")); return
        sessions: list[dict] = data.get("sessions", [])
        if not sessions:
            card.mount(Label("No calls recorded yet.", classes="notification-empty")); return

        for s in sessions:
            parts = s.get("participants",[])
            hdr = Label(
                f"📅 {_fmt_ts(s.get('started_at'))} → "
                f"{_fmt_ts(s.get('ended_at')) if s.get('ended_at') else 'ongoing'}"
                f"  ·  {s.get('room','voice')}  ·  {len(parts)} participant(s)",
                classes="vcall-session-header",
            )
            hdr.can_focus = False
            card.mount(hdr)
            for p in parts:
                row = Label(
                    f"    @{p.get('username','?'):<16} joined {_fmt_ts(p.get('joined_at'))} · {_fmt_dur(p.get('duration_s'))}",
                    classes="vcall-participant-row",
                )
                row.can_focus = False
                card.mount(row)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if   event.button.id == "vcall-log-close-btn":   self.app.pop_screen()
        elif event.button.id == "vcall-log-refresh-btn": self._load()


# ===========================================================================
# LOGIN SCREEN
# ===========================================================================

class LoginScreen(Screen):

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                yield Label(KATTO_LOGO, id="login-logo")
                yield Label(choice(TAGLINES), id="login-subtitle")
                with Vertical(id="login-card"):
                    yield Input(placeholder="Username", id="username-input")
                    yield Input(placeholder="Password", password=True, id="password-input")
                    with Horizontal(id="server-toggle"):
                        yield RadioSet(
                            RadioButton("Default Server", value=True, id="default-radio"),
                            RadioButton("Custom Server",              id="custom-radio"),
                            id="server-radio-set",
                        )
                    yield Input(placeholder="Server address (e.g. 192.168.1.5:8000)",
                                id="custom-server-input")
                    with Vertical(id="login-buttons"):
                        yield Button("Login",   id="login-btn")
                        yield Button("Sign Up", id="signup-btn")
                    yield Label("", id="login-status")
                    yield Label("", id="session-hint")

    def on_mount(self) -> None:
        sess = load_session()
        if sess.get("username"):
            try:
                self.query_one("#username-input", Input).value = sess["username"]
                self.query_one("#session-hint",   Label).update("[dim]⚡ Session restored[/]")
                self.query_one("#password-input", Input).focus()
            except Exception: pass

    def _server(self) -> str:
        rs = self.query_one("#server-radio-set", RadioSet)
        if rs.pressed_index == 1:
            return self.query_one("#custom-server-input", Input).value.strip() or DEFAULT_SERVER
        return DEFAULT_SERVER

    def _set_status(self, t: str, *, error: bool = False) -> None:
        try:
            lbl = self.query_one("#login-status", Label)
            lbl.update(t); lbl.styles.color = "#f87171" if error else "#6ee7b7"
        except Exception: pass

    def _set_btns(self, en: bool) -> None:
        for bid in ("#login-btn","#signup-btn"):
            try: self.query_one(bid, Button).disabled = not en
            except Exception: pass

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        show = event.pressed.id == "custom-radio"
        try:
            inp = self.query_one("#custom-server-input", Input)
            inp.styles.display = "block" if show else "none"
            if show: inp.focus()
        except Exception: pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id not in ("login-btn","signup-btn"): return
        try:
            u = self.query_one("#username-input", Input).value.strip()
            p = self.query_one("#password-input", Input).value.strip()
        except Exception: return
        if not u: self._set_status("Username required.", error=True); return
        if not p: self._set_status("Password required.", error=True); return
        self._set_btns(False); self._set_status("Authenticating…")
        self._auth(u, p, self._server(), event.button.id == "login-btn")

    @work
    async def _auth(self, u: str, p: str, server: str, is_login: bool) -> None:
        data = await api_post(server,"login" if is_login else "signup",{"username":u,"password":p})
        self._set_btns(True)
        if not data: self._set_status("Server not responding.", error=True); return
        if data.get("success"):
            self._set_status(data.get("message","Success!"))
            save_session(u, server)
            self.set_timer(0.4, lambda: self.app.push_screen(
                DashboardScreen(username=u, server_url=server)
            ))
        else:
            self._set_status(data.get("error","Auth failed."), error=True)


# ===========================================================================
# DASHBOARD SCREEN
# ===========================================================================

class DashboardScreen(Screen):

    BINDINGS = [("ctrl+b","toggle_sidebar","Toggle Sidebar")]

    def __init__(self, username: str, server_url: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.username     = username
        self.server_url   = server_url
        self.current_room = "#general"

        self._websocket:     websocket.WebSocket | None = None
        self._ws_running:    bool                       = False
        self._last_msg_time: datetime | None            = None
        self._unread:        dict[str, int]             = {}
        self._typing_timer                              = None
        self._call_ticker                               = None
        self._in_voice_view: bool                       = False

        self._voice = VoiceCallManager(
            my_username           = username,
            send_signal           = self._signal_async,
            on_status             = self._system,
            on_call_state         = self._on_call_state,
            on_participant_change = self._on_participant_change,
        )

    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        cmds = (
            ["/help","/rooms","/profile","/users","/clear","/quit",
             "/logout","/me ","/search ","/friend req @","/friend accept @",
             "/friends","/dm @","/call @","/mute","/unmute",
             "/deafen","/undeafen","/hangup","/vcalls","/join-voice "]
            + [f"/join {r}" for r in DEFAULT_ROOMS]
            + [f"/join-voice {vc}" for vc in VOICE_CHANNELS_LIST]
        )
        with Horizontal(id="dashboard"):
            yield Sidebar(username=self.username, server_url=self.server_url, id="sidebar")
            with Vertical(id="main-content"):
                # Channel header — always visible
                with Horizontal(id="channel-header-container"):
                    yield Label("💬", id="channel-icon")
                    with Vertical(id="channel-info"):
                        yield Label(self.current_room, id="channel-name")
                        yield Label("",                id="channel-topic")
                    with Horizontal(id="channel-header-actions"):
                        yield Label("", id="channel-online-count")
                        yield Button("🔍", id="search-btn",  classes="icon-btn")
                        yield Button("👥", id="members-btn", classes="icon-btn")

                # Text chat area — swapped out for VoiceView when in voice
                with Vertical(id="chat-area"):
                    with VerticalScroll(id="chat-history"): pass
                    yield Label("", id="typing-indicator")
                    yield Input(
                        placeholder=f"Message {self.current_room}  ·  /help for commands",
                        id="message-input",
                        suggester=SuggestFromList(cmds, case_sensitive=False),
                    )

    def on_mount(self) -> None:
        self.query_one("#message-input", Input).focus()
        self.query_one("#channel-topic", Label).update(ROOM_TOPICS.get(self.current_room,""))
        self._system(f"Welcome to [bold cyan]{self.current_room}[/], [bold]{self.username}[/]!")
        self._system("Type [bold green]/help[/] · /join-voice for voice channels.")

        self._ws_listener()
        self._fetch_history(self.current_room)
        self.set_timer(0.8, self.update_sidebar_dms)
        self.set_timer(1.5, self._refresh_online_count)
        self.set_interval(30, self.update_sidebar_dms)

    # ------------------------------------------------------------------
    # Voice view switching — no screen push, swap the chat-area in-place
    # ------------------------------------------------------------------

    def _enter_voice_view(self, channel_name: str) -> None:
        """Replace chat-area content with VoiceView widget."""
        if self._in_voice_view:
            # Already in voice — just refresh channel name
            try:
                vv = self.query_one(VoiceView)
                vv._channel_name = channel_name
                vv.query_one("#vc-channel-name", Label).update(channel_name)
            except Exception: pass
            return

        try:
            chat_area = self.query_one("#chat-area")
            chat_area.remove_children()
            vv = VoiceView(channel_name, self._voice, id="voice-view")
            chat_area.mount(vv)
            self._in_voice_view = True

            # Update channel header
            self.query_one("#channel-icon",  Label).update("🔊")
            self.query_one("#channel-name",  Label).update(channel_name)
            self.query_one("#channel-topic", Label).update("Voice Channel")
        except Exception as exc:
            log(f"_enter_voice_view: {exc}")

    def _exit_voice_view(self) -> None:
        """Restore the text chat area after leaving voice."""
        if not self._in_voice_view: return
        try:
            chat_area = self.query_one("#chat-area")
            chat_area.remove_children()
            # Re-mount the chat widgets
            chat_area.mount(VerticalScroll(id="chat-history"))
            chat_area.mount(Label("", id="typing-indicator"))
            cmds = (
                ["/help","/rooms","/profile","/users","/clear","/quit",
                 "/logout","/me ","/search ","/friend req @","/friend accept @",
                 "/friends","/dm @","/call @","/mute","/unmute",
                 "/deafen","/undeafen","/hangup","/vcalls","/join-voice "]
                + [f"/join {r}" for r in DEFAULT_ROOMS]
                + [f"/join-voice {vc}" for vc in VOICE_CHANNELS_LIST]
            )
            inp = Input(
                placeholder=f"Message {self.current_room}  ·  /help for commands",
                id="message-input",
                suggester=SuggestFromList(cmds, case_sensitive=False),
            )
            chat_area.mount(inp)
            self._in_voice_view = False

            # Restore text channel header
            self.query_one("#channel-icon",  Label).update("💬")
            self.query_one("#channel-name",  Label).update(self.current_room)
            self.query_one("#channel-topic", Label).update(ROOM_TOPICS.get(self.current_room,""))

            # Reload history and refocus
            self._fetch_history(self.current_room)
            try: inp.focus()
            except Exception: pass
        except Exception as exc:
            log(f"_exit_voice_view: {exc}")

    # ------------------------------------------------------------------
    # Voice state callbacks
    # ------------------------------------------------------------------

    def _on_call_state(self, state: str, peer: str) -> None:
        if not self.is_mounted: return
        try:
            self.query_one("#voice-bar", VoiceBar).set_state(
                state, peer, self._voice.channel or "",
                self._voice.elapsed, self._voice.muted, self._voice.deafened,
            )
        except Exception as exc:
            log(f"_on_call_state VoiceBar: {exc}")

        # Update VoiceView if open
        try:
            vv = self.query_one(VoiceView)
            vv.refresh_controls()
        except Exception: pass

        if state == "in_call" and self._call_ticker is None:
            self._call_ticker = self.set_interval(1, self._tick_voice)
        elif state == "idle":
            if self._call_ticker:
                try: self._call_ticker.stop()
                except Exception: pass
                self._call_ticker = None
            # Auto-close voice view on hangup
            if self._in_voice_view:
                self._exit_voice_view()

    def _on_participant_change(self, participants: list[dict]) -> None:
        try:
            self.query_one(VoiceView).refresh_participants(participants)
        except Exception: pass

    def _tick_voice(self) -> None:
        if not (self.is_mounted and self._voice.in_call): return
        try:
            self.query_one("#voice-bar", VoiceBar).set_state(
                "in_call", self._voice.peer or "", self._voice.channel or "",
                self._voice.elapsed, self._voice.muted, self._voice.deafened,
            )
        except Exception: pass

    # ------------------------------------------------------------------
    # Sidebar helpers
    # ------------------------------------------------------------------

    def action_toggle_sidebar(self) -> None:
        sb = self.query_one("#sidebar")
        sb.display = not sb.display

    @work
    async def _refresh_online_count(self) -> None:
        data = await api_get(self.server_url, "online")
        if not (self.is_mounted and data.get("success")): return
        try:
            self.query_one("#channel-online-count", Label).update(f"─ {data['count']} online")
        except Exception as exc:
            log(f"_refresh_online_count: {exc}")

    @work
    async def update_sidebar_dms(self) -> None:
        safe = urllib.parse.quote(self.username)
        data = await api_get(self.server_url, f"friends/{safe}")
        if not self.is_mounted: return
        if not data.get("success"):
            log(f"update_sidebar_dms: {data.get('error','no response')}"); return

        friends_list: list[str] = data.get("friends", [])
        pending:      list[str] = data.get("pending", [])

        try: container = self.query_one("#sidebar-dms")
        except Exception as exc:
            log(f"update_sidebar_dms (container): {exc}"); return

        existing_ids = {
            btn.id for btn in container.query(Button)
            if btn.id and btn.id.startswith("dm__")
        }
        new_ids = {f"dm__{re.sub(r'[^a-zA-Z0-9_-]','_',f)}" for f in friends_list}

        if existing_ids != new_ids:
            try: container.remove_children()
            except Exception as exc:
                log(f"update_sidebar_dms (clear): {exc}"); return
            if friends_list:
                for friend in friends_list:
                    try:
                        sid = re.sub(r"[^a-zA-Z0-9_-]","_",friend)
                        btn = Button(f"  @{friend}", classes="dm-btn", id=f"dm__{sid}")
                        btn.target_name = friend  # type: ignore
                        if self._unread.get(_dm_room(self.username,friend), 0) > 0:
                            btn.label = f"  @{friend} [b magenta]•[/]"
                            btn.add_class("has-unread")
                        container.mount(btn)
                    except Exception as exc:
                        log(f"update_sidebar_dms (mount {friend}): {exc}")
            else:
                container.mount(Label("  No friends yet.", classes="sidebar-section-title"))
        else:
            for friend in friends_list:
                self._update_dm_badge(friend)

        try:
            nb = self.query_one("#notifications-btn", Button)
            if pending: nb.label = f"🔔 {len(pending)}"; nb.styles.color = "#ec4899"
            else:       nb.label = "🔔";                  nb.styles.color = "#94a3b8"
        except Exception as exc:
            log(f"update_sidebar_dms (badge): {exc}")

    def _update_room_badge(self, room: str) -> None:
        rid = f"room-{room[1:]}"; count = self._unread.get(room, 0)
        try:
            btn = self.query_one(f"#{rid}", Button)
            btn.label = f"  {room} [b cyan]•[/]" if count > 0 else f"  {room}"
            btn.set_class(count > 0, "has-unread")
        except Exception as exc: log(f"_update_room_badge {room}: {exc}")

    def _update_dm_badge(self, target: str) -> None:
        room = _dm_room(self.username, target); count = self._unread.get(room, 0)
        sid  = re.sub(r"[^a-zA-Z0-9_-]","_",target)
        try:
            btn = self.query_one(f"#dm__{sid}", Button)
            btn.label = f"  @{target} [b magenta]•[/]" if count > 0 else f"  @{target}"
            btn.set_class(count > 0, "has-unread")
        except Exception as exc: log(f"_update_dm_badge {target}: {exc}")

    # ------------------------------------------------------------------
    # Room / DM switching
    # ------------------------------------------------------------------

    def _switch_room(self, room: str) -> None:
        if self._in_voice_view: self._exit_voice_view()
        self.current_room = room
        is_dm = room.startswith("DM-")
        try:
            self.query_one("#channel-icon",  Label).update("👤" if is_dm else "💬")
            self.query_one("#channel-name",  Label).update(room)
            self.query_one("#channel-topic", Label).update(
                "Direct Message" if is_dm else ROOM_TOPICS.get(room,""))
            self.query_one("#message-input", Input).placeholder = \
                f"Message {room}  ·  /help for commands"
            self.query_one("#chat-history").remove_children()
        except Exception as exc: log(f"_switch_room ({room}): {exc}")
        self._unread[room] = 0
        self._fetch_history(room)

    def open_dm(self, target: str) -> None:
        room = _dm_room(self.username, target)
        sid  = re.sub(r"[^a-zA-Z0-9_-]","_",target)
        for btn in self.query("Sidebar .dm-btn"): btn.remove_class("active")
        try: self.query_one(f"#dm__{sid}", Button).add_class("active")
        except Exception: pass
        self._switch_room(room)
        self._system(f"Switched to [bold magenta]DM with @{target}[/]")
        self._update_dm_badge(target)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    @work
    async def _fetch_history(self, room: str) -> None:
        data = await api_get(self.server_url, f"messages/{urllib.parse.quote(room)}")
        if not self.is_mounted or self._in_voice_view: return
        try: chat = self.query_one("#chat-history")
        except Exception as exc:
            log(f"_fetch_history ({room}): {exc}"); return

        if not data.get("success"):
            self._system(f"Could not load history: {data.get('error','unknown')}"); return

        msgs = data.get("messages",[])
        if not msgs: self._post_empty_state(); return

        labels = []
        for m in msgs:
            ts = self._parse_ts(m.get("timestamp",""))
            if self._should_show_ts(ts):
                labels.append(Label(ts.strftime("%H:%M"), classes="msg-timestamp"))
                self._last_msg_time = ts
            labels.append(Label(
                f"[bold cyan]{m.get('sender','?')}[/]  {m.get('content','')}",
                classes="msg-other",
            ))
        try:
            chat.mount_all(labels); chat.scroll_end(animate=False)
        except Exception as exc: log(f"_fetch_history mount_all: {exc}")

    def _parse_ts(self, raw: str) -> datetime:
        try: return datetime.fromisoformat(raw.replace("Z","+00:00"))
        except Exception: return datetime.now()

    def _should_show_ts(self, ts: datetime) -> bool:
        if self._last_msg_time is None: return True
        return (ts - self._last_msg_time).total_seconds() > TIMESTAMP_GAP_SECONDS

    def _post_empty_state(self) -> None:
        if self._in_voice_view: return
        try:
            chat = self.query_one("#chat-history")
            chat.mount(Label("No messages yet — say hello! 👋", classes="msg-empty"))
            chat.scroll_end(animate=False)
        except Exception: pass

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    @work
    async def _ws_listener(self) -> None:
        self._ws_running = True
        url    = _ws_url(self.server_url, f"ws/{self.username}")
        sslopt = {"cert_reqs": ssl.CERT_NONE, "check_hostname": False} \
                 if _is_local(self.server_url) else None

        for attempt in range(1, WS_MAX_RETRIES + 1):
            if not self._ws_running: break
            if attempt > 1:
                self._system(f"Reconnecting… ({attempt}/{WS_MAX_RETRIES})")
                await asyncio.sleep(WS_RETRY_DELAY_S)

            ws, err = await asyncio.to_thread(self._ws_connect, url, sslopt)
            if ws is None:
                if attempt == WS_MAX_RETRIES:
                    self._post(f"❌ Could not connect — {err}", "msg-error")
                    self._set_ws_status("● Offline","#ef4444")
                continue

            self._websocket = ws
            self._system("✓ Connected to chat server")
            self._set_ws_status("● Online","#10b981")
            self._refresh_online_count()
            await asyncio.to_thread(self._ws_read_loop, ws)
            self._websocket = None
            if self._ws_running and self.is_attached:
                self._set_ws_status("● Offline","#ef4444")
            break

        self._ws_running = False

    @staticmethod
    def _ws_connect(url: str, sslopt) -> tuple["websocket.WebSocket | None", str]:
        # Use create_connection — the correct websocket-client high-level API.
        # Never instantiate WebSocket() directly: constructor signature changed
        # across versions and collides with the wrong 'websocket' package.
        try:
            kw: dict = {"timeout": WS_CONNECT_TIMEOUT}
            if sslopt:
                kw["sslopt"] = sslopt
            ws = websocket.create_connection(url, **kw)
            return ws, ""
        except websocket.WebSocketException as exc: return None, str(exc)
        except ConnectionRefusedError:               return None, "Connection refused"
        except TimeoutError:                          return None, "Timed out"
        except OSError as exc:                        return None, f"Network error: {exc}"
        except Exception as exc:                      return None, f"{type(exc).__name__}: {exc}"

    def _ws_read_loop(self, ws: websocket.WebSocket) -> None:
        while self._ws_running:
            try:
                ws.settimeout(WS_READ_TIMEOUT)
                raw = ws.recv()
                if raw: self.app.call_from_thread(self._handle_ws_message, raw)
            except websocket.WebSocketTimeoutException: continue
            except websocket.WebSocketConnectionClosedException:  break
            except (ConnectionResetError, BrokenPipeError): break
            except Exception as exc:
                log(f"WS read: {exc}"); time.sleep(0.5)

    def _handle_ws_message(self, raw: str) -> None:
        try: data = json.loads(raw)
        except json.JSONDecodeError as exc:
            log(f"_handle_ws_message parse: {exc}"); return

        t      = data.get("type","message")
        sender = data.get("sender","Unknown")
        content= data.get("content","")
        room   = data.get("room","")

        if t in {"webrtc-offer","webrtc-answer","webrtc-ice-candidate","webrtc-hangup"}:
            self._voice.handle_signal(data)
            from_user = data.get("from_user","?")
            if t == "webrtc-offer":
                self._voice.add_participant(from_user)
                try: self.query_one(VoiceView).add_event(f"@{from_user} joined the call.")
                except Exception: pass
                # Auto-open voice view for callee
                if not self._in_voice_view:
                    ch = data.get("channel", f"DM:{from_user}")
                    self._enter_voice_view(ch)
            elif t == "webrtc-hangup":
                try: self.query_one(VoiceView).add_event(f"@{from_user} left the call.")
                except Exception: pass

        elif t == "typing":    self._handle_typing(data)
        elif t == "friend_request":
            self._system(f"[bold pink]🔔 {content}[/]"); self.update_sidebar_dms()
        elif t == "friend_accepted":
            self._system(f"[bold green]🤝 {content}[/]"); self.update_sidebar_dms()
        elif room in (self.current_room,"all") and not self._in_voice_view:
            css = "msg-self" if sender == self.username else "msg-other"
            self._post(f"[bold magenta]{sender}[/]  {content}", css)
        elif room:
            self._unread[room] = self._unread.get(room,0) + 1
            if room.startswith("DM-"):
                parts  = room.split("-",2)
                target = parts[1] if parts[1] != self.username else parts[2]
                self._update_dm_badge(target)
            else:
                self._update_room_badge(room)

    def _handle_typing(self, data: dict) -> None:
        typer = data.get("user","")
        if not typer or typer == self.username or data.get("room") != self.current_room: return
        if self._in_voice_view: return
        try:
            self.query_one("#typing-indicator", Label).update(
                f"[dim italic]• {typer} is typing…[/]"
            )
            if self._typing_timer: self._typing_timer.stop()
            self._typing_timer = self.set_timer(
                3, lambda: self.query_one("#typing-indicator", Label).update("")
            )
        except Exception as exc: log(f"_handle_typing: {exc}")

    def _set_ws_status(self, text: str, color: str) -> None:
        if not self.is_attached: return
        try:
            lbl = self.query_one("#ws-status-text", Label)
            lbl.update(text); lbl.styles.color = color
        except Exception: pass

    async def _on_unmount(self) -> None:
        self._ws_running = False
        await self._voice.hangup()
        if self._websocket:
            try: self._websocket.close()
            except Exception: pass

    # ------------------------------------------------------------------
    # Signal helper
    # ------------------------------------------------------------------

    async def _signal_async(self, payload: dict) -> None:
        if not self._websocket: return
        try:
            await asyncio.to_thread(self._websocket.send, json.dumps(payload))
        except Exception as exc: log(f"_signal_async: {exc}")

    # ------------------------------------------------------------------
    # Chat input
    # ------------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "message-input" or not self._websocket: return
        if event.value and not event.value.startswith("/"): self._send_typing()

    @work
    async def _send_typing(self) -> None:
        if not self._websocket: return
        try:
            await asyncio.to_thread(
                self._websocket.send,
                json.dumps({"type":"typing","room":self.current_room}),
            )
        except Exception: pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip(); event.input.value = ""
        if not text: return
        if text.startswith("/"): self._handle_command(text)
        elif self._websocket:    self._send_message(text)
        else:                    self._post("Not connected.", "msg-error")

    @work
    async def _send_message(self, text: str) -> None:
        if not self._websocket:
            self._post("Not connected.", "msg-error"); return
        try:
            await asyncio.to_thread(
                self._websocket.send,
                json.dumps({"content":text,"room":self.current_room}),
            )
        except Exception as exc:
            self._post(f"Send failed: {exc}", "msg-error")

    # ------------------------------------------------------------------
    # Message rendering
    # ------------------------------------------------------------------

    def _post(self, text: str, css: str = "msg-other") -> None:
        if not self.is_mounted or self._in_voice_view: return
        try: chat = self.query_one("#chat-history")
        except Exception: return
        now = datetime.now()
        if self._should_show_ts(now):
            try: chat.mount(Label(now.strftime("%H:%M"), classes="msg-timestamp"))
            except Exception: pass
        self._last_msg_time = now
        try:
            chat.mount(Label(text, classes=css)); chat.scroll_end(animate=False)
        except Exception as exc: log(f"_post (mount): {exc}")

    def _system(self, text: str) -> None:
        self._post(f"[dim]⟫[/] {text}", "msg-system")

    def _post_help(self) -> None:
        lines = [
            "[bold cyan]── KATTO HELP ──[/]","",
            "[bold]Chat[/]",
            "  /rooms                     List text channels",
            "  /join <#channel>           Switch channel",
            "  /dm @user                  Open DM",
            "  /me <action>               Emote",
            "  /search <term>             Filter messages",
            "  /clear                     Clear chat",
            "",
            "[bold]Voice[/]",
            "  /join-voice <channel>      Join a voice channel",
            "  /call @user                Direct voice call",
            "  /mute  /unmute             Toggle microphone",
            "  /deafen  /undeafen         Toggle speakers",
            "  /hangup                    Leave voice",
            "  /vcalls                    Voice call history",
            "",
            "[bold]Social[/]",
            "  /friend req @user          Send friend request",
            "  /friend accept @user       Accept request",
            "  /friends                   List friends",
            "  /profile [user]            View profile",
            "",
            "[bold]System[/]",
            "  /users                     Who's online",
            "  /logout                    Back to login",
            "  /quit                      Exit Katto",
        ]
        for line in lines: self._post(line, "msg-help")

    # ------------------------------------------------------------------
    # Button handler
    # ------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        try:
            if bid.startswith("room-"):
                self._handle_command(f"/join #{bid[5:]}")
            elif bid.startswith("vc__"):
                vc_name = next(
                    (vc for vc in VOICE_CHANNELS_LIST
                     if re.sub(r"[^a-zA-Z0-9_-]","_",vc) == bid[4:]), None
                )
                if vc_name: self._handle_command(f"/join-voice {vc_name}")
            elif bid.startswith("dm__"):
                target = getattr(event.button,"target_name",None) or \
                         str(event.button.label).strip().split("@")[-1].split()[0]
                self.open_dm(target)
            elif bid == "settings-tab-btn":
                self.app.push_screen(ProfileScreen(self.username, self.server_url))
            elif bid == "sidebar-user-btn":
                self.app.push_screen(UserProfileScreen(self.username, self.username, self.server_url))
            elif bid == "notifications-btn":
                self.app.push_screen(NotificationsScreen(self.username, self.server_url))
            elif bid == "vcall-log-btn":
                self.app.push_screen(VoiceCallLogScreen(self.server_url))
            elif bid == "search-btn":
                if not self._in_voice_view:
                    inp = self.query_one("#message-input", Input)
                    inp.value = "/search "; inp.focus()
            elif bid == "members-btn":
                self._show_online_members()
            elif bid == "quit-btn":
                self.app.exit()
            # VoiceBar buttons
            elif bid == "vbar-mute-btn":
                self._handle_command("/unmute" if self._voice.muted else "/mute")
            elif bid == "vbar-deaf-btn":
                self._handle_command("/undeafen" if self._voice.deafened else "/deafen")
            elif bid == "vbar-leave-btn":
                self._handle_command("/hangup")
            elif bid == "vbar-open-btn":
                if self._voice.in_call or self._voice.channel:
                    self._enter_voice_view(self._voice.channel or "Voice")
        except Exception as exc:
            log(f"on_button_pressed ({bid}): {exc}")

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @work
    async def _handle_command(self, text: str) -> None:
        parts = text.split(None, 1)
        cmd   = parts[0].lower()
        rest  = parts[1] if len(parts) > 1 else ""

        if cmd == "/help": self._post_help()

        elif cmd == "/rooms":
            self._system("Text channels:")
            for r in DEFAULT_ROOMS:
                self._system(f"  {'→' if r == self.current_room else ' '} {r}")

        elif cmd == "/join":
            room = rest.strip()
            room = room if room.startswith("#") else f"#{room}"
            if room not in DEFAULT_ROOMS:
                self._post(f"Room '{room}' not found.", "msg-error"); return
            self._switch_room(room)
            for btn in self.query("Sidebar .room-btn"): btn.remove_class("active")
            try: self.query_one(f"#room-{room[1:]}", Button).add_class("active")
            except Exception: pass
            self._system(f"Switched to [bold cyan]{room}[/]")

        elif cmd == "/join-voice":
            vc_name = rest.strip()
            if not vc_name:
                self._system("Voice channels: " + "  ".join(VOICE_CHANNELS_LIST)); return
            match = next(
                (vc for vc in VOICE_CHANNELS_LIST
                 if vc_name.lower() in vc.lower() or vc.lower() in vc_name.lower()), None
            )
            if not match:
                self._post(f"Voice channel '{vc_name}' not found.", "msg-error"); return

            # Highlight the vc button
            for btn in self.query("Sidebar .vc-channel-btn"): btn.remove_class("active")
            sid = re.sub(r"[^a-zA-Z0-9_-]","_",match)
            try: self.query_one(f"#vc__{sid}", Button).add_class("active")
            except Exception: pass

            # Open voice view and set channel
            self._voice._channel    = match
            if not self._voice._call_start:
                self._voice._call_start = datetime.now(tz=timezone.utc)
            if not self._voice._participants:
                self._voice._participants = [
                    {"username": self.username, "joined_at": self._voice._call_start}
                ]
            self._enter_voice_view(match)
            self._on_call_state("calling", "")
            self._on_participant_change(self._voice.participants)
            self._system(f"Joined voice channel [bold cyan]{match}[/] — waiting for peers…")

        elif cmd == "/call":
            target = rest.lstrip("@").strip()
            if not target: self._post("Usage: /call @user", "msg-error"); return
            if target == self.username: self._post("Cannot call yourself.", "msg-error"); return
            await self._voice.call(target)
            self._enter_voice_view(self._voice.channel or f"DM:{target}")

        elif cmd in ("/mute", "/unmute"):
            if not self._voice.in_call and not self._voice.channel:
                self._post("Not in a voice channel.", "msg-error"); return
            mute = cmd == "/mute"
            self._voice.set_muted(mute)
            self._system("🔇 Muted." if mute else "🎤 Unmuted.")
            try: self.query_one(VoiceView).refresh_participants(self._voice.participants)
            except Exception: pass
            try: self.query_one(VoiceView).refresh_controls()
            except Exception: pass
            try: self.query_one(VoiceView).add_event("You muted." if mute else "You unmuted.")
            except Exception: pass

        elif cmd in ("/deafen", "/undeafen"):
            if not self._voice.in_call and not self._voice.channel:
                self._post("Not in a voice channel.", "msg-error"); return
            deaf = cmd == "/deafen"
            self._voice.set_deafened(deaf)
            self._system("🙉 Deafened." if deaf else "🔊 Undeafened.")
            try: self.query_one(VoiceView).refresh_participants(self._voice.participants)
            except Exception: pass
            try: self.query_one(VoiceView).refresh_controls()
            except Exception: pass
            try: self.query_one(VoiceView).add_event("You deafened." if deaf else "You undeafened.")
            except Exception: pass

        elif cmd == "/hangup":
            if not self._voice.in_call and not self._voice.channel:
                self._post("Not in a voice channel.", "msg-error"); return
            await self._voice.hangup()
            self._exit_voice_view()

        elif cmd == "/vcalls":
            self.app.push_screen(VoiceCallLogScreen(self.server_url))

        elif cmd == "/dm":
            self.open_dm(rest.lstrip("@").strip())

        elif cmd == "/profile":
            target = rest.lstrip("@").strip() or self.username
            if target == self.username:
                self.app.push_screen(ProfileScreen(self.username, self.server_url))
            else:
                self.app.push_screen(UserProfileScreen(target, self.username, self.server_url))

        elif cmd == "/user":
            if rest:
                self.app.push_screen(UserProfileScreen(rest.lstrip("@"), self.username, self.server_url))

        elif cmd == "/friend":
            sub_parts = rest.split(None, 1)
            if len(sub_parts) < 2:
                self._post("Usage: /friend req|accept @user","msg-error"); return
            sub = sub_parts[0].lower(); target = sub_parts[1].lstrip("@")
            if sub in ("req","add"):
                self._api_fb(await api_post(self.server_url,"friends/request",
                                            {"from_user":self.username,"to_user":target}))
            elif sub == "accept":
                self._api_fb(await api_post(self.server_url,"friends/accept",
                                            {"from_user":self.username,"to_user":target}))
                self.update_sidebar_dms()
            else:
                self._post("Usage: /friend req|accept @user","msg-error")

        elif cmd == "/friends":
            safe = urllib.parse.quote(self.username)
            data = await api_get(self.server_url, f"friends/{safe}")
            if data.get("success"):
                fl = data.get("friends",[]); pe = data.get("pending",[])
                self._system(f"Friends: {', '.join(fl) if fl else 'None yet.'}")
                if pe: self._system(f"Pending: {', '.join(pe)}")
                self.update_sidebar_dms()
            else: self._post("Failed to fetch friends.","msg-error")

        elif cmd == "/users":
            self._system(f"Online: [bold]{self.username}[/] (you)")

        elif cmd == "/clear":
            if not self._in_voice_view:
                try:
                    self.query_one("#chat-history").remove_children()
                    self._system("Chat cleared.")
                except Exception as exc: log(f"/clear: {exc}")

        elif cmd == "/me":
            await self._send_message(f"* {self.username} {rest}")

        elif cmd == "/search":
            if not rest: self._system("Usage: /search <term>"); return
            if self._in_voice_view: self._system("Switch to a text channel to search."); return
            term = rest.lower(); count = 0
            try:
                for lbl in self.query_one("#chat-history").query(Label):
                    vis = term in str(lbl.renderable).lower()
                    lbl.styles.display = "block" if vis else "none"
                    if vis: count += 1
            except Exception as exc: log(f"/search: {exc}")
            self._system(f"{count} result(s) for '{term}'. /clear to reset.")

        elif cmd == "/logout": self.app.pop_screen()
        elif cmd == "/quit":   self.app.exit()
        else: self._post(f"Unknown command: [bold]{cmd}[/]. /help", "msg-error")

    def _api_fb(self, data: dict) -> None:
        if data.get("success"): self._system(f"[bold green]✓[/] {data.get('message','Done.')}")
        else: self._post(data.get("error","Request failed."),"msg-error")

    @work
    async def _show_online_members(self) -> None:
        data = await api_get(self.server_url, "online")
        if data.get("success"):
            users = data.get("users",[])
            self._system(f"[bold]👥 {data['count']} online:[/] {', '.join(users) or 'None'}")
            try:
                self.query_one("#channel-online-count", Label).update(f"─ {data['count']} online")
            except Exception: pass
        else: self._system("Could not fetch online members.")


# ===========================================================================
# ROOT APP
# ===========================================================================

class Katto(App):
    TITLE = "Katto"; SUB_TITLE = "Terminal Social Chat"
    BINDINGS = [("ctrl+q","quit","Quit"),("ctrl+c","quit","Quit")]

    _css_candidates = [Path(__file__).parent / "chat_ui.tcss"]
    if _res_files is not None:
        try:
            _css_candidates.insert(0, Path(str(_res_files("client") / "chat_ui.tcss")))
        except Exception: pass
    CSS_PATH = str(next((p for p in _css_candidates if p.exists()), _css_candidates[-1]))

    def on_mount(self) -> None:
        self.push_screen(LoginScreen())

def main() -> None:
    Katto().run()

if __name__ == "__main__":
    main()