import logging
import time
from threading import Event

import numpy as np
import sounddevice as sd
from PyQt6.QtCore import QThread, pyqtSignal
from scipy.fft import rfft, rfftfreq
from scipy.signal.windows import tukey, hann

from .config import Config

logger = logging.getLogger(__name__)


class SonarEngine(QThread):
    cycle_result = pyqtSignal(float, object, float)
    calibration_sample = pyqtSignal(float)
    calibration_complete = pyqtSignal(float, float)
    error_occurred = pyqtSignal(str)

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self._config = config
        self._stop_event = Event()
        self._calibrating = False
        self._chirp = self._generate_chirp()
        self._output_buffer = self._build_output_buffer()

    def _generate_chirp(self) -> np.ndarray:
        cfg = self._config
        t = np.linspace(0, cfg.CHIRP_DURATION, cfg.chirp_samples, endpoint=False)
        envelope = tukey(cfg.chirp_samples, alpha=0.1)
        chirp = np.sin(2 * np.pi * cfg.CHIRP_FREQ * t) * envelope
        return chirp.astype(np.float32)

    def _build_output_buffer(self) -> np.ndarray:
        silence = np.zeros(self._config.record_frames, dtype=np.float32)
        return np.concatenate([self._chirp, silence])

    def _check_devices(self):
        try:
            sd.query_devices(kind='input')
        except sd.PortAudioError:
            raise RuntimeError("No microphone found")
        try:
            sd.query_devices(kind='output')
        except sd.PortAudioError:
            raise RuntimeError("No speaker found")

    def _do_cycle(self) -> tuple[float, np.ndarray]:
        cfg = self._config
        total_frames = cfg.total_cycle_frames

        recording = sd.playrec(
            self._output_buffer.reshape(-1, 1),
            samplerate=cfg.SAMPLE_RATE,
            channels=1,
            dtype='float32',
            blocking=True,
        )

        audio = recording.flatten().astype(np.float64)
        return self._analyze(audio)

    def _analyze(self, recording: np.ndarray) -> tuple[float, np.ndarray]:
        cfg = self._config
        window = hann(len(recording))
        windowed = recording * window
        spectrum = np.abs(rfft(windowed))
        freqs = rfftfreq(len(recording), d=1.0 / cfg.SAMPLE_RATE)

        mask = (freqs >= cfg.BAND_LOW) & (freqs <= cfg.BAND_HIGH)
        band_energy = float(np.sum(spectrum[mask] ** 2))

        return band_energy, spectrum

    def start_calibration(self):
        self._calibrating = True

    def request_stop(self):
        self._stop_event.set()

    def _run_calibration(self):
        cfg = self._config
        energies = []
        for i in range(cfg.calibration_cycles):
            if self._stop_event.is_set():
                return
            try:
                energy, _ = self._do_cycle()
                energies.append(energy)
                self.calibration_sample.emit(energy)
                logger.info("Calibration sample %d/%d: energy=%.2f",
                            i + 1, cfg.calibration_cycles, energy)
            except Exception as e:
                logger.error("Calibration cycle failed: %s", e)
                continue

            remaining = cfg.CYCLE_INTERVAL - (cfg.CHIRP_DURATION + cfg.RECORD_DURATION)
            if remaining > 0 and not self._stop_event.is_set():
                self._stop_event.wait(timeout=remaining)

        if energies:
            baseline = float(np.mean(energies))
            std_dev = float(np.std(energies))
            std_dev = max(std_dev, 0.05 * baseline)
            self.calibration_complete.emit(baseline, std_dev)
            logger.info("Calibration complete: baseline=%.2f, std=%.2f", baseline, std_dev)
        else:
            self.error_occurred.emit("Calibration failed: no valid samples collected")

        self._calibrating = False

    def run(self):
        consecutive_errors = 0
        try:
            self._check_devices()
            sd.default.samplerate = self._config.SAMPLE_RATE
            sd.default.channels = self._config.CHANNELS

            if self._calibrating:
                self._run_calibration()

            while not self._stop_event.is_set():
                cycle_start = time.perf_counter()
                try:
                    energy, spectrum = self._do_cycle()
                    consecutive_errors = 0
                    self.cycle_result.emit(energy, spectrum, time.time())
                except Exception as e:
                    consecutive_errors += 1
                    logger.error("Cycle error (%d): %s", consecutive_errors, e)
                    if consecutive_errors > 5:
                        self.error_occurred.emit(f"Persistent audio error: {e}")
                        break
                    continue

                elapsed = time.perf_counter() - cycle_start
                sleep_time = self._config.CYCLE_INTERVAL - elapsed
                if sleep_time > 0:
                    self._stop_event.wait(timeout=sleep_time)

        except Exception as e:
            self.error_occurred.emit(str(e))
