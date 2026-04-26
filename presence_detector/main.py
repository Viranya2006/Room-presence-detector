import logging
import sys

from PyQt6.QtWidgets import QApplication

from .config import Config
from .sonar import SonarEngine
from .detector import PresenceDetector
from .hud import HudWindow, TrayIcon

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    config = Config()

    sonar = SonarEngine(config)
    detector = PresenceDetector(config)
    hud = HudWindow()
    tray = TrayIcon()

    # Sonar -> Detector
    sonar.cycle_result.connect(detector.on_cycle_result)
    sonar.calibration_sample.connect(detector.on_calibration_sample)
    sonar.calibration_complete.connect(detector.on_calibration_complete)

    # Sonar -> HUD (errors)
    sonar.error_occurred.connect(hud.on_error)
    sonar.error_occurred.connect(tray.on_error)

    # Detector -> HUD
    detector.state_changed.connect(hud.on_state_changed)
    detector.state_changed.connect(tray.on_state_changed)
    detector.reading_updated.connect(hud.on_reading_updated)
    detector.warning_emitted.connect(hud.on_warning)

    # HUD controls -> Detector
    hud.calibrate_btn.clicked.connect(_make_recalibrate(detector, sonar))
    hud.autolock_check.toggled.connect(detector.set_auto_lock)

    # Tray callbacks
    def toggle_hud():
        if hud.isVisible():
            hud.hide()
        else:
            hud.show()
            hud.raise_()

    def recalibrate():
        _make_recalibrate(detector, sonar)()

    def toggle_autolock(checked):
        detector.set_auto_lock(checked)
        hud.autolock_check.setChecked(checked)

    def quit_app():
        sonar.request_stop()
        sonar.wait(3000)
        app.quit()

    tray.set_callbacks(toggle_hud, recalibrate, toggle_autolock, quit_app)

    # Sync autolock checkbox state both ways
    hud.autolock_check.toggled.connect(tray.set_autolock_checked)

    def cleanup():
        logger.info("Shutting down...")
        sonar.request_stop()
        sonar.wait(3000)

    app.aboutToQuit.connect(cleanup)

    # Start
    sonar.start_calibration()
    sonar.start()
    tray.show()
    hud.show()

    logger.info("Room Presence Detector started. Calibrating for %.0fs...",
                config.CALIBRATION_DURATION)

    sys.exit(app.exec())


def _make_recalibrate(detector, sonar):
    def do_recalibrate():
        detector.recalibrate()
        sonar.request_stop()
        sonar.wait(3000)
        sonar.start_calibration()
        sonar._stop_event.clear()
        sonar.start()
    return do_recalibrate


if __name__ == "__main__":
    main()
