"""
Hype detector.
Watches the chat message rate and fires a callback when a spike is detected.
Includes cooldown logic to prevent back-to-back clips.
"""
import threading
import time
import re
from typing import Callable, Optional


class HypeDetector:
    """
    Monitors message-per-second rate and triggers clips when rate exceeds threshold.
    Supports absolute and relative detection modes, rolling baseline, and warmup.
    """

    def __init__(
        self,
        threshold: float = 8.0,       # msgs/sec to trigger clip (absolute mode)
        cooldown: float = 30.0,        # seconds between clips
        check_interval: float = 0.5,   # how often to check rate
        detection_mode: str = "relative",  # "relative" or "absolute"
        multiplier: float = 3.0,
        min_floor: float = 2.0,
        warmup: float = 60.0,
    ):
        self.threshold = threshold
        self.cooldown = cooldown
        self.check_interval = check_interval
        self.detection_mode = detection_mode
        self.multiplier = multiplier
        self.min_floor = min_floor
        self.warmup = warmup

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_clip_time: float = 0
        self._current_rate: float = 0
        self._baseline: float = 0.0
        self._ema_alpha: float = 0.0023  # EMA alpha for ~5 minutes at 0.5s check intervals
        self._connect_time: float = 0.0

        self.on_clip_triggered: Optional[Callable[[float], None]] = None  # rate
        self.on_rate_change: Optional[Callable[[float, float], None]] = None  # rate, threshold
        self.get_rate: Optional[Callable[[], float]] = None  # injected from chat monitor

    def start(self):
        self._running = True
        self._connect_time = time.time()
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

    def get_baseline(self) -> float:
        return self._baseline

    def get_effective_threshold(self) -> float:
        if self.detection_mode == "relative":
            return max(self.min_floor, self.multiplier * self._baseline)
        return self.threshold

    def _loop(self):
        while self._running:
            time.sleep(self.check_interval)
            if not self.get_rate:
                continue

            rate = self.get_rate()
            self._current_rate = rate

            # Update EMA baseline
            if self._baseline == 0.0 and rate > 0:
                self._baseline = rate
            else:
                self._baseline = self._ema_alpha * rate + (1 - self._ema_alpha) * self._baseline

            effective_threshold = self.get_effective_threshold()

            if self.on_rate_change:
                self.on_rate_change(rate, effective_threshold)

            # Warmup check
            if time.time() - self._connect_time < self.warmup:
                continue

            if rate >= effective_threshold and not self.in_cooldown():
                self._last_clip_time = time.time()
                if self.on_clip_triggered:
                    self.on_clip_triggered(rate)
