from datetime import datetime

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QBrush, QPen, QColor, QAction
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QCheckBox, QSystemTrayIcon, QMenu, QApplication,
)

from .detector import State


class HudWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_pos: QPoint | None = None
        self._max_energy = 1.0
        self._setup_ui()
        self._position_default()

    def _setup_ui(self):
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(280)

        container = QWidget(self)
        container.setObjectName("hud")
        container.setStyleSheet("""
            QWidget#hud {
                background-color: rgba(30, 30, 30, 235);
                border: 1px solid rgba(255, 255, 255, 40);
                border-radius: 10px;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 10pt;
                background: transparent;
                border: none;
            }
            QLabel#title {
                font-size: 9pt;
                font-weight: bold;
                color: #888888;
                letter-spacing: 1px;
            }
            QLabel#status {
                font-size: 18pt;
                font-weight: bold;
            }
            QLabel#confidence {
                font-size: 11pt;
                color: #aaaaaa;
            }
            QProgressBar {
                border: 1px solid #444;
                border-radius: 3px;
                background-color: #222;
                height: 14px;
                text-align: center;
                font-size: 8pt;
                color: #888;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 2px;
            }
            QPushButton {
                background-color: #333;
                color: #ccc;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #444;
            }
            QPushButton:pressed {
                background-color: #555;
            }
            QCheckBox {
                color: #ccc;
                font-size: 9pt;
                background: transparent;
                border: none;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
            }
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        self.title_label = QLabel("ROOM PRESENCE DETECTOR")
        self.title_label.setObjectName("title")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        self.status_label = QLabel("CALIBRATING...")
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #FFC107;")
        layout.addWidget(self.status_label)

        self.confidence_label = QLabel("Confidence: --")
        self.confidence_label.setObjectName("confidence")
        self.confidence_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.confidence_label)

        energy_label = QLabel("Echo Energy")
        energy_label.setStyleSheet("font-size: 8pt; color: #666;")
        layout.addWidget(energy_label)

        self.energy_bar = QProgressBar()
        self.energy_bar.setRange(0, 100)
        self.energy_bar.setValue(0)
        self.energy_bar.setFormat("%v%")
        layout.addWidget(self.energy_bar)

        self.last_seen_label = QLabel("Last seen: --")
        self.last_seen_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.last_seen_label)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #F44336; font-size: 8pt;")
        self.error_label.setWordWrap(True)
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.calibrate_btn = QPushButton("Recalibrate")
        controls.addWidget(self.calibrate_btn)

        self.autolock_check = QCheckBox("Auto-Lock")
        self.autolock_check.setChecked(True)
        controls.addWidget(self.autolock_check)

        layout.addLayout(controls)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

    def _position_default(self):
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            x = geom.right() - self.width() - 20
            y = geom.bottom() - self.sizeHint().height() - 60
            self.move(x, y)

    def on_state_changed(self, state: State):
        colors = {
            State.CALIBRATING: ("#FFC107", "CALIBRATING..."),
            State.PRESENT: ("#4CAF50", "PRESENT"),
            State.EMPTY: ("#F44336", "EMPTY"),
            State.LOCKING: ("#FF9800", "LOCKING..."),
        }
        color, text = colors.get(state, ("#9E9E9E", "UNKNOWN"))
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color}; font-size: 18pt; font-weight: bold;")

    def on_reading_updated(self, energy: float, confidence: float,
                           is_present: bool, timestamp: float):
        self.confidence_label.setText(f"Confidence: {confidence:.0f}%")

        if energy > self._max_energy:
            self._max_energy = energy
        bar_value = int(min(energy / self._max_energy * 100, 100)) if self._max_energy > 0 else 0
        self.energy_bar.setValue(bar_value)

        chunk_color = "#4CAF50" if is_present else "#F44336"
        self.energy_bar.setStyleSheet(
            f"QProgressBar::chunk {{ background-color: {chunk_color}; border-radius: 2px; }}"
        )

        if is_present:
            ts = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
            self.last_seen_label.setText(f"Last seen: {ts}")

    def on_error(self, message: str):
        self.error_label.setText(message)
        self.error_label.show()
        self.status_label.setText("ERROR")
        self.status_label.setStyleSheet("color: #9E9E9E; font-size: 18pt; font-weight: bold;")

    def on_warning(self, message: str):
        self.error_label.setText(message)
        self.error_label.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


def _make_icon(color: QColor) -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(color))
    painter.setPen(QPen(color.darker(150), 1))
    painter.drawEllipse(2, 2, 28, 28)
    painter.end()
    return QIcon(pixmap)


ICONS = {
    State.CALIBRATING: lambda: _make_icon(QColor("#FFC107")),
    State.PRESENT: lambda: _make_icon(QColor("#4CAF50")),
    State.EMPTY: lambda: _make_icon(QColor("#F44336")),
    State.LOCKING: lambda: _make_icon(QColor("#FF9800")),
}


class TrayIcon(QSystemTrayIcon):
    recalibrate_clicked = None
    toggle_auto_lock = None
    show_hud_clicked = None
    quit_clicked = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._icons = {state: factory() for state, factory in ICONS.items()}
        self._error_icon = _make_icon(QColor("#9E9E9E"))
        self.setIcon(self._icons[State.CALIBRATING])
        self.setToolTip("Room Presence Detector — Calibrating")

        menu = QMenu()

        show_action = QAction("Show HUD", menu)
        show_action.triggered.connect(self._on_show_hud)
        menu.addAction(show_action)

        recal_action = QAction("Recalibrate", menu)
        recal_action.triggered.connect(self._on_recalibrate)
        menu.addAction(recal_action)

        self._autolock_action = QAction("Auto-Lock", menu)
        self._autolock_action.setCheckable(True)
        self._autolock_action.setChecked(True)
        self._autolock_action.toggled.connect(self._on_toggle_autolock)
        menu.addAction(self._autolock_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._on_quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def set_callbacks(self, show_hud, recalibrate, toggle_autolock, quit_app):
        self.show_hud_clicked = show_hud
        self.recalibrate_clicked = recalibrate
        self.toggle_auto_lock = toggle_autolock
        self.quit_clicked = quit_app

    def on_state_changed(self, state: State):
        icon = self._icons.get(state, self._error_icon)
        self.setIcon(icon)
        tooltips = {
            State.CALIBRATING: "Room Presence Detector — Calibrating",
            State.PRESENT: "Room Presence Detector — Present",
            State.EMPTY: "Room Presence Detector — Empty",
            State.LOCKING: "Room Presence Detector — Locking...",
        }
        self.setToolTip(tooltips.get(state, "Room Presence Detector"))

    def on_error(self, message: str):
        self.setIcon(self._error_icon)
        self.setToolTip(f"Room Presence Detector — Error: {message}")

    def set_autolock_checked(self, checked: bool):
        self._autolock_action.setChecked(checked)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.show_hud_clicked:
                self.show_hud_clicked()

    def _on_show_hud(self):
        if self.show_hud_clicked:
            self.show_hud_clicked()

    def _on_recalibrate(self):
        if self.recalibrate_clicked:
            self.recalibrate_clicked()

    def _on_toggle_autolock(self, checked):
        if self.toggle_auto_lock:
            self.toggle_auto_lock(checked)

    def _on_quit(self):
        if self.quit_clicked:
            self.quit_clicked()
