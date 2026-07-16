"""
Multi-channel Twitch IRC chat monitor and hype detector.
Connects anonymously to Twitch IRC and monitors multiple channels in a single socket connection.
Detects synchronized chat spikes across multiple channels.
"""
import socket
import threading
import time
import re
from collections import deque
from typing import Callable, Optional, List, Dict


class MultiTwitchChatMonitor:
    """
    Connects to Twitch IRC and monitors chat message rates for multiple channels simultaneously.
    Uses a single SSL/TLS socket connection and JOINs multiple channels.
    """

    TWITCH_HOST = "irc.chat.twitch.tv"
    TWITCH_PORT = 6697
    NICK = "justinfan83421"  # Anonymous Nick
    RATE_WINDOW = 5          # seconds to measure rate over

    def __init__(self):
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._channels: List[str] = []

        # Dict of rolling windows of message timestamps for each channel: {channel: deque}
        self._msg_times: Dict[str, deque] = {}
        self._lock = threading.Lock()

        # Callbacks
        self.on_message: Optional[Callable[[str, str, str], None]] = None     # (channel, username, message)
        self.on_rate_update: Optional[Callable[[Dict[str, float]], None]] = None  # {channel: msgs/sec}
        self.on_connected: Optional[Callable[[], None]] = None
        self.on_disconnected: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

    def connect(self, channels: List[str]):
        """Connect to multiple Twitch channels. Channel names without #."""
        with self._lock:
            self._channels = [ch.lower().lstrip("#") for ch in channels if ch.strip()]
            self._msg_times = {ch: deque() for ch in self._channels}
        
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

    def get_rates(self) -> Dict[str, float]:
        """Get current message rates (msgs/sec) for all monitored channels."""
        cutoff = time.time() - self.RATE_WINDOW
        rates = {}
        with self._lock:
            for ch in self._channels:
                times = self._msg_times.get(ch)
                if times is None:
                    rates[ch] = 0.0
                    continue
                while times and times[0][0] < cutoff:
                    times.popleft()
                total_weight = sum(item[1] for item in times)
                rates[ch] = total_weight / self.RATE_WINDOW
        return rates

    def get_rate(self, channel: str) -> float:
        """Get message rate for a specific channel."""
        ch = channel.lower().lstrip("#")
        cutoff = time.time() - self.RATE_WINDOW
        with self._lock:
            times = self._msg_times.get(ch)
            if not times:
                return 0.0
            while times and times[0][0] < cutoff:
                times.popleft()
            total_weight = sum(item[1] for item in times)
            return total_weight / self.RATE_WINDOW

    def _run(self):
        retry_delay = 2
        while self._running:
            try:
                self._connect_and_listen()
                retry_delay = 2
            except Exception as e:
                if self._running:
                    msg = str(e)
                    if self.on_error:
                        self.on_error(f"Chat monitor error: {msg}")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 30)

    def _connect_and_listen(self):
        import ssl
        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_sock.settimeout(10)
        context = ssl.create_default_context()
        self._sock = context.wrap_socket(raw_sock, server_hostname=self.TWITCH_HOST)
        self._sock.connect((self.TWITCH_HOST, self.TWITCH_PORT))
        self._sock.settimeout(None)

        # Send IRC Handshake
        self._send(f"NICK {self.NICK}")
        self._send(f"USER {self.NICK} 0 * :{self.NICK}")

        # Join all channels in comma-separated format
        with self._lock:
            if self._channels:
                channel_list = ",".join([f"#{ch}" for ch in self._channels])
                self._send(f"JOIN {channel_list}")

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
        if line.startswith("PING"):
            self._send("PONG " + line[5:])
            return

        # Parse PRIVMSG format: :username!user@user.tmi.twitch.tv PRIVMSG #channel :message
        match = re.match(r":([^!]+)![^ ]+ PRIVMSG #(\w+) :(.+)", line)
        if match:
            username = match.group(1)
            channel = match.group(2).lower()
            message = match.group(3)
            now = time.time()

            # Determine message weight (signal boost)
            weight = 1.0
            if re.search(r'\b(clip|lul|omegalul|w)\b', message, re.IGNORECASE):
                weight = 1.5
            elif any(w.isupper() and len(w) >= 6 for w in re.findall(r'\b[A-Za-z0-9_]+\b', message)):
                weight = 1.5

            with self._lock:
                if channel in self._msg_times:
                    self._msg_times[channel].append((now, weight))

            if self.on_message:
                self.on_message(channel, username, message)
            if self.on_rate_update:
                self.on_rate_update(self.get_rates())

    def _send(self, msg: str):
        if self._sock:
            self._sock.sendall((msg + "\r\n").encode("utf-8"))


