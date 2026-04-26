import logging
import time
from threading import Event

import numpy as np
import pyaudio
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
        self._pa: pyaudio.PyAudio | None = None
        self._stream: pyaudio.Stream | None = None
        self._input_stream: pyaudio.Stream | None = None
        self._output_stream: pyaudio.Stream | None = None
        self._chirp = self._generate_chirp()

    def _generate_chirp(self) -> np.ndarray:
        cfg = self._config
        t = np.linspace(0, cfg.CHIRP_DURATION, cfg.chirp_samples, endpoint=False)
        envelope = tukey(cfg.chirp_samples, alpha=0.1)
        chirp = np.sin(2 * np.pi * cfg.CHIRP_FREQ * t) * envelope
        return (chirp * 32767).astype(np.int16)

    def _build_output_buffer(self) -> bytes:
        silence_samples = self._config.record_frames
        silence = np.zeros(silence_samples, dtype=np.int16)
        full = np.concatenate([self._chirp, silence])
        return full.tobytes()

    def _open_streams(self):
        cfg = self._config
        self._input_stream = None
        self._output_stream = None

        # Try full-duplex first
        try:
            self._stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=cfg.CHANNELS,
                rate=cfg.SAMPLE_RATE,
                input=True,
                output=True,
                frames_per_buffer=cfg.CHUNK_SIZE,
            )
            logger.info("Opened full-duplex audio stream")
            return
        except Exception:
            logger.warning("Full-duplex failed, using separate streams")
            self._stream = None

        # Fallback: separate input and output streams
        self._input_stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=cfg.CHANNELS,
            rate=cfg.SAMPLE_RATE,
            input=True,
            frames_per_buffer=cfg.CHUNK_SIZE,
        )
        self._output_stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=cfg.CHANNELS,
            rate=cfg.SAMPLE_RATE,
            output=True,
            frames_per_buffer=cfg.CHUNK_SIZE,
        )
        logger.info("Opened separate input/output streams")

    def _flush_input(self):
        """Discard any stale frames in the input buffer."""
        stream = self._stream or self._input_stream
        if stream is None:
            return
        try:
            avail = stream.get_read_available()
            if avail > 0:
                stream.read(avail, exception_on_overflow=False)
        except Exception:
            pass

    def _do_cycle(self) -> tuple[float, np.ndarray]:
        cfg = self._config
        output_buf = self._build_output_buffer()
        total_frames = cfg.total_cycle_frames

        self._flush_input()

        if self._stream is not None:
            # Full-duplex: write blocks while input buffer fills simultaneously
            self._stream.write(output_buf)
            raw = self._stream.read(total_frames, exception_on_overflow=False)
        elif self._input_stream and self._output_stream:
            # Separate streams: input is already recording, write chirp, then read
            self._output_stream.write(output_buf)
            raw = self._input_stream.read(total_frames, exception_on_overflow=False)
        else:
            raise RuntimeError("No audio stream available")

        recording = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
        return self._analyze(recording)

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
                time.sleep(remaining)

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
            self._pa = pyaudio.PyAudio()
            try:
                self._pa.get_default_input_device_info()
            except IOError:
                self.error_occurred.emit("No microphone found")
                return
            try:
                self._pa.get_default_output_device_info()
            except IOError:
                self.error_occurred.emit("No speaker found")
                return

            self._open_streams()

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
        finally:
            self._cleanup()

    def _cleanup(self):
        for stream in (self._stream, self._input_stream, self._output_stream):
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
        self._stream = None
        self._input_stream = None
        self._output_stream = None
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None
