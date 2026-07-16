"""
Twitch IRC chat monitor.
Connects anonymously to Twitch IRC (no API key needed for read-only chat).
Uses socket directly - no external websocket library required.
"""
import socket
import threading
import time
import re
from collections import deque
from typing import Callable, Optional


class TwitchChatMonitor:
    """
    Connects to Twitch IRC and monitors chat message rate.
    Twitch IRC is accessible anonymously over plain TCP on port 6667.
    No OAuth token needed for read-only chat monitoring.
    """

    TWITCH_HOST = "irc.chat.twitch.tv"
    TWITCH_PORT = 6667
    NICK = "justinfan83421"   # justinfan + any number = anonymous login
    RATE_WINDOW = 5           # seconds to measure message rate over

    def __init__(self):
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._channel = ""

        # Rolling window of message timestamps for rate calculation
        self._msg_times: deque = deque()

        # Callbacks
        self.on_message: Optional[Callable[[str, str], None]] = None   # (username, message)
        self.on_rate_update: Optional[Callable[[float], None]] = None  # msgs/sec
        self.on_connected: Optional[Callable[[], None]] = None
        self.on_disconnected: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

    # ── Public API ────────────────────────────────────────────────────────

    def connect(self, channel: str):
        """Connect to a Twitch channel's chat. Channel name without #."""
        self._channel = channel.lower().lstrip("#")
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def disconnect(self):
        """Disconnect cleanly."""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None

    def get_rate(self) -> float:
        """Current message rate in messages per second (over RATE_WINDOW)."""
        cutoff = time.time() - self.RATE_WINDOW
        while self._msg_times and self._msg_times[0][0] < cutoff:
            self._msg_times.popleft()
        total_weight = sum(item[1] for item in self._msg_times)
        return total_weight / self.RATE_WINDOW

    # ── Internal ──────────────────────────────────────────────────────────

    def _run(self):
        retry_delay = 2
        while self._running:
            try:
                self._connect_and_listen()
                retry_delay = 2  # reset on clean exit
            except Exception as e:
                if self._running:
                    msg = str(e)
                    if self.on_error:
                        self.on_error(f"Chat connection error: {msg}")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 30)

    def _connect_and_listen(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(10)
        self._sock.connect((self.TWITCH_HOST, self.TWITCH_PORT))
        self._sock.settimeout(None)

        # IRC handshake
        self._send(f"NICK {self.NICK}")
        self._send(f"USER {self.NICK} 0 * :{self.NICK}")
        self._send(f"JOIN #{self._channel}")

        if self.on_connected:
            self.on_connected()

        buf = ""
        while self._running:
            try:
                data = self._sock.recv(4096).decode("utf-8", errors="replace")
                if not data:
                    break
                buf += data
                while "\r\n" in buf:
                    line, buf = buf.split("\r\n", 1)
                    self._handle_line(line)
            except socket.timeout:
                continue
            except OSError:
                break

        if self.on_disconnected:
            self.on_disconnected("Disconnected")

    def _handle_line(self, line: str):
        # Respond to PING to stay alive
        if line.startswith("PING"):
            self._send("PONG " + line[5:])
            return

        # Parse PRIVMSG  :username!user@user.tmi.twitch.tv PRIVMSG #channel :message
        match = re.match(
            r":([^!]+)![^ ]+ PRIVMSG #\w+ :(.+)", line
        )
        if match:
            username = match.group(1)
            message = match.group(2)
            now = time.time()
            
            # Determine message weight (signal boost)
            weight = 1.0
            if re.search(r'\b(clip|lul|omegalul|w)\b', message, re.IGNORECASE):
                weight = 1.5
            elif any(w.isupper() and len(w) >= 6 for w in re.findall(r'\b[A-Za-z0-9_]+\b', message)):
                weight = 1.5
                
            self._msg_times.append((now, weight))

            if self.on_message:
                self.on_message(username, message)
            if self.on_rate_update:
                self.on_rate_update(self.get_rate())

    def _send(self, msg: str):
        if self._sock:
            self._sock.sendall((msg + "\r\n").encode("utf-8"))
