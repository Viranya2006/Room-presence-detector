import logging
from enum import Enum, auto

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .config import Config
from .locker import lock_workstation

logger = logging.getLogger(__name__)


class State(Enum):
    CALIBRATING = auto()
    PRESENT = auto()
    EMPTY = auto()
    LOCKING = auto()


class PresenceDetector(QObject):
    state_changed = pyqtSignal(object)
    reading_updated = pyqtSignal(float, float, bool, float)
    lock_triggered = pyqtSignal()
    warning_emitted = pyqtSignal(str)

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self._config = config
        self._state = State.CALIBRATING
        self._baseline = 0.0
        self._baseline_std = 0.0
        self._empty_count = 0
        self._confidence = 0.0
        self._last_detected = 0.0
        self._cal_samples: list[float] = []

        self._lock_timer = QTimer(self)
        self._lock_timer.setSingleShot(True)
        self._lock_timer.timeout.connect(self._on_lock_timer)

    @property
    def state(self) -> State:
        return self._state

    @property
    def auto_lock_enabled(self) -> bool:
        return self._config.AUTO_LOCK_ENABLED

    @property
    def last_detected(self) -> float:
        return self._last_detected

    def set_auto_lock(self, enabled: bool):
        self._config.AUTO_LOCK_ENABLED = enabled
        if not enabled:
            self._lock_timer.stop()
            if self._state == State.LOCKING:
                self._state = State.EMPTY
                self.state_changed.emit(self._state)

    def recalibrate(self):
        self._state = State.CALIBRATING
        self._cal_samples.clear()
        self._lock_timer.stop()
        self.state_changed.emit(self._state)

    def on_calibration_sample(self, energy: float):
        self._cal_samples.append(energy)

    def on_calibration_complete(self, baseline: float, std_dev: float):
        self._baseline = baseline
        self._baseline_std = std_dev
        self._empty_count = 0
        self._state = State.PRESENT
        self.state_changed.emit(self._state)

        if baseline < self._config.MINIMUM_BASELINE_ENERGY:
            self.warning_emitted.emit(
                "Very low signal at configured frequency. "
                "Your hardware may not support ultrasonic detection. "
                "Try lowering CHIRP_FREQ in config.py."
            )

        logger.info("Detector active: baseline=%.2f, std=%.2f", baseline, std_dev)

    def on_cycle_result(self, energy: float, spectrum: object, timestamp: float):
        if self._state == State.CALIBRATING:
            return

        if self._baseline_std == 0:
            return

        deviation = abs(energy - self._baseline) / self._baseline_std
        is_present = deviation > self._config.PRESENCE_THRESHOLD

        raw_confidence = (deviation / self._config.PRESENCE_THRESHOLD) * 50.0
        self._confidence = min(100.0, max(0.0, raw_confidence))

        if is_present:
            self._empty_count = 0
            self._last_detected = timestamp
            if self._state != State.PRESENT:
                self._lock_timer.stop()
                self._state = State.PRESENT
                self.state_changed.emit(self._state)
                logger.info("Presence detected (deviation=%.2f)", deviation)
        else:
            self._empty_count += 1
            if self._empty_count >= self._config.EMPTY_DEBOUNCE_COUNT:
                if self._state == State.PRESENT:
                    self._state = State.EMPTY
                    self.state_changed.emit(self._state)
                    logger.info("Room empty (debounce met, deviation=%.2f)", deviation)
                    if self._config.AUTO_LOCK_ENABLED:
                        delay_ms = int(self._config.LOCK_DELAY_SECONDS * 1000)
                        self._lock_timer.start(max(delay_ms, 0))

        self.reading_updated.emit(energy, self._confidence, is_present, timestamp)

    def _on_lock_timer(self):
        if self._state in (State.EMPTY, State.LOCKING):
            self._state = State.LOCKING
            self.state_changed.emit(self._state)
            logger.info("Locking workstation")
            self.lock_triggered.emit()
            lock_workstation()
            self._state = State.EMPTY
            self.state_changed.emit(self._state)
