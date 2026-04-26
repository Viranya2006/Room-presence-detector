from dataclasses import dataclass


@dataclass
class Config:
    CHIRP_FREQ: int = 18000
    CHIRP_DURATION: float = 0.05
    SAMPLE_RATE: int = 44100
    CHUNK_SIZE: int = 1024
    AUDIO_FORMAT_WIDTH: int = 2
    CHANNELS: int = 1

    RECORD_DURATION: float = 0.20
    CYCLE_INTERVAL: float = 2.0

    BAND_LOW: int = 17000
    BAND_HIGH: int = 19000

    CALIBRATION_DURATION: float = 10.0
    MINIMUM_BASELINE_ENERGY: float = 100.0

    PRESENCE_THRESHOLD: float = 2.0
    EMPTY_DEBOUNCE_COUNT: int = 3

    AUTO_LOCK_ENABLED: bool = True
    LOCK_DELAY_SECONDS: float = 0.0

    @property
    def calibration_cycles(self) -> int:
        return int(self.CALIBRATION_DURATION / self.CYCLE_INTERVAL)

    @property
    def record_frames(self) -> int:
        return int(self.SAMPLE_RATE * self.RECORD_DURATION)

    @property
    def chirp_samples(self) -> int:
        return int(self.SAMPLE_RATE * self.CHIRP_DURATION)

    @property
    def total_cycle_frames(self) -> int:
        return int(self.SAMPLE_RATE * (self.CHIRP_DURATION + self.RECORD_DURATION))