class MultiHypeDetector:
    """
    Monitors message-per-second rates for multiple channels.
    Triggers a synchronized global event when channels spike together.
    """

    def __init__(
        self,
        threshold: float = 8.0,        # msgs/sec threshold
        cooldown: float = 45.0,         # global cooldown between cuts (larger for compilations)
        sync_window: float = 12.0,      # window (secs) to correlate streamer spikes
        min_sync_count: int = 2,        # min number of streamers spiking to trigger clip
        check_interval: float = 0.5,    # rate checking interval
        detection_mode: str = "relative",  # "relative" or "absolute"
        multiplier: float = 3.0,
        min_floor: float = 2.0,
        warmup: float = 60.0,
    ):
        self.threshold = threshold
        self.cooldown = cooldown
        self.sync_window = sync_window
        self.min_sync_count = min_sync_count
        self.check_interval = check_interval
        self.detection_mode = detection_mode
        self.multiplier = multiplier
        self.min_floor = min_floor
        self.warmup = warmup

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_global_clip: float = 0.0
        self._connect_time: float = 0.0
        
        # Track last individual spike time for each channel: {channel: timestamp}
        self._last_spikes: Dict[str, float] = {}
        # Track EMA baselines per channel
        self._baselines: Dict[str, float] = {}
        self._ema_alpha: float = 0.0023
        
        # Callbacks
        self.on_global_clip_triggered: Optional[Callable[[Dict[str, float]], None]] = None  # {channel: rate}
        self.on_rates_change: Optional[Callable[[Dict[str, float], float], None]] = None     # rates_dict, threshold
        self.get_rates: Optional[Callable[[], Dict[str, float]]] = None  # Injected

    def start(self):
        self._running = True
        self._connect_time = time.time()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def in_global_cooldown(self) -> bool:
        return time.time() - self._last_global_clip < self.cooldown

    def global_cooldown_remaining(self) -> float:
        remaining = self.cooldown - (time.time() - self._last_global_clip)
        return max(0.0, remaining)

    def reset_cooldown(self):
        self._last_global_clip = 0.0
        self._last_spikes = {}

    def get_effective_threshold(self, channel: str = None) -> float:
        if self.detection_mode == "relative":
            if channel and channel in self._baselines:
                return max(self.min_floor, self.multiplier * self._baselines[channel])
            avg_baseline = sum(self._baselines.values()) / len(self._baselines) if self._baselines else 0.0
            return max(self.min_floor, self.multiplier * avg_baseline)
        return self.threshold

    def _loop(self):
        while self._running:
            time.sleep(self.check_interval)
            if not self.get_rates:
                continue

            rates = self.get_rates()

            # Update EMA baselines
            for ch, rate in rates.items():
                if ch not in self._baselines:
                    self._baselines[ch] = rate
                else:
                    self._baselines[ch] = self._ema_alpha * rate + (1 - self._ema_alpha) * self._baselines[ch]

            effective_threshold = self.get_effective_threshold()

            if self.on_rates_change:
                self.on_rates_change(rates, effective_threshold)

            # Do not process trigger if we are in global cooldown or warmup
            if self.in_global_cooldown():
                continue
            if time.time() - self._connect_time < self.warmup:
                continue

            now = time.time()

            # Update individual channel spikes
            for ch, rate in rates.items():
                ch_threshold = self.get_effective_threshold(ch)
                if rate >= ch_threshold:
                    self._last_spikes[ch] = now

            # Count how many channels spiked within the sync window
            spiked_recent = []
            for ch in rates.keys():
                last_t = self._last_spikes.get(ch, 0.0)
                if now - last_t <= self.sync_window:
                    spiked_recent.append(ch)

            # If the sync condition is met (e.g. at least 2 channels spiked recently)
            if len(spiked_recent) >= self.min_sync_count:
                self._last_global_clip = now
                # Clean spikes to prevent immediate re-trigger
                self._last_spikes = {}
                if self.on_global_clip_triggered:
                    # Pass the active rates of the spiking channels
                    triggered_info = {ch: rates.get(ch, 0.0) for ch in spiked_recent}
                    self.on_global_clip_triggered(triggered_info)
