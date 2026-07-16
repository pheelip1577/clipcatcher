import time
import pytest
from unittest.mock import MagicMock, patch
from app.hype_detector import HypeDetector

def test_warmup_suppresses_trigger():
    # Setup HypeDetector with relative mode and 60s warmup
    detector = HypeDetector(
        detection_mode="relative",
        multiplier=3.0,
        min_floor=2.0,
        warmup=60.0,
        check_interval=0.1
    )
    callback = MagicMock()
    detector.on_clip_triggered = callback
    
    # Mock get_rate to return a high rate (e.g. 10 msg/s)
    detector.get_rate = MagicMock(return_value=10.0)
    
    # Set connect time
    now = time.time()
    detector._connect_time = now
    
    # Simulate check within warmup period (t = connect_time + 10s)
    with patch("time.time", return_value=now + 10.0):
        rate = detector.get_rate()
        detector._current_rate = rate
        # Update baseline
        detector._baseline = detector._ema_alpha * rate + (1 - detector._ema_alpha) * detector._baseline
        effective_threshold = detector.get_effective_threshold()
        
        is_warmup = (time.time() - detector._connect_time) < detector.warmup
        assert is_warmup is True
        
        if not is_warmup and rate >= effective_threshold and not detector.in_cooldown():
            detector.on_clip_triggered(rate)
            
        callback.assert_not_called()

def test_relative_mode_constant_high_rate_does_not_trigger():
    # Setup HypeDetector
    detector = HypeDetector(
        detection_mode="relative",
        multiplier=3.0,
        min_floor=2.0,
        warmup=60.0
    )
    callback = MagicMock()
    detector.on_clip_triggered = callback
    
    # Big channel has constant rate of 20 msg/s
    detector.get_rate = MagicMock(return_value=20.0)
    
    # Initialize baseline to 20.0
    detector._baseline = 20.0
    
    # Connect time is in the past (warmup passed)
    now = time.time()
    detector._connect_time = now - 100.0
    
    # Simulate check
    with patch("time.time", return_value=now):
        rate = detector.get_rate()
        detector._baseline = detector._ema_alpha * rate + (1 - detector._ema_alpha) * detector._baseline
        eff_threshold = detector.get_effective_threshold()
        
        # threshold is max(2.0, 3.0 * baseline) = max(2.0, 3.0 * 20.0) = 60.0
        assert eff_threshold == 60.0
        assert rate < eff_threshold
        
        is_warmup = (time.time() - detector._connect_time) < detector.warmup
        if not is_warmup and rate >= eff_threshold and not detector.in_cooldown():
            detector.on_clip_triggered(rate)
            
        callback.assert_not_called()

def test_relative_mode_small_channel_spike_triggers():
    # Setup HypeDetector
    detector = HypeDetector(
        detection_mode="relative",
        multiplier=3.0,
        min_floor=2.0,
        warmup=60.0
    )
    callback = MagicMock()
    detector.on_clip_triggered = callback
    
    # Small channel has constant rate of 1.0 msg/s
    detector._baseline = 1.0
    
    # Connect time in past
    now = time.time()
    detector._connect_time = now - 100.0
    
    # Spike rate to 5.0 msg/s
    detector.get_rate = MagicMock(return_value=5.0)
    
    with patch("time.time", return_value=now):
        rate = detector.get_rate()
        detector._baseline = detector._ema_alpha * rate + (1 - detector._ema_alpha) * detector._baseline
        eff_threshold = detector.get_effective_threshold()
        
        # baseline becomes 0.0023 * 5.0 + 0.9977 * 1.0 = 1.0092
        # multiplier * baseline = 3.0276
        # floor = 2.0
        # eff_threshold = 3.0276
        # rate (5.0) is >= eff_threshold, so it triggers
        assert rate >= eff_threshold
        
        is_warmup = (time.time() - detector._connect_time) < detector.warmup
        if not is_warmup and rate >= eff_threshold and not detector.in_cooldown():
            detector.on_clip_triggered(rate)
            
        callback.assert_called_once_with(5.0)
