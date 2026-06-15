"""
Hype detector.
Watches the chat message rate and fires a callback when a spike is detected.
Includes cooldown logic to prevent back-to-back clips.
"""
import threading
import time
from typing import Callable, Optional
from collections import deque


class HypeDetector:
    """
    Monitors message-per-second rate and triggers clips when rate exceeds threshold.
    Uses a cooldown period to avoid duplicate clips during sustained hype.
    """

    def __init__(
        self,
        threshold: float = 8.0,       # msgs/sec to trigger clip
        cooldown: float = 30.0,        # seconds between clips
        check_interval: float = 0.5,   # how often to check rate
    ):
        self.threshold = threshold
        self.cooldown = cooldown
        self.check_interval = check_interval

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_clip_time: float = 0
        self._current_rate: float = 0

        self.on_clip_triggered: Optional[Callable[[float], None]] = None  # rate
        self.on_rate_change: Optional[Callable[[float, float], None]] = None  # rate, threshold
        self.get_rate: Optional[Callable[[], float]] = None  # injected from chat monitor

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def in_cooldown(self) -> bool:
        return time.time() - self._last_clip_time < self.cooldown

    def cooldown_remaining(self) -> float:
        remaining = self.cooldown - (time.time() - self._last_clip_time)
        return max(0.0, remaining)

    def reset_cooldown(self):
        self._last_clip_time = 0

    def _loop(self):
        while self._running:
            time.sleep(self.check_interval)
            if not self.get_rate:
                continue

            rate = self.get_rate()
            self._current_rate = rate

            if self.on_rate_change:
                self.on_rate_change(rate, self.threshold)

            if rate >= self.threshold and not self.in_cooldown():
                self._last_clip_time = time.time()
                if self.on_clip_triggered:
                    self.on_clip_triggered(rate)
