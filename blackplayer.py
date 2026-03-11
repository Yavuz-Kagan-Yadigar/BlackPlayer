#!/usr/bin/env python3
"""
BlackPlayer  —  Dark music player
Wayland · GNOME/KDE Integration · PipeWire · GStreamer spectrum viz
MPRIS2 D-Bus  ·  Bit-perfect audio  ·  OLED blackout overlay
"""

import sys, os, json, threading, enum, random, math
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List
from collections import deque

from PyQt6.QtWidgets import *
from PyQt6.QtCore    import *
from PyQt6.QtGui     import *

import gi
gi.require_version('Gst', '1.0')
gi.require_version('Gio', '2.0')
from gi.repository import Gst, GLib, Gio
Gst.init(None)

from mutagen import File as MutagenFile

# ══════════════════════════════════════════════════════════════════════════════
#  Palette
# ══════════════════════════════════════════════════════════════════════════════
BG   = '#000000'
BG2  = '#0a0a0a'
BG3  = '#141414'
BG4  = '#1e1e1e'
BORD = '#222222'
B2   = '#333333'
ACC  = '#e03030'
ACCH = '#ff4444'
FG   = '#f0f0f0'
FG2  = '#909090'
SEL  = '#181818'

def make_acch(acc_hex: str) -> str:
    c = QColor(acc_hex)
    h, s, v, _ = c.getHsvF()
    c2 = QColor(); c2.setHsvF(h, max(0.0, s-0.15), min(1.0, v+0.25))
    return c2.name()

SUPPORTED_EXT = frozenset({'.flac', '.mp3', '.opus', '.m4a', '.aac', '.ogg'})
CONFIG_PATH   = Path.home() / '.config' / 'blackplayer' / 'config.json'
VIZ_BANDS     = 256
MIN_DB        = -70.0
RAD           = 10   # global corner radius

# EQ constants
MAX_EQ_BANDS  = 10
EQ_FREQ_MIN   = 20.0
EQ_FREQ_MAX   = 22000.0
EQ_GAIN_MIN   = -10.0
EQ_GAIN_MAX   = 10.0
EQ_Q_MIN      = 0.1
EQ_Q_MAX      = 10.0
EQ_GAIN_MAX_GRAPH = 10.0   # graph vertical range ±10 dB
# ══════════════════════════════════════════════════════════════════════════════
#  Stylesheet (unchanged)
# ══════════════════════════════════════════════════════════════════════════════
def make_stylesheet(acc: str = None, acch: str = None) -> str:
    if acc  is None: acc  = ACC
    if acch is None: acch = ACCH
    return f"""
* {{ outline: none; }}
QWidget     {{ background:{BG};  color:{FG};  font-size:13px; }}
QMainWindow {{ background:{BG}; }}
QDialog     {{ background:{BG}; border-radius:{RAD}px; }}
QWidget#sidebar {{ background:{BG2}; border-right:1px solid {BORD}; }}

QPushButton {{
    background:{BG3}; color:{FG}; border:1px solid {B2};
    border-radius:{RAD}px; padding:8px 14px; min-height:36px; text-align:center;
}}
QPushButton:hover   {{ border-color:{acc}; }}
QPushButton:pressed {{ background:{BG4}; }}
QPushButton:checked {{ color:{acc}; border-color:{acc}; background:{BG3}; }}
QPushButton:disabled {{ color:{B2}; border-color:{BORD}; }}

QPushButton#play {{
    background:{BG3}; color:{acc}; border:2px solid {acc}; border-radius:26px;
    min-width:52px; max-width:52px; min-height:52px; max-height:52px;
    font-size:22px; padding:0; text-align:center;
}}
QPushButton#play:hover   {{ border-color:{acch}; color:{acch}; background:{BG4}; }}
QPushButton#play:pressed {{ background:{BG4}; }}

QPushButton#ctrl {{
    background:transparent; border:none; color:{FG2}; font-size:20px;
    min-width:44px; max-width:44px; min-height:44px; max-height:44px;
    border-radius:22px; padding:0; text-align:center;
}}
QPushButton#ctrl:hover   {{ color:{FG};  background:{BG3}; }}
QPushButton#ctrl:checked {{ color:{acc}; background:transparent; }}
QPushButton#ctrl:pressed {{ background:{BG4}; }}

QPushButton#icon_btn {{
    background:transparent; border:none; color:{FG2}; font-size:18px;
    min-width:36px; max-width:36px; min-height:36px; max-height:36px;
    border-radius:18px; padding:0; text-align:center;
}}
QPushButton#icon_btn:hover   {{ color:{FG}; background:{BG3}; }}
QPushButton#icon_btn:pressed {{ background:{BG4}; }}

QSlider {{
    background: transparent;
}}
QSlider::groove:horizontal {{ background:{B2}; height:4px; border-radius:2px; }}
QSlider::sub-page:horizontal {{ background:{acc}; border-radius:2px; }}
QSlider::handle:horizontal {{
    background:{BG4}; border:2px solid {acc};
    width:14px; height:14px; border-radius:7px; margin:-5px 0;
}}
QSlider::handle:horizontal:hover {{
    background:{BG4}; border-color:{acch};
    width:18px; height:18px; border-radius:9px; margin:-7px 0;
}}

QTableWidget {{
    background:{BG}; color:{FG}; border:none; gridline-color:transparent;
    selection-background-color:{SEL}; selection-color:{FG};
    border-radius:{RAD}px;
}}
QTableWidget::item {{ padding:6px 8px; border-bottom:1px solid {BORD}; }}
QTableWidget::item:selected {{ background:{SEL}; color:{FG}; }}
QHeaderView {{ background:{BG2}; border:none; }}
QHeaderView::section {{
    background:{BG2}; color:{FG2}; border:none;
    border-right:1px solid {BORD}; border-bottom:1px solid {BORD};
    padding:7px 8px; font-size:11px;
}}
QHeaderView::section:last {{ border-right:none; }}

QTabWidget::pane {{ border:none; border-top:1px solid {BORD}; }}
QTabBar {{ background:{BG2}; }}
QTabBar::tab {{
    background:{BG2}; color:{FG2};
    border:1px solid {BORD}; border-bottom:none;
    border-top-left-radius:6px; border-top-right-radius:6px;
    padding:5px 10px; min-width:50px; margin-right:2px; margin-top:3px;
    font-size:12px;
}}
QTabBar::tab:selected {{
    background:{BG}; color:{acc};
    border-color:{BORD}; border-top:2px solid {acc};
    border-bottom:1px solid {BG}; margin-bottom:-1px; margin-top:2px;
}}
QTabBar::tab:hover:!selected {{ color:{FG}; background:{BG3}; }}

QLineEdit {{
    background:{BG3}; color:{FG}; border:1px solid {B2};
    border-radius:18px; padding:8px 16px; min-height:36px; max-height:36px;
}}
QLineEdit:focus {{ border-color:{acc}; }}

QListWidget {{ background:{BG2}; border:none; color:{FG}; border-radius:{RAD}px; }}
QListWidget::item {{ padding:12px 14px; border-bottom:1px solid {BORD}; font-size:12px; }}
QListWidget::item:selected {{ background:{SEL}; color:{acc}; border-radius:6px; }}
QListWidget::item:hover:!selected {{ background:{BG3}; border-radius:6px; }}

QScrollBar {{ background:{BG}; border:none; }}
QScrollBar:vertical   {{ width:5px; margin:0; }}
QScrollBar:horizontal {{ height:5px; margin:0; }}
QScrollBar::handle {{ background:{B2}; border-radius:2px; min-height:20px; }}
QScrollBar::handle:hover {{ background:{acc}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height:0; width:0; }}
QScrollBar::add-page,  QScrollBar::sub-page {{ background:none; }}

QSplitter::handle {{ background:{BORD}; }}
QSplitter::handle:horizontal {{ width:1px; }}

QMenu {{ background:{BG3}; border:1px solid {B2}; border-radius:{RAD}px; padding:4px 0; }}
QMenu::item {{ padding:9px 22px; color:{FG}; }}
QMenu::item:selected {{ background:{SEL}; color:{acc}; }}
QMenu::separator {{ height:1px; background:{BORD}; margin:4px 0; }}

QLabel#now_title  {{ font-size:14px; font-weight:bold; color:{FG}; }}
QLabel#now_artist {{ font-size:12px; color:{FG2}; }}
QLabel#time_lbl   {{ font-size:11px; color:{FG2}; font-family:monospace;
                     min-width:38px; background:transparent; }}
QLabel#sect_lbl   {{ font-size:10px; color:{FG2}; letter-spacing:2px;
                     padding:12px 14px 5px 14px; }}
QLabel#popup_title{{ font-size:12px; font-weight:bold; color:{FG2};
                     letter-spacing:1px; background:transparent; }}
QLabel#setting_lbl{{ font-size:11px; color:{FG2}; background:transparent; }}

QStatusBar {{ background:{BG2}; color:{FG2}; font-size:11px; border-top:1px solid {BORD}; }}
QToolTip   {{ background:{BG3}; border:1px solid {B2}; color:{FG}; padding:5px 9px;
              border-radius:6px; }}
QFrame#ctrlbar {{ border-top:1px solid {BORD}; }}

/* Settings & EQ popups – background drawn by paintEvent */
QFrame#settings_popup,
QFrame#eq_popup {{
    background: transparent;
    border: none;
}}
"""

SS = make_stylesheet()  # initial

# ══════════════════════════════════════════════════════════════════════════════
#  Toggle switch (unchanged)
# ══════════════════════════════════════════════════════════════════════════════
class ToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)
    W, H, R = 42, 22, 11

    def __init__(self, label: str = '', parent=None):
        super().__init__(parent)
        self._on = False; self._label = label; self._anim = 0.0
        self._timer = QTimer(self); self._timer.setInterval(16)
        self._timer.timeout.connect(self._step)
        lw = self.fontMetrics().horizontalAdvance(label)+4 if label else 0
        self.setFixedSize(self.W + lw + (6 if label else 0), max(self.H, 18))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def isChecked(self) -> bool: return self._on

    def setChecked(self, on: bool):
        self._on = on; self._anim = 1.0 if on else 0.0; self.update()

    def setCheckedSignal(self, on: bool):
        self.setChecked(on); self.toggled.emit(on)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._on = not self._on; self._timer.start(); self.toggled.emit(self._on)

    def _step(self):
        target = 1.0 if self._on else 0.0; delta = 0.15
        if abs(self._anim - target) < delta: self._anim = target; self._timer.stop()
        else: self._anim += delta if self._on else -delta
        self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._anim
        # Darker, desaturated accent for the track when ON
        _acc = QColor(ACC)
        h, s, v, _ = _acc.getHsvF()
        _track_on = QColor(); _track_on.setHsvF(h, s*0.55, v*0.38)
        _border_on = QColor(); _border_on.setHsvF(h, s*0.65, v*0.55)
        _off = QColor(0x20, 0x20, 0x20)
        _boff = QColor(0x3e, 0x3e, 0x3e)
        tc = QColor(
            int(_off.red()   + t*(_track_on.red()   - _off.red())),
            int(_off.green() + t*(_track_on.green() - _off.green())),
            int(_off.blue()  + t*(_track_on.blue()  - _off.blue())))
        bc = QColor(
            int(_boff.red()   + t*(_border_on.red()   - _boff.red())),
            int(_boff.green() + t*(_border_on.green() - _boff.green())),
            int(_boff.blue()  + t*(_border_on.blue()  - _boff.blue())))
        p.setPen(QPen(bc, 1.5)); p.setBrush(QBrush(tc))
        p.drawRoundedRect(QRectF(0,(self.height()-self.H)/2,self.W,self.H), self.R, self.R)
        kx = 3 + t*(self.W-2*self.R-2); ky = (self.height()-self.H)/2+(self.H-self.R*2)/2
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(QColor(ACCH if self._on else FG2)))
        p.drawEllipse(QRectF(kx, ky, self.R*2, self.R*2))
        if self._label:
            p.setPen(QColor(FG2)); p.setFont(self.font())
            p.drawText(self.W+6, 0, self.width()-self.W-6, self.height(),
                       Qt.AlignmentFlag.AlignVCenter, self._label)
        p.end()


# ══════════════════════════════════════════════════════════════════════════════
#  Inline slider row (unchanged)
# ══════════════════════════════════════════════════════════════════════════════
class JumpSlider(QSlider):
    """Slider that jumps immediately to click/touch position."""
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)
        self._touch_active = False

    def _jump(self, x: float):
        v = QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(), int(max(0, x)), self.width())
        self.setValue(v)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton: self._jump(e.position().x())
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton: self._jump(e.position().x())
        super().mouseMoveEvent(e)

    def event(self, e: QEvent) -> bool:
        t = e.type()
        if t == QEvent.Type.TouchBegin:
            pts = e.points()
            if pts:
                self._touch_active = True
                self._jump(pts[0].position().x())
            e.accept(); return True
        if t == QEvent.Type.TouchUpdate:
            pts = e.points()
            if pts and self._touch_active:
                self._jump(pts[0].position().x())
            e.accept(); return True
        if t == QEvent.Type.TouchEnd:
            self._touch_active = False
            e.accept(); return True
        return super().event(e)


class SliderRow(QWidget):
    valueChanged = pyqtSignal(int)

    def __init__(self, label: str, lo: int, hi: int, val: int,
                 fmt=lambda v: str(v), parent=None):
        super().__init__(parent)
        self._fmt = fmt
        lay = QHBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(6)
        lbl = QLabel(label); lbl.setObjectName('setting_lbl')
        lbl.setFixedWidth(70)
        lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._sl = JumpSlider(Qt.Orientation.Horizontal)
        self._sl.setRange(lo, hi); self._sl.setValue(val)
        self._sl.setFixedHeight(22)
        self._sl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._val_lbl = QLabel(fmt(val)); self._val_lbl.setObjectName('setting_lbl')
        self._val_lbl.setFixedWidth(46)
        self._val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._val_lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._sl.valueChanged.connect(self._on_change)
        lay.addWidget(lbl); lay.addWidget(self._sl, 1); lay.addWidget(self._val_lbl)

    def _on_change(self, v):
        self._val_lbl.setText(self._fmt(v)); self.valueChanged.emit(v)

    def value(self) -> int: return self._sl.value()
    def setValue(self, v: int): self._sl.setValue(v)


# ══════════════════════════════════════════════════════════════════════════════
#  Settings popup (sliders now have transparent background)
# ══════════════════════════════════════════════════════════════════════════════
class SettingsPopup(QFrame):
    viz_toggled    = pyqtSignal(bool)
    log_toggled    = pyqtSignal(bool)
    volume_changed = pyqtSignal(int)
    delay_changed  = pyqtSignal(int)
    inertia_changed    = pyqtSignal(int)
    brightness_changed = pyqtSignal(int)   # 0..100
    cover_toggled      = pyqtSignal(bool)
    accent_changed     = pyqtSignal(str)
    lyrics_fetch_toggled = pyqtSignal(bool)
    cover_fetch_toggled = pyqtSignal()   # emitted when user clicks "Fetch Covers" button
    tag_fetch_toggled    = pyqtSignal()   # emitted when user clicks "Fetch Tags" button

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('settings_popup')
        # Child widget (no top-level flags) — works on Wayland with move()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(True)
        self.hide()  # start hidden
        self._hidden_by_outside = False
        # Close when user clicks outside the popup
        QApplication.instance().installEventFilter(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 16); root.setSpacing(10)

        hdr = QLabel('SETTINGS'); hdr.setObjectName('popup_title')
        root.addWidget(hdr)

        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet(f'background:{BORD}; margin:0;')
        root.addWidget(div)

        # Volume
        vol_row = QHBoxLayout(); vol_row.setSpacing(6)
        vol_lbl = QLabel('Volume'); vol_lbl.setObjectName('setting_lbl')
        vol_lbl.setFixedWidth(70)
        vol_lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._vol = JumpSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 100); self._vol.setValue(80); self._vol.setFixedHeight(22)
        self._vol.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._vol_lbl = QLabel('80%'); self._vol_lbl.setObjectName('setting_lbl')
        self._vol_lbl.setFixedWidth(36)
        self._vol_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._vol_lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._vol.valueChanged.connect(lambda v: (
            self._vol_lbl.setText(f'{v}%'), self.volume_changed.emit(v)))
        vol_row.addWidget(vol_lbl); vol_row.addWidget(self._vol, 1); vol_row.addWidget(self._vol_lbl)
        root.addLayout(vol_row)

        # Row 1: VIZ + LOG/LIN
        sw_row = QHBoxLayout(); sw_row.setSpacing(16)
        sw_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._viz_sw = ToggleSwitch('VIZ',     self)
        self._log_sw = ToggleSwitch('LOG/LIN', self)
        self._viz_sw.setChecked(True); self._log_sw.setChecked(True)
        self._viz_sw.toggled.connect(self.viz_toggled)
        self._log_sw.toggled.connect(self.log_toggled)
        sw_row.addWidget(self._viz_sw); sw_row.addWidget(self._log_sw)
        root.addLayout(sw_row)

        # Row 2: LYRICS FETCH + COVER
        sw2 = QHBoxLayout(); sw2.setSpacing(16)
        sw2.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._lyrics_fetch_sw = ToggleSwitch('LYRICS FETCH', self)
        self._lyrics_fetch_sw.setChecked(True)
        self._lyrics_fetch_sw.toggled.connect(self.lyrics_fetch_toggled)
        self._cover_sw = ToggleSwitch('COVER', self)
        self._cover_sw.setChecked(True)
        self._cover_sw.toggled.connect(self.cover_toggled)
        sw2.addWidget(self._lyrics_fetch_sw); sw2.addWidget(self._cover_sw)
        root.addLayout(sw2)

        # Action buttons row: Fetch Covers + Fetch Tags 
        action_row = QHBoxLayout(); action_row.setSpacing(8)
        self._btn_fetch_covers = QPushButton('Fetch Covers…')
        self._btn_fetch_covers.setFixedHeight(22)
        self._btn_fetch_covers.clicked.connect(self.cover_fetch_toggled)
        self._btn_fetch_tags = QPushButton('Fetch Tags…')
        self._btn_fetch_tags.setFixedHeight(22)
        self._btn_fetch_tags.clicked.connect(self.tag_fetch_toggled)
        action_row.addWidget(self._btn_fetch_covers)
        action_row.addWidget(self._btn_fetch_tags)
        root.addLayout(action_row)
        root.addSpacing(16)

        # Delay
        self._delay_row = SliderRow('Delay', 0, 1000, 0, lambda v: f'{v}ms')
        self._delay_row.valueChanged.connect(self.delay_changed)
        root.addWidget(self._delay_row)

        # Inertia
        self._inertia_row = SliderRow('Inertia', 0, 95, 50, lambda v: f'{v}%')
        self._inertia_row.valueChanged.connect(self.inertia_changed)
        root.addWidget(self._inertia_row)

        # Brightness
        self._bright_row = SliderRow('Brightness', 0, 100, 40, lambda v: f'{v}%')
        self._bright_row.valueChanged.connect(self.brightness_changed)
        root.addWidget(self._bright_row)

        # Accent color picker
        acc_row = QHBoxLayout(); acc_row.setSpacing(10)
        acc_lbl = QLabel('Color'); acc_lbl.setObjectName('setting_lbl')
        acc_lbl.setFixedWidth(55)
        acc_lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._accent_color = ACC
        self._accent_btn = QPushButton()
        self._accent_btn.setFixedSize(70, 24); self._accent_btn.setMinimumHeight(24); self._accent_btn.setMaximumHeight(24)
        self._accent_btn.setStyleSheet(
            f'background:{ACC}; border-radius:12px; border:1px solid #555; min-height:24px; max-height:24px;')
        self._accent_btn.clicked.connect(self._pick_accent)
        self._accent_hex = QLabel(ACC); self._accent_hex.setObjectName('setting_lbl')
        acc_row.addWidget(acc_lbl); acc_row.addWidget(self._accent_btn)
        acc_row.addWidget(self._accent_hex, 1)
        root.addLayout(acc_row)

        self.setFixedWidth(310)
        self.setMaximumHeight(600)
        self.adjustSize()

    def _pick_accent(self):
        # Must hide the Popup window before showing QColorDialog;
        # otherwise the Popup flag causes Qt to close the dialog immediately.
        saved_color = self._accent_color
        self.hide()
        dlg = QColorDialog(QColor(saved_color))
        dlg.setWindowTitle('Select Accent Color')
        dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dlg.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, False)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            c = dlg.currentColor()
            if c.isValid():
                self._accent_color = c.name()
                self._accent_btn.setStyleSheet(
                    f'background:{self._accent_color}; border-radius:12px; border:1px solid #555; min-height:24px; max-height:24px;')
                self._accent_hex.setText(self._accent_color)
                self.accent_changed.emit(self._accent_color)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QBrush(QColor('#000000')))
        p.setPen(QPen(QColor(B2), 1.0))
        p.drawRoundedRect(r, 12, 12)
        p.end()

    def volume(self)     -> int: return self._vol.value()
    def delay(self)      -> int: return self._delay_row.value()
    def inertia(self)    -> int: return self._inertia_row.value()
    def viz_on(self)     -> bool: return self._viz_sw.isChecked()
    def log_on(self)     -> bool: return self._log_sw.isChecked()

    def set_volume(self, v): self._vol.setValue(v)
    def set_delay(self, v):  self._delay_row.setValue(v)
    def set_inertia(self, v):self._inertia_row.setValue(v)
    def brightness(self) -> int: return self._bright_row.value()
    def set_brightness(self, v): self._bright_row.setValue(v)
    def cover_on(self) -> bool: return self._cover_sw.isChecked()
    def set_cover(self, v):     self._cover_sw.setChecked(v)
    def accent_color(self) -> str: return self._accent_color
    def set_accent_color(self, v: str):
        self._accent_color = v
        self._accent_btn.setStyleSheet(
            f'background:{v}; border-radius:12px; border:1px solid #555; min-height:24px; max-height:24px;')
        self._accent_hex.setText(v)
    def set_viz(self, v):    self._viz_sw.setChecked(v)
    def set_log(self, v):    self._log_sw.setChecked(v)
    def lyrics_fetch_on(self) -> bool: return self._lyrics_fetch_sw.isChecked()
    def set_lyrics_fetch(self, v): self._lyrics_fetch_sw.setChecked(v)
    def cover_fetch_on(self) -> bool: return True   # always enabled; user triggers manually
    def set_cover_fetch(self, v): pass              # no-op — kept for config compat

    def eventFilter(self, obj, e: QEvent) -> bool:
        """Close settings popup on mouse press outside it."""
        if (self.isVisible() and
                e.type() == QEvent.Type.MouseButtonPress and
                QApplication.activePopupWidget() is None and
                obj is not self and
                not (isinstance(obj, QWidget) and self.isAncestorOf(obj))):
            # For child widget: map click to our coords
            try:
                gpt = e.globalPosition().toPoint()
                local = self.mapFromGlobal(gpt)
                if not self.rect().contains(local):
                    self.hide()
                    self._hidden_by_outside = True
            except Exception:
                self.hide()
                self._hidden_by_outside = True
        return False  # never swallow events

    def show_above(self, btn: QWidget):
        # Position as a child widget inside the main window — works on Wayland
        win = btn.window()
        if self.parent() is not win:
            self.setParent(win)
            self.setWindowFlags(Qt.WindowType.Widget)  # ensure child
        self.adjustSize()
        btn_in_win = btn.mapTo(win, QPoint(0, 0))
        x = btn_in_win.x() + btn.width()//2 - self.width()//2
        # Prefer above the button; if not enough room, show below
        y_above = btn_in_win.y() - self.height() - 6
        y_below = btn_in_win.y() + btn.height() + 6
        y = y_above if y_above >= 4 else y_below
        # clamp inside window
        x = max(4, min(x, win.width()  - self.width()  - 4))
        y = max(4, min(y, win.height() - self.height() - 4))
        self.move(x, y)
        self.show()
        self.raise_()


# ══════════════════════════════════════════════════════════════════════════════
#  Tag edit dialog
# ══════════════════════════════════════════════════════════════════════════════
class TagEditDialog(QDialog):
    """Tag editor with cover art management."""
    def __init__(self, track: 'Track', locked_paths: set = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Edit Tags')
        self.setModal(True)
        self.setMinimumWidth(420)
        self._track    = track
        self._locked   = track.filepath in (locked_paths or set())
        self._cover_action = 'keep'   # 'keep' | 'remove' | 'set'
        self._new_cover_bytes: Optional[bytes] = None
        self._locked_changed = False

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── Cover row ──────────────────────────────────────────────────────
        cover_row = QHBoxLayout(); cover_row.setSpacing(12)
        self._cover_lbl = QLabel()
        self._cover_lbl.setFixedSize(96, 96)
        self._cover_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover_lbl.setStyleSheet(
            f'background:{BG3}; border:1px solid {B2}; border-radius:6px;')
        # Load current cover
        raw = extract_cover_bytes(track.filepath)
        if raw:
            pm = QPixmap(); pm.loadFromData(raw)
            self._cover_lbl.setPixmap(
                pm.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                          Qt.TransformationMode.SmoothTransformation).copy(0,0,96,96))
        else:
            self._cover_lbl.setText('No Cover')
            self._cover_lbl.setStyleSheet(
                f'background:{BG3}; border:1px solid {B2}; border-radius:6px;'
                f' color:{FG2}; font-size:11px;')
        cover_row.addWidget(self._cover_lbl)

        cover_btns = QVBoxLayout(); cover_btns.setSpacing(4)
        self._btn_cover_file   = QPushButton('Set from File…')
        self._btn_cover_search = QPushButton('Search Cover…')
        self._btn_cover_remove = QPushButton('Remove Cover')
        self._btn_cover_lock   = QPushButton('Locked' if self._locked else 'Unlocked')
        self._btn_cover_lock.setCheckable(True)
        self._btn_cover_lock.setChecked(self._locked)
        self._btn_cover_lock.setToolTip('Locked: auto-fetch will not replace this cover')
        for b in (self._btn_cover_file, self._btn_cover_search,
                  self._btn_cover_remove, self._btn_cover_lock):
            b.setFixedHeight(24); cover_btns.addWidget(b)
        # Tag fetch button below divider
        div2 = QFrame(); div2.setFrameShape(QFrame.Shape.HLine)
        div2.setStyleSheet(f'color:{BORD}; margin:2px 0;')
        cover_btns.addWidget(div2)
        self._btn_tag_fetch = QPushButton('Auto-fill Tags…')
        self._btn_tag_fetch.setFixedHeight(24)
        cover_btns.addWidget(self._btn_tag_fetch)
        cover_btns.addStretch()
        cover_row.addLayout(cover_btns)
        layout.addLayout(cover_row)

        self._btn_cover_file.clicked.connect(self._pick_cover_file)
        self._btn_cover_search.clicked.connect(self._search_cover_online)
        self._btn_cover_remove.clicked.connect(self._remove_cover)
        self._btn_cover_lock.toggled.connect(self._on_lock_toggled)
        self._btn_tag_fetch.clicked.connect(self._fetch_tags_online)

        # Divider
        div = QFrame(); div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f'color:{BORD};'); layout.addWidget(div)

        # ── Text tags ──────────────────────────────────────────────────────
        for label, attr in [('Title', 'title'), ('Artist', 'artist'), ('Album', 'album')]:
            row = QHBoxLayout()
            lbl = QLabel(f'{label}:'); lbl.setFixedWidth(50)
            row.addWidget(lbl)
            edit = QLineEdit(getattr(track, attr))
            setattr(self, f'_{attr}_edit', edit)
            row.addWidget(edit)
            layout.addLayout(row)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _pick_cover_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select Cover Image', '',
            'Images (*.jpg *.jpeg *.png *.webp *.bmp)')
        if not path: return
        with open(path, 'rb') as f:
            data = f.read()
        pm = QPixmap()
        if pm.loadFromData(data):
            self._new_cover_bytes = data
            self._cover_action = 'set'
            self._cover_lbl.setPixmap(
                pm.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                          Qt.TransformationMode.SmoothTransformation).copy(0,0,96,96))
            self._cover_lbl.setText('')

    def _search_cover_online(self):
        """Fetch cover from online sources for this specific track in a background thread."""
        self._btn_cover_search.setEnabled(False)
        self._btn_cover_search.setText('Searching…')
        artist = self._artist_edit.text().strip() or self._track.artist
        title  = self._title_edit.text().strip()  or self._track.title
        album  = self._album_edit.text().strip()  or self._track.album

        # Run network fetch in a daemon thread; update UI via QTimer
        import concurrent.futures as _cf
        result = [None]

        def _fetch():
            result[0] = fetch_cover_online(artist, title, album)

        future = _cf.Future()
        t = threading.Thread(target=_fetch, daemon=True)
        t.start()

        def _poll():
            if t.is_alive():
                QTimer.singleShot(200, _poll)
                return
            data = result[0]
            self._btn_cover_search.setEnabled(True)
            self._btn_cover_search.setText('Search Cover…')
            if data:
                pm = QPixmap()
                if pm.loadFromData(data):
                    self._new_cover_bytes = data
                    self._cover_action    = 'set'
                    self._cover_lbl.setPixmap(
                        pm.scaled(96, 96,
                                  Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                  Qt.TransformationMode.SmoothTransformation).copy(0, 0, 96, 96))
                    self._cover_lbl.setText('')
                    self._cover_lbl.setStyleSheet(
                        f'background:{BG3};border:1px solid {B2};border-radius:6px;')
                else:
                    self._cover_lbl.setText('Load error')
            else:
                self._btn_cover_search.setText('Not found')
                QTimer.singleShot(2000,
                    lambda: self._btn_cover_search.setText('Search Cover…'))

        QTimer.singleShot(200, _poll)

    def _fetch_tags_online(self):
        """Look up missing title/artist/album for this track and fill the edit fields."""
        self._btn_tag_fetch.setEnabled(False)
        self._btn_tag_fetch.setText('Searching…')
        artist = self._artist_edit.text().strip() or self._track.artist
        title  = self._title_edit.text().strip()  or self._track.title or Path(self._track.filepath).stem

        result = [{}]
        def _fetch():
            result[0] = lookup_tags_online(artist, title)

        t = threading.Thread(target=_fetch, daemon=True)
        t.start()

        def _poll():
            if t.is_alive():
                QTimer.singleShot(200, _poll)
                return
            self._btn_tag_fetch.setEnabled(True)
            tags = result[0]
            if tags:
                # Fill only empty fields
                if not self._title_edit.text().strip()  and tags.get('title'):
                    self._title_edit.setText(tags['title'])
                if not self._artist_edit.text().strip() and tags.get('artist'):
                    self._artist_edit.setText(tags['artist'])
                if not self._album_edit.text().strip()  and tags.get('album'):
                    self._album_edit.setText(tags['album'])
                self._btn_tag_fetch.setText('Auto-fill Tags…')
            else:
                self._btn_tag_fetch.setText('Not found')
                QTimer.singleShot(2000,
                    lambda: self._btn_tag_fetch.setText('Auto-fill Tags…'))

        QTimer.singleShot(200, _poll)

    def _remove_cover(self):
        self._cover_action = 'remove'
        self._new_cover_bytes = None
        self._cover_lbl.clear()
        self._cover_lbl.setText('Removed')

    def _on_lock_toggled(self, locked: bool):
        self._locked = locked
        self._locked_changed = True
        self._btn_cover_lock.setText('Locked' if locked else 'Unlocked')

    def get_tags(self):
        return self._title_edit.text(), self._artist_edit.text(), self._album_edit.text()

    def get_cover_result(self):
        """Returns (action, bytes|None, locked)."""
        return self._cover_action, self._new_cover_bytes, self._locked


# ══════════════════════════════════════════════════════════════════════════════
#  Custom slider cell for EQ table
# ══════════════════════════════════════════════════════════════════════════════
class EQSliderCell(QWidget):
    valueChanged = pyqtSignal(int, str, float)  # band index, param, new value

    def __init__(self, param_type: str, min_val, max_val, val, band_idx, parent=None):
        super().__init__(parent)
        self._param = param_type  # 'freq', 'gain', 'q'
        self._band_idx = band_idx
        self._min = min_val
        self._max = max_val
        self._val = val

        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self._slider = JumpSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 1000)
        self._slider.setValue(self._to_slider(val))
        self._slider.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._slider.valueChanged.connect(self._on_slider)

        self._label = QLabel(self._format(val))
        self._label.setFixedWidth(60)
        self._label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        lay.addWidget(self._slider, 1)
        lay.addWidget(self._label)

    def _to_slider(self, val):
        if self._param == 'freq':
            # logarithmic mapping
            if val <= 0:
                return 0
            log_min = math.log10(EQ_FREQ_MIN)
            log_max = math.log10(EQ_FREQ_MAX)
            log_val = math.log10(val)
            pos = (log_val - log_min) / (log_max - log_min) * 1000
            return int(max(0, min(1000, pos)))
        else:
            # linear
            return int((val - self._min) / (self._max - self._min) * 1000)

    def _from_slider(self, pos):
        if self._param == 'freq':
            log_min = math.log10(EQ_FREQ_MIN)
            log_max = math.log10(EQ_FREQ_MAX)
            log_val = log_min + (pos / 1000.0) * (log_max - log_min)
            return 10.0 ** log_val
        else:
            return self._min + (pos / 1000.0) * (self._max - self._min)

    def _format(self, val):
        if self._param == 'freq':
            return f"{val:.0f} Hz"
        elif self._param == 'gain':
            return f"{val:+.1f} dB"
        else:
            return f"{val:.2f}"

    def _on_slider(self, pos):
        val = self._from_slider(pos)
        # clamp due to rounding
        val = max(self._min, min(self._max, val))
        self._val = val
        self._label.setText(self._format(val))
        self.valueChanged.emit(self._band_idx, self._param, val)

    def set_value(self, val):
        self._val = val
        self._slider.setValue(self._to_slider(val))
        self._label.setText(self._format(val))

    def set_band_index(self, idx):
        self._band_idx = idx




# ══════════════════════════════════════════════════════════════════════════════
#  Cover art fetching + embedding
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_cover_itunes(artist: str, title: str) -> Optional[bytes]:
    try:
        q = _urlparse.quote(f'{artist} {title}')
        d = _get_json(f'https://itunes.apple.com/search?term={q}'
                      f'&media=music&entity=song&limit=5')
        for item in d.get('results', []):
            url = item.get('artworkUrl100', '')
            if url:
                url = url.replace('100x100bb', '600x600bb')
                data = _get(url)
                if isinstance(data, str): data = data.encode('latin1')
                if data and len(data) > 1000: return data
    except Exception: pass
    return None

def _fetch_cover_deezer(artist: str, title: str) -> Optional[bytes]:
    try:
        q = _urlparse.quote(f'artist:"{artist}" track:"{title}"')
        d = _get_json(f'https://api.deezer.com/search?q={q}&limit=3')
        for item in d.get('data', []):
            url = item.get('album', {}).get('cover_xl', '') or \
                  item.get('album', {}).get('cover_big', '')
            if url:
                data = _get(url)
                if isinstance(data, str): data = data.encode('latin1')
                if data and len(data) > 1000: return data
    except Exception: pass
    return None

def _fetch_cover_musicbrainz(artist: str, album: str) -> Optional[bytes]:
    try:
        q = _urlparse.quote(f'artist:"{artist}" AND release:"{album}"')
        d = _get_json(
            f'https://musicbrainz.org/ws/2/release/?query={q}&limit=5&fmt=json',
            headers={'Accept': 'application/json'})
        for rel in d.get('releases', [])[:3]:
            mbid = rel.get('id', '')
            if not mbid: continue
            url = f'https://coverartarchive.org/release/{mbid}/front-500'
            try:
                req = _urlreq.Request(url, headers={'User-Agent': 'BlackPlayer/2.0'})
                with _urlreq.urlopen(req, timeout=8) as r:
                    data = r.read()
                if data and len(data) > 1000: return data
            except Exception: pass
    except Exception: pass
    return None

def _fetch_cover_lastfm(artist: str, album: str) -> Optional[bytes]:
    # Uses public lastfm API with community key
    try:
        a = _urlparse.quote(artist); al = _urlparse.quote(album)
        url = (f'https://ws.audioscrobbler.com/2.0/?method=album.getinfo'
               f'&artist={a}&album={al}&api_key=f24e79dab45bed5e3d35c47e1f3e3bda&format=json')
        d = _get_json(url)
        images = d.get('album', {}).get('image', [])
        for img in reversed(images):
            img_url = img.get('#text', '')
            if img_url and 'noimage' not in img_url:
                data = _get(img_url)
                if isinstance(data, str): data = data.encode('latin1')
                if data and len(data) > 1000: return data
    except Exception: pass
    return None

def fetch_cover_online(artist: str, title: str, album: str) -> Optional[bytes]:
    """Try multiple sources, return raw image bytes or None."""
    for fn in [
        lambda: _fetch_cover_itunes(artist, title),
        lambda: _fetch_cover_deezer(artist, title),
        lambda: _fetch_cover_musicbrainz(artist, album),
        lambda: _fetch_cover_lastfm(artist, album),
    ]:
        try:
            data = fn()
            if data: return data
        except Exception: pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  Online tag / metadata lookup
# ══════════════════════════════════════════════════════════════════════════════

def _lookup_tags_musicbrainz(artist: str, title: str) -> dict:
    """Query MusicBrainz for recording metadata. Returns dict with keys:
    title, artist, album, date. All values may be empty strings."""
    try:
        q = _urlparse.quote(f'recording:"{title}" AND artist:"{artist}"')
        d = _get_json(
            f'https://musicbrainz.org/ws/2/recording/?query={q}&limit=5&fmt=json',
            headers={'Accept': 'application/json'})
        for rec in d.get('recordings', [])[:5]:
            t = rec.get('title', '').strip()
            rels = rec.get('releases', [])
            alb = rels[0].get('title', '').strip() if rels else ''
            date = rels[0].get('date', '')[:4] if rels else ''
            art_list = rec.get('artist-credit', [])
            art = art_list[0].get('artist', {}).get('name', '').strip() if art_list else ''
            if t or art:
                return {'title': t, 'artist': art, 'album': alb, 'date': date}
    except Exception:
        pass
    return {}


def _lookup_tags_itunes(artist: str, title: str) -> dict:
    """Query iTunes Search API for track metadata."""
    try:
        q = _urlparse.quote(f'{artist} {title}')
        d = _get_json(
            f'https://itunes.apple.com/search?term={q}&media=music&entity=song&limit=5')
        for item in d.get('results', []):
            return {
                'title':  item.get('trackName', '').strip(),
                'artist': item.get('artistName', '').strip(),
                'album':  item.get('collectionName', '').strip(),
                'date':   str(item.get('releaseDate', ''))[:4],
            }
    except Exception:
        pass
    return {}


def _lookup_tags_lastfm(artist: str, title: str) -> dict:
    """Query Last.fm track.getInfo for metadata."""
    try:
        a = _urlparse.quote(artist); t = _urlparse.quote(title)
        url = (f'https://ws.audioscrobbler.com/2.0/?method=track.getinfo'
               f'&artist={a}&track={t}&api_key=f24e79dab45bed5e3d35c47e1f3e3bda&format=json')
        d = _get_json(url)
        tr = d.get('track', {})
        alb = tr.get('album', {}).get('title', '').strip()
        return {
            'title':  tr.get('name', '').strip(),
            'artist': tr.get('artist', {}).get('name', '').strip() if isinstance(tr.get('artist'), dict) else tr.get('artist', '').strip(),
            'album':  alb,
            'date':   '',
        }
    except Exception:
        pass
    return {}


def lookup_tags_online(artist: str, title: str) -> dict:
    """Try multiple sources; return best result dict with title/artist/album keys.
    Only fields that are non-empty in the result should be used to fill gaps."""
    import concurrent.futures as _cf

    results = [{}]
    lock = threading.Lock()

    def _try(fn):
        try:
            r = fn()
            if r.get('album') or r.get('artist'):
                with lock:
                    # Merge: keep first non-empty value found per key
                    for k, v in r.items():
                        if v and not results[0].get(k):
                            results[0][k] = v
        except Exception:
            pass

    sources = [
        lambda: _lookup_tags_musicbrainz(artist, title),
        lambda: _lookup_tags_itunes(artist, title),
        lambda: _lookup_tags_lastfm(artist, title),
    ]
    with _cf.ThreadPoolExecutor(max_workers=3) as pool:
        _cf.wait([pool.submit(_try, fn) for fn in sources])

    return results[0]


def write_tags_to_file(fp: str, tags: dict) -> bool:
    """Write title/artist/album from tags dict into the audio file. Returns True on success."""
    try:
        ext = Path(fp).suffix.lower()
        af  = MutagenFile(fp, easy=False)
        if af is None: return False
        if ext == '.mp3':
            if af.tags is None: af.add_tags()
            if tags.get('title'):  af.tags['TIT2'] = tags['title']
            if tags.get('artist'): af.tags['TPE1'] = tags['artist']
            if tags.get('album'):  af.tags['TALB'] = tags['album']
        elif ext in ('.flac', '.ogg', '.opus'):
            if af.tags is None: af.add_tags()
            if tags.get('title'):  af.tags['title']  = [tags['title']]
            if tags.get('artist'): af.tags['artist'] = [tags['artist']]
            if tags.get('album'):  af.tags['album']  = [tags['album']]
        elif ext in ('.m4a', '.aac'):
            if af.tags is None: af.add_tags()
            if tags.get('title'):  af.tags['\xa9nam'] = [tags['title']]
            if tags.get('artist'): af.tags['\xa9ART'] = [tags['artist']]
            if tags.get('album'):  af.tags['\xa9alb'] = [tags['album']]
        else:
            return False
        af.save()
        return True
    except Exception as e:
        print(f'write_tags_to_file error: {e}')
        return False


def embed_cover_bytes(fp: str, data: bytes) -> bool:
    """Write cover bytes into the audio file tags. Returns True on success."""
    try:
        ext = Path(fp).suffix.lower()
        af  = MutagenFile(fp, easy=False)
        if af is None: return False

        if ext == '.mp3':
            from mutagen.id3 import ID3, APIC
            if af.tags is None: af.add_tags()
            mime = 'image/jpeg' if data[:3] == b'\xff\xd8\xff' else 'image/png'
            af.tags.delall('APIC')
            af.tags.add(APIC(encoding=3, mime=mime, type=3,
                             desc='Cover', data=data))

        elif ext == '.flac':
            from mutagen.flac import Picture
            pic = Picture()
            pic.type = 3; pic.mime = 'image/jpeg' if data[:3] == b'\xff\xd8\xff' else 'image/png'
            pic.desc = 'Cover'; pic.data = data
            af.clear_pictures(); af.add_picture(pic)

        elif ext in ('.m4a', '.aac'):
            from mutagen.mp4 import MP4Cover
            fmt = MP4Cover.FORMAT_JPEG if data[:3] == b'\xff\xd8\xff' else MP4Cover.FORMAT_PNG
            af.tags['covr'] = [MP4Cover(data, imageformat=fmt)]

        elif ext in ('.ogg', '.opus'):
            import base64
            from mutagen.flac import Picture
            pic = Picture()
            pic.type = 3; pic.mime = 'image/jpeg' if data[:3] == b'\xff\xd8\xff' else 'image/png'
            pic.desc = 'Cover'; pic.data = data
            encoded = base64.b64encode(pic.write()).decode('ascii')
            af.tags['metadata_block_picture'] = [encoded]
        else:
            return False

        af.save(); return True
    except Exception as e:
        print(f'embed_cover_bytes error: {e}'); return False


def embed_lyrics(fp: str, synced, plain: str) -> bool:
    """Write lyrics into audio file tags. Returns True on success."""
    try:
        ext = Path(fp).suffix.lower()
        af  = MutagenFile(fp, easy=False)
        if af is None: return False

        if synced:
            lrc_lines = [f'[{ms//60000:02d}:{(ms%60000)/1000:05.2f}]{txt}'
                         for ms, txt in synced]
            lrc_text = '\n'.join(lrc_lines)
        else:
            lrc_text = None

        text_to_write = lrc_text if lrc_text else plain

        if ext == '.mp3':
            from mutagen.id3 import USLT, SYLT, Encoding
            if af.tags is None: af.add_tags()
            af.tags.delall('USLT'); af.tags.delall('SYLT')
            af.tags.add(USLT(encoding=3, lang='eng', desc='', text=text_to_write))

        elif ext in ('.flac', '.ogg', '.opus'):
            if af.tags is None: af.add_tags()
            af.tags['LYRICS'] = [text_to_write]

        elif ext in ('.m4a', '.aac'):
            if af.tags is None: af.add_tags()
            af.tags['\xa9lyr'] = [text_to_write]

        else:
            return False

        af.save(); return True
    except Exception as e:
        print(f'embed_lyrics error: {e}'); return False

# ══════════════════════════════════════════════════════════════════════════════
#  Lyrics — fetch, parse, display
# ══════════════════════════════════════════════════════════════════════════════
import re          as _re
import html        as _html
import urllib.request as _urlreq
import urllib.parse   as _urlparse


# ── LRC parser ────────────────────────────────────────────────────────────────
def _lrc_parse(text: str):
    pat = _re.compile(r'\[(\d+):(\d+(?:\.\d+)?)\](.*)')
    lines = []
    for raw in text.splitlines():
        m = pat.match(raw.strip())
        if m:
            mm, ss_str, txt = m.groups()
            ms = int(mm) * 60000 + int(float(ss_str) * 1000)
            lines.append((ms, txt.strip()))
    return sorted(lines, key=lambda x: x[0]) if lines else None


# ── Embedded tags ─────────────────────────────────────────────────────────────
def _extract_embedded_lyrics(fp: str):
    try:
        af = MutagenFile(fp, easy=False)
        if af is None or af.tags is None:
            return None, None
        ext = Path(fp).suffix.lower()
        if ext == '.mp3':
            from mutagen.id3 import USLT, SYLT
            for tag in af.tags.values():
                if isinstance(tag, SYLT):
                    lines = sorted([(ms, t) for t, ms in tag.text if t.strip()],
                                   key=lambda x: x[0])
                    if lines: return lines, None
            for tag in af.tags.values():
                if isinstance(tag, USLT) and tag.text.strip():
                    p = _lrc_parse(tag.text)
                    return (p, None) if p else (None, tag.text.strip())
        else:
            tg = af.tags
            for key in ('lyrics', 'LYRICS', 'unsyncedlyrics', 'UNSYNCEDLYRICS'):
                v = tg.get(key)
                if v:
                    text = str(v[0]) if isinstance(v, list) else str(v)
                    if text.strip():
                        p = _lrc_parse(text)
                        return (p, None) if p else (None, text.strip())
    except Exception:
        pass
    return None, None


# ── Network helpers ───────────────────────────────────────────────────────────
def _get(url, timeout=8, headers=None):
    h = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) BlackPlayer/2.0'}
    if headers: h.update(headers)
    req = _urlreq.Request(url, headers=h)
    with _urlreq.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace')

def _get_json(url, timeout=8, headers=None):
    return json.loads(_get(url, timeout, headers))


# ── Source functions — each returns (synced|None, plain|None) or (None, text) ─

def _src_lrclib_exact(artist, title, album, dur):
    try:
        p = _urlparse.urlencode({'artist_name': artist, 'track_name': title,
                                  'album_name': album, 'duration': int(dur)})
        d = _get_json(f'https://lrclib.net/api/get?{p}')
        sl = d.get('syncedLyrics') or ''
        pl = d.get('plainLyrics')  or ''
        if sl.strip():
            lrc = _lrc_parse(sl)
            if lrc: return lrc, None
        if pl.strip(): return None, pl.strip()
    except Exception: pass
    return None, None

def _src_lrclib_search(artist, title):
    try:
        q = _urlparse.quote(f'{artist} {title}')
        results = _get_json(f'https://lrclib.net/api/search?q={q}')
        for item in results[:6]:
            sl = item.get('syncedLyrics') or ''
            pl = item.get('plainLyrics')  or ''
            if sl.strip():
                lrc = _lrc_parse(sl)
                if lrc: return lrc, None
            if pl.strip(): return None, pl.strip()
    except Exception: pass
    return None, None

def _src_lyrics_ovh(artist, title):
    try:
        a = _urlparse.quote(artist); t = _urlparse.quote(title)
        d = _get_json(f'https://api.lyrics.ovh/v1/{a}/{t}')
        txt = (d.get('lyrics') or '').strip()
        if txt: return None, txt
    except Exception: pass
    return None, None

def _src_chartlyrics(artist, title):
    try:
        a = _urlparse.quote(artist); t = _urlparse.quote(title)
        xml = _get(f'http://api.chartlyrics.com/apiv1.asmx/SearchLyricDirect?artist={a}&song={t}')
        m = _re.search(r'<Lyric>(.*?)</Lyric>', xml, _re.DOTALL)
        if m:
            txt = _html.unescape(m.group(1)).strip()
            if txt and len(txt) > 30: return None, txt
    except Exception: pass
    return None, None

def _src_musixmatch(artist, title):
    # Unofficial Musixmatch community token (no auth required for search)
    try:
        token = 'community'
        a = _urlparse.quote(artist); t = _urlparse.quote(title)
        base = 'https://api.musixmatch.com/ws/1.1'
        # search track
        d = _get_json(f'{base}/track.search?q_artist={a}&q_track={t}'
                      f'&apikey={token}&page_size=3&f_has_lyrics=1')
        items = (d.get('message', {}).get('body', {})
                   .get('track_list', []))
        for item in items[:3]:
            tid = item.get('track', {}).get('track_id')
            if not tid: continue
            d2 = _get_json(f'{base}/track.lyrics.get?track_id={tid}&apikey={token}')
            body = d2.get('message', {}).get('body', {})
            lyr = body.get('lyrics', {}).get('lyrics_body', '').strip()
            if lyr and '******* This Lyrics' not in lyr:
                return None, lyr
            # Also try subtitle (synced)
            d3 = _get_json(f'{base}/track.subtitle.get?track_id={tid}&apikey={token}')
            sub = (d3.get('message', {}).get('body', {})
                      .get('subtitle', {}).get('subtitle_body', ''))
            if sub.strip():
                lrc = _lrc_parse(sub)
                if lrc: return lrc, None
    except Exception: pass
    return None, None

def _src_genius_search(artist, title):
    # Genius web scraping — no API key
    try:
        q = _urlparse.quote(f'{artist} {title}')
        html_txt = _get(f'https://genius.com/search?q={q}',
                        headers={'Accept': 'text/html'})
        # Find first hit URL
        m = _re.search(r'"url":"(https://genius\.com/[^"]+lyrics[^"]*)"', html_txt)
        if not m: return None, None
        url = m.group(1)
        page = _get(url, headers={'Accept': 'text/html'})
        # Extract lyrics containers
        parts = _re.findall(
            r'<div[^>]*data-lyrics-container[^>]*>(.*?)</div>',
            page, _re.DOTALL)
        if not parts: return None, None
        lines = []
        for part in parts:
            clean = _re.sub(r'<br\s*/?>', '\n', part)
            clean = _re.sub(r'<[^>]+>', '', clean)
            lines.append(_html.unescape(clean).strip())
        txt = '\n'.join(lines).strip()
        if txt and len(txt) > 30: return None, txt
    except Exception: pass
    return None, None

def _src_azlyrics(artist, title):
    try:
        a = _re.sub(r'[^a-z0-9]', '', artist.lower())
        t = _re.sub(r'[^a-z0-9]', '', title.lower())
        url = f'https://www.azlyrics.com/lyrics/{a}/{t}.html'
        page = _get(url, headers={'Accept': 'text/html'}, timeout=9)
        m = _re.search(
            r'<!-- Usage of azlyrics.*?-->\s*(.*?)\s*</div>',
            page, _re.DOTALL)
        if m:
            raw = _re.sub(r'<[^>]+>', '', m.group(1))
            txt = _html.unescape(raw).strip()
            if txt and len(txt) > 30: return None, txt
    except Exception: pass
    return None, None

def _src_songlyrics(artist, title):
    try:
        a = _re.sub(r'[^a-z0-9-]', '-', artist.lower()).strip('-')
        t = _re.sub(r'[^a-z0-9-]', '-', title.lower()).strip('-')
        url = f'https://www.songlyrics.com/{a}/{t}-lyrics/'
        page = _get(url, headers={'Accept': 'text/html'})
        m = _re.search(r'<p id="songLyricsDiv"[^>]*>(.*?)</p>', page, _re.DOTALL)
        if m:
            raw = _re.sub(r'<[^>]+>', '', m.group(1))
            txt = _html.unescape(raw).strip()
            if txt and 'not found' not in txt.lower() and len(txt) > 30:
                return None, txt
    except Exception: pass
    return None, None

def _src_letras(artist, title):
    try:
        a = _re.sub(r'[^a-z0-9-]', '-', artist.lower()).strip('-')
        t = _re.sub(r'[^a-z0-9-]', '-', title.lower()).strip('-')
        url = f'https://www.letras.mus.br/{a}/{t}/'
        page = _get(url, headers={'Accept': 'text/html'})
        m = _re.search(r'<div class="lyric-original">(.*?)</div>', page, _re.DOTALL)
        if m:
            raw = _re.sub(r'<br\s*/?>', '\n', m.group(1))
            raw = _re.sub(r'<[^>]+>', '', raw)
            txt = _html.unescape(raw).strip()
            if txt and len(txt) > 30: return None, txt
    except Exception: pass
    return None, None


# ── Fetcher — sequential sources with status callbacks ────────────────────────
class ClickableLyricLine(QLabel):
    clicked = pyqtSignal(int)  # emits timestamp ms

    def __init__(self, text: str, ms: int, parent=None):
        super().__init__(text, parent)
        self._ms = ms
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._ms)
        super().mousePressEvent(e)


class LyricsFetcher(QObject):
    finished = pyqtSignal(object, object)   # synced|None, plain|None
    status   = pyqtSignal(str)              # progress message

    def __init__(self, track, fetch_online: bool = True):
        super().__init__()
        self._t = track
        self._fetch_online = fetch_online
        self.was_online = False   # set True if result came from network

    def run(self):
        import concurrent.futures as _cf
        t = self._t
        artist = (t.artist or '').strip()
        title  = (t.title  or '').strip()
        album  = (t.album  or '').strip()

        # 1. Embedded tags — instant, no network needed
        self.status.emit('Checking embedded tags…')
        synced, plain = _extract_embedded_lyrics(t.filepath)
        if synced or plain:
            self.finished.emit(synced, plain); return

        if not self._fetch_online:
            self.status.emit('')
            self.finished.emit(None, None); return

        # 2. All online sources fired in parallel.
        #    Synced result takes priority; among each tier first-to-respond wins.
        sources = [
            ('LrcLib (exact)',   lambda: _src_lrclib_exact(artist, title, album, t.duration)),
            ('LrcLib (search)',  lambda: _src_lrclib_search(artist, title)),
            ('Lyrics.ovh',       lambda: _src_lyrics_ovh(artist, title)),
            ('Musixmatch',       lambda: _src_musixmatch(artist, title)),
            ('Genius',           lambda: _src_genius_search(artist, title)),
            ('AZLyrics',         lambda: _src_azlyrics(artist, title)),
            ('SongLyrics',       lambda: _src_songlyrics(artist, title)),
            ('ChartLyrics',      lambda: _src_chartlyrics(artist, title)),
            ('Letras.mus.br',    lambda: _src_letras(artist, title)),
        ]

        self.status.emit('Searching lyrics…')

        result_lock = threading.Lock()
        best_synced = [None]
        best_plain  = [None]
        synced_event = threading.Event()   # set as soon as any synced result arrives

        def _run_source(fn):
            if synced_event.is_set():
                return   # synced already found, skip remaining
            try:
                s, p = fn()
            except Exception:
                return
            with result_lock:
                if s and best_synced[0] is None:
                    best_synced[0] = s
                    synced_event.set()
                elif p and best_plain[0] is None:
                    best_plain[0] = p

        with _cf.ThreadPoolExecutor(max_workers=len(sources)) as pool:
            futs = [pool.submit(_run_source, fn) for _, fn in sources]
            _cf.wait(futs)

        if best_synced[0] or best_plain[0]:
            self.was_online = True
            self.finished.emit(best_synced[0], best_plain[0])
            return

        self.status.emit('')
        self.finished.emit(None, None)


# ── Panel ─────────────────────────────────────────────────────────────────────
class LyricsPanel(QWidget):
    status_msg = pyqtSignal(str)   # forwarded to status bar
    seek_requested = pyqtSignal(int)  # seek to ms

    _LINE_H  = 38
    _LINE_SP = 4

    def __init__(self, player, ctrlbar=None, parent=None):
        super().__init__(parent)
        self._player   = player
        self._ctrlbar  = ctrlbar  # for lyrics_fetch_enabled flag
        self._synced   = []
        self._plain    = ''
        self._cur_idx  = -1
        self._track    = None
        self._thread: QThread  = None
        self._fetcher: LyricsFetcher = None   # keep ref to prevent GC
        self._pending_track = None
        self._fetch_id: int = 0   # incremented on each new fetch; guards stale callbacks

        self.setObjectName('lyrics_panel')
        self.setFixedWidth(290)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QWidget(); hdr.setFixedHeight(28)
        hdr.setStyleSheet(f'background:{BG2}; border-bottom:1px solid {BORD};')
        hl = QHBoxLayout(hdr); hl.setContentsMargins(12, 0, 8, 0)
        self._hdr_lbl = QLabel('Lyrics')
        self._hdr_lbl.setStyleSheet(f'color:{FG2};font-size:11px;background:transparent;')
        self._src_lbl = QLabel('')
        self._src_lbl.setStyleSheet(f'color:{FG2};font-size:10px;background:transparent;')
        hl.addWidget(self._hdr_lbl, 1); hl.addWidget(self._src_lbl)
        root.addWidget(hdr)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            'QScrollArea{border:none;background:transparent;}'
            'QScrollBar:vertical{background:#0d0d0d;width:3px;border-radius:1px;}'
            'QScrollBar::handle:vertical{background:#2a2a2a;border-radius:1px;min-height:20px;}'
            'QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}')

        self._cont = QWidget()
        self._cont.setStyleSheet('background:transparent;')
        self._cl = QVBoxLayout(self._cont)
        self._cl.setContentsMargins(14, 18, 14, 18)
        self._cl.setSpacing(self._LINE_SP)
        self._scroll.setWidget(self._cont)
        root.addWidget(self._scroll, 1)

        self._lbls: list = []

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(80)
        self._sync_timer.timeout.connect(self._tick)

    # ── public ──────────────────────────────────────────────────────────────

    def set_track(self, track, deferred=False):
        # Increment fetch_id before aborting so any in-flight _done callback is discarded
        self._fetch_id += 1
        self._track = track
        self._synced = []; self._plain = ''; self._cur_idx = -1
        self._sync_timer.stop()
        self._abort()
        if track:
            self._hdr_lbl.setText(track.title or '')
            fetch_ok = (self._ctrlbar is None or self._ctrlbar.lyrics_fetch_enabled)
            if deferred:
                self._pending_track = track
                self._show_status('Waiting for focus…')
            else:
                self._pending_track = None
                self._show_status('Searching…')
                self._start(track, fetch_ok)
        else:
            self._pending_track = None
            self._hdr_lbl.setText('Lyrics')
            self._show_status('')

    def on_focus_gained(self):
        """Call when app regains focus — starts deferred fetch if pending."""
        if self._pending_track and self._fetcher is None:
            track = self._pending_track
            self._pending_track = None
            self._show_status('Searching…')
            fetch_ok = (self._ctrlbar is None or self._ctrlbar.lyrics_fetch_enabled)
            self._start(track, fetch_ok)

    def on_position(self, ms: int):
        if self._synced:
            self._highlight(ms)

    def set_accent(self, _acc: str):
        if 0 <= self._cur_idx < len(self._lbls):
            self._style_lbl(self._lbls[self._cur_idx], True)

    # ── internal ────────────────────────────────────────────────────────────

    def _abort(self):
        if self._thread is not None:
            try:
                if self._thread.isRunning():
                    self._thread.quit()
                    self._thread.wait(300)
            except RuntimeError:
                pass  # C++ object already deleted
        self._thread  = None
        self._fetcher = None

    def _start(self, track, fetch_online: bool = True):
        # Increment generation counter so any in-flight callbacks become stale
        self._fetch_id += 1
        my_id = self._fetch_id
        thread  = QThread(self)
        fetcher = LyricsFetcher(track, fetch_online=fetch_online)
        fetcher.moveToThread(thread)
        thread.started.connect(fetcher.run)
        # Wrap _done with the current fetch_id so stale callbacks are ignored
        fetcher.finished.connect(lambda s, p, fid=my_id: self._done(s, p, fid))
        fetcher.finished.connect(thread.quit)
        fetcher.status.connect(self.status_msg)   # forward to status bar
        thread.finished.connect(thread.deleteLater)
        self._thread  = thread
        self._fetcher = fetcher   # prevent GC!
        thread.start()

    def _done(self, synced, plain, fetch_id: int = -1):
        # Ignore callbacks from previous fetch cycles (stale results)
        if fetch_id != self._fetch_id:
            return
        fetcher = self._fetcher; self._fetcher = None
        if self._track is None: return
        if synced:
            self._synced = synced
            self._src_lbl.setText('synced')
            self._build_synced()
            self._sync_timer.start()
            self._tick()
        elif plain:
            self._plain = plain
            self._src_lbl.setText('')
            self._build_plain()
        else:
            fetch_off = self._ctrlbar and not self._ctrlbar.lyrics_fetch_enabled
            msg = 'File does not contain lyrics.' if fetch_off else 'Lyrics not found.'
            self._show_status(msg)
            self._src_lbl.setText('')
            return
        # Embed into file if fetched from network (fetcher flag) and not already embedded
        if fetcher and fetcher.was_online and self._track:
            fp = self._track.filepath
            threading.Thread(
                target=embed_lyrics, args=(fp, synced, plain or ''),
                daemon=True).start()

    def _clear(self):
        while self._cl.count():
            it = self._cl.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        self._lbls = []

    def _show_status(self, msg):
        self._sync_timer.stop(); self._clear()
        if not msg: return
        lbl = QLabel(msg)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f'color:{FG2};font-size:13px;background:transparent;')
        self._cl.addStretch(); self._cl.addWidget(lbl); self._cl.addStretch()

    def _style_lbl(self, lbl, active: bool):
        if active:
            lbl.setStyleSheet(
                f'color:{ACC};font-size:16px;font-weight:600;'
                f'padding:0 2px;background:transparent;')
        else:
            lbl.setStyleSheet(
                f'color:{FG2};font-size:14px;padding:0 2px;background:transparent;')

    def _build_synced(self):
        self._clear()
        for ms, txt in self._synced:
            lbl = ClickableLyricLine(txt if txt else '·', ms)
            lbl.setWordWrap(True)
            lbl.setFixedHeight(self._LINE_H)
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._style_lbl(lbl, False)
            lbl.clicked.connect(self.seek_requested)
            self._lbls.append(lbl)
            self._cl.addWidget(lbl)
        self._cl.addStretch()

    def _build_plain(self):
        self._clear()
        lbl = QLabel(self._plain)
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        lbl.setStyleSheet(
            f'color:{FG2};font-size:14px;line-height:1.7;background:transparent;')
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._cl.addWidget(lbl); self._cl.addStretch()

    def _highlight(self, ms: int):
        if not self._synced or not self._lbls: return
        idx = 0
        for i, (t, _) in enumerate(self._synced):
            if t <= ms: idx = i
            else:       break
        if idx == self._cur_idx: return
        if 0 <= self._cur_idx < len(self._lbls):
            self._style_lbl(self._lbls[self._cur_idx], False)
        self._cur_idx = idx
        self._style_lbl(self._lbls[idx], True)
        # Inertia scroll via QPropertyAnimation
        step   = self._LINE_H + self._LINE_SP
        target = idx * step - self._scroll.height() // 2 + self._LINE_H // 2
        target = max(0, target)
        bar = self._scroll.verticalScrollBar()
        anim = QPropertyAnimation(bar, b'value', self)
        anim.setDuration(420)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(bar.value())
        anim.setEndValue(target)
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def _tick(self):
        if not self._synced: return
        try:
            ok, p = self._player._pipe.query_position(Gst.Format.TIME)
            if ok: self._highlight(p // Gst.MSECOND)
        except Exception:
            pass


class TouchComboBox(QComboBox):
    """QComboBox that won't close its popup immediately after opening on touch."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_opened_ms = 0

    def showPopup(self):
        self._popup_opened_ms = QDateTime.currentMSecsSinceEpoch()
        super().showPopup()

    def hidePopup(self):
        # Block immediate close within 400 ms of opening (touch double-fire)
        if QDateTime.currentMSecsSinceEpoch() - self._popup_opened_ms < 400:
            return
        super().hidePopup()


# ══════════════════════════════════════════════════════════════════════════════
#  EQ Popup – parametric equalizer with profiles
# ══════════════════════════════════════════════════════════════════════════════
class EqPopup(QFrame):
    eq_changed = pyqtSignal(list, bool)   # bands, enabled

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('eq_popup')
        # Tool window: does NOT auto-close when OSK or other windows take focus.
        # User dismisses via the EQ button toggle or the ✕ close button.
        self.setWindowFlags(
            Qt.WindowType.Tool |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(False)
        # Close when user clicks outside this window (anywhere in the app)
        QApplication.instance().installEventFilter(self)

        self._bands = []          # list of (freq, gain, Q)
        self._hidden_by_outside = False
        self._enabled = True
        self._profiles = {}       # name -> list of bands
        self._current_profile = ""
        self._default_bands = []  # stored default (bands, enabled)
        self._default_enabled = True

        # Debounce timer for applying changes
        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.setInterval(300)  # 300 ms
        self._apply_timer.timeout.connect(self._apply)

        self._build_ui()
        self._update_graph()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(16, 10, 16, 12)
        main.setSpacing(7)

        hdr = QLabel('PARAMETRIC EQ'); hdr.setObjectName('popup_title')
        main.addWidget(hdr)

        # Profile management
        prof_layout = QHBoxLayout()
        prof_label = QLabel('Profile:')
        prof_layout.addWidget(prof_label)
        self._loaded_lbl = None   # removed from UI, kept for compat

        self._NEW = '＋ New'   # sentinel — always first item
        self._profile_combo = TouchComboBox()
        self._profile_combo.setEditable(True)
        self._profile_combo.setMinimumWidth(150)
        self._profile_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._profile_combo.setCompleter(None)   # no autocomplete / no filter while typing
        self._profile_combo.setStyleSheet(
            'QComboBox { background:#141414; color:#f0f0f0; border:1px solid #444;'
            ' border-radius:6px; padding:4px 8px 4px 8px; min-height:30px; }'
            'QComboBox:focus { border-color:' + ACC + '; }'
            'QComboBox::drop-down { width:44px; border-left:1px solid #555;'
            ' background:#222222; border-radius:0 6px 6px 0; }'
            'QComboBox::down-arrow { width:16px; height:16px; }'
            'QComboBox QAbstractItemView { background:#1e1e1e; color:#f0f0f0;'
            ' selection-background-color:#282828; border:1px solid #444; }'
            'QComboBox QAbstractItemView::item { min-height:35px; padding:0 8px; }')
        if self._profile_combo.lineEdit():
            le = self._profile_combo.lineEdit()
            le.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
            le.setPlaceholderText('Profile name…')
        # Force item height via the popup list viewf
        combo_view = self._profile_combo.view()
        if combo_view:
            combo_view.setUniformItemSizes(True)
            combo_view.setSpacing(0)
        self._profile_combo.addItem(self._NEW)  # always first
        # ONLY load/react when user explicitly selects from dropdown
        self._profile_combo.activated.connect(self._on_profile_activated)
        prof_layout.addWidget(self._profile_combo)

        self._btn_save = QPushButton('Save')
        self._btn_save.clicked.connect(self._save_profile)
        self._btn_del = QPushButton('Delete')
        self._btn_del.clicked.connect(self._delete_profile)
        prof_layout.addWidget(self._btn_save)
        prof_layout.addWidget(self._btn_del)
        self._enable_sw = ToggleSwitch('EQ')
        self._enable_sw.setChecked(True)
        self._enable_sw.toggled.connect(self._on_enable_toggled)
        prof_layout.addWidget(self._enable_sw)
        self._btn_default = QPushButton('Set Default')
        self._btn_default.clicked.connect(self._set_as_default)
        prof_layout.addWidget(self._btn_default)
        prof_layout.addStretch()
        main.addLayout(prof_layout)



        # Frequency response graph
        self._graph = EQGraph(self)
        self._graph.setFixedHeight(200)
        main.addWidget(self._graph)

        # Band table
        table_label = QLabel('Bands')
        table_label.setObjectName('setting_lbl')
        main.addWidget(table_label)

        self._band_table = QTableWidget(0, 3)
        self._band_table.setHorizontalHeaderLabels(['Frequency', 'Gain', 'Q', ''])
        # Set column widths: last column fixed 40px, others stretch
        self._band_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._band_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._band_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._band_table.verticalHeader().setVisible(False)
        self._band_table.verticalHeader().setDefaultSectionSize(46)
        self._band_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._band_table.setMinimumHeight(240)
        self._band_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        QScroller.grabGesture(self._band_table.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        _eq_sp = QScrollerProperties()
        _eq_sp.setScrollMetric(QScrollerProperties.ScrollMetric.DecelerationFactor,         0.35)
        _eq_sp.setScrollMetric(QScrollerProperties.ScrollMetric.MaximumVelocity,            0.8)
        _eq_sp.setScrollMetric(QScrollerProperties.ScrollMetric.VerticalOvershootPolicy,
                               QScrollerProperties.OvershootPolicy.OvershootAlwaysOff)
        _eq_sp.setScrollMetric(QScrollerProperties.ScrollMetric.HorizontalOvershootPolicy,
                               QScrollerProperties.OvershootPolicy.OvershootAlwaysOff)
        QScroller.scroller(self._band_table.viewport()).setScrollerProperties(_eq_sp)
        main.addWidget(self._band_table)

        # Add/Remove buttons
        btn_row = QHBoxLayout()
        self._btn_add = QPushButton('+ Add Band')
        self._btn_add.clicked.connect(self._add_band)
        self._btn_remove = QPushButton('- Remove')
        self._btn_remove.clicked.connect(self._remove_selected_band)
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_remove)
        btn_row.addStretch()
        main.addLayout(btn_row)

        self.setFixedWidth(960)
        self.setMinimumHeight(640)
        self.adjustSize()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QBrush(QColor('#000000')))
        p.setPen(QPen(QColor(B2), 1.0))
        p.drawRoundedRect(r, 12, 12)
        p.end()

    def _on_enable_toggled(self, on):
        self._enabled = on
        self._graph.set_enabled(on)
        self._apply_timer.start()  # apply after toggle

    def _on_freq_scale_changed(self, log: bool):
        self._freq_log = log
        self._graph.set_freq_log(log)
        for row in range(self._band_table.rowCount()):
            cell = self._band_table.cellWidget(row, 0)
            if cell and hasattr(cell, 'set_freq_log'):
                cell.set_freq_log(log)

    def _add_band(self):
        if len(self._bands) >= MAX_EQ_BANDS:
            self._btn_add.setText(f'Max {MAX_EQ_BANDS} bands')
            self._btn_add.setEnabled(False)
            def _restore():
                self._btn_add.setText('+ Add Band')
                self._btn_add.setEnabled(True)
            QTimer.singleShot(2000, _restore)
            return
        # Default values: 1000 Hz, 0 dB, Q=1.0
        self._bands.append((1000.0, 0.0, 1.0))
        self._refresh_table()
        self._update_graph()
        self._apply_timer.start()

    def _remove_selected_band(self):
        row = self._band_table.currentRow()
        if row >= 0 and row < len(self._bands):
            del self._bands[row]
            self._refresh_table()
            self._update_graph()
            self._apply_timer.start()

    def _refresh_table(self):
        self._band_table.setRowCount(len(self._bands))
        for i, (f, g, q) in enumerate(self._bands):
            # Frequency slider cell
            freq_cell = EQSliderCell('freq', EQ_FREQ_MIN, EQ_FREQ_MAX, f, i)
            freq_cell.valueChanged.connect(self._on_slider_changed)
            self._band_table.setCellWidget(i, 0, freq_cell)

            # Gain slider cell
            gain_cell = EQSliderCell('gain', EQ_GAIN_MIN, EQ_GAIN_MAX, g, i)
            gain_cell.valueChanged.connect(self._on_slider_changed)
            self._band_table.setCellWidget(i, 1, gain_cell)

            # Q slider cell
            q_cell = EQSliderCell('q', EQ_Q_MIN, EQ_Q_MAX, q, i)
            q_cell.valueChanged.connect(self._on_slider_changed)
            self._band_table.setCellWidget(i, 2, q_cell)

    def _on_slider_changed(self, band_idx, param, new_val):
        """Update the band in self._bands."""
        if band_idx >= len(self._bands):
            return
        f, g, q = self._bands[band_idx]
        if param == 'freq':
            f = new_val
        elif param == 'gain':
            g = new_val
        elif param == 'q':
            q = new_val
        self._bands[band_idx] = (f, g, q)
        # Update graph immediately
        self._update_graph()
        # Schedule apply after a short delay
        self._apply_timer.start()

    def _remove_band_at(self, idx):
        if idx < len(self._bands):
            del self._bands[idx]
            self._refresh_table()
            self._update_graph()
            self._apply_timer.start()

    def _update_graph(self):
        self._graph.set_bands(self._bands)

    def _apply(self):
        """Emit eq_changed so the player updates."""
        self.eq_changed.emit(self._bands, self._enabled)

    def _on_profile_activated(self, index):
        """Called only when user explicitly picks an item from the dropdown."""
        name = self._profile_combo.itemText(index)
        if name == self._NEW:
            # Start fresh: clear bands, clear name field so user can type new name
            self._bands = []
            self._current_profile = ''
            self._profile_combo.lineEdit().clear()
            if self._loaded_lbl: self._loaded_lbl.setText('Loaded: —')
            self._refresh_table()
            self._update_graph()
            self._apply_timer.start()
        elif name and name in self._profiles:
            self._bands = [list(b) for b in self._profiles[name]]
            self._refresh_table()
            self._update_graph()
            self._current_profile = name
            if self._loaded_lbl: self._loaded_lbl.setText(f'Loaded: {name}')
            self._apply_timer.start()

    def _on_profile_selected(self, name):
        """Legacy: only called programmatically (e.g. after save)."""
        pass  # typing in the combo no longer triggers anything

    def _save_profile(self):
        name = self._profile_combo.currentText().strip()
        if not name or name == self._NEW:
            QMessageBox.warning(self, 'Error', 'Profile name cannot be empty.')
            return
        self._profiles[name] = [b for b in self._bands]
        # Add after ＋New if new; keep ＋New always at index 0
        if self._profile_combo.findText(name) < 0:
            self._profile_combo.insertItem(1, name)   # insert at 1, after ＋New
        self._profile_combo.setCurrentText(name)
        self._current_profile = name
        if self._loaded_lbl: self._loaded_lbl.setText(f'Loaded: {name}')

    def _delete_profile(self):
        name = self._profile_combo.currentText().strip()
        if name and name != self._NEW and name in self._profiles:
            del self._profiles[name]
            idx = self._profile_combo.findText(name)
            if idx >= 0:
                self._profile_combo.removeItem(idx)
            # Select ＋New, clear bands
            self._profile_combo.setCurrentIndex(0)
            self._profile_combo.lineEdit().clear()
            self._current_profile = ''
            if self._loaded_lbl: self._loaded_lbl.setText('Loaded: —')
            self._bands = []
            self._refresh_table()
            self._update_graph()

    def _set_as_default(self):
        """Save current bands and enabled as default."""
        self._default_bands = [b for b in self._bands]
        self._default_enabled = self._enabled
        self._default_profile_name = self._current_profile
        QToolTip.showText(self.mapToGlobal(QPoint(0,0)), 'Saved as default')

    # Public methods to set/get state
    def set_bands(self, bands, enabled, name=''):
        self._bands = [list(b) for b in bands]
        self._enabled = enabled
        self._enable_sw.setChecked(enabled)
        self._refresh_table()
        self._update_graph()
        if name:
            self._current_profile = name
            if self._loaded_lbl: self._loaded_lbl.setText(f'Loaded: {name}')
            idx = self._profile_combo.findText(name)
            if idx >= 0:
                self._profile_combo.blockSignals(True)
                self._profile_combo.setCurrentIndex(idx)
                self._profile_combo.blockSignals(False)
            elif self._profile_combo.lineEdit():
                self._profile_combo.lineEdit().setText(name)
        self.eq_changed.emit(self._bands, self._enabled)

    def set_profiles(self, profiles):
        self._profiles = profiles
        self._profile_combo.clear()
        self._profile_combo.addItem(self._NEW)  # always first
        for name in sorted(profiles.keys()):
            self._profile_combo.addItem(name)
        if self._current_profile:
            idx = self._profile_combo.findText(self._current_profile)
            if idx >= 0:
                self._profile_combo.blockSignals(True)
                self._profile_combo.setCurrentIndex(idx)
                self._profile_combo.blockSignals(False)

    def get_profiles(self):
        return self._profiles

    def set_default(self, bands, enabled, name=''):
        self._default_bands = [list(b) for b in bands]
        self._default_enabled = enabled
        self._default_profile_name = name

    def get_default_name(self) -> str:
        return getattr(self, '_default_profile_name', '')

    def get_default(self):
        return self._default_bands, self._default_enabled

    def show_above(self, btn: QWidget):
        gpos = btn.mapToGlobal(QPoint(0, 0))
        self.adjustSize()
        x = gpos.x() + btn.width()//2 - self.width()//2
        y = gpos.y() - self.height() - 6
        screen = QApplication.primaryScreen().availableGeometry()
        x = max(screen.left()+4, min(x, screen.right()-self.width()-4))
        y = max(screen.top()+4, y)
        self.move(x, y)
        self.show(); self.raise_()
        
    def eventFilter(self, obj, e: QEvent) -> bool:
        """Close EQ popup on click outside it (within the application)."""
        if (self.isVisible() and
                e.type() == QEvent.Type.MouseButtonPress and
                QApplication.activePopupWidget() is None and
                obj is not self and
                not (isinstance(obj, QWidget) and self.isAncestorOf(obj)) and
                not self.rect().contains(
                    self.mapFromGlobal(e.globalPosition().toPoint()))):
            self.hide()
            self._hidden_by_outside = True
        return False

    def show_center(self):
        """Show popup in the center of the screen."""
        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.center().x() - self.width() // 2
        y = screen.center().y() - self.height() // 2
        x = max(screen.left() + 4, min(x, screen.right() - self.width() - 4))
        y = max(screen.top() + 4, min(y, screen.bottom() - self.height() - 4))
        self.move(x, y)
        self.show()
        self.raise_()


class EQGraph(QWidget):
    """Widget to draw frequency response of the current EQ bands."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bands = []
        self._enabled = True
        self.setMinimumHeight(100)

    def set_bands(self, bands):
        self._bands = bands
        self.update()

    def set_enabled(self, en):
        self._enabled = en
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w < 10 or h < 10:
            return

        # Background
        p.fillRect(self.rect(), QColor('#000000'))

        # Draw grid
        p.setPen(QPen(QColor(BORD), 1))
        # Horizontal lines (every 2 dB)
        for db in range(-10, 11, 2):
            y = h/2 - (db * (h/2) / EQ_GAIN_MAX_GRAPH)
            if 0 <= y <= h:
                p.drawLine(0, int(y), w, int(y))
        # Vertical lines (decades)
        for decade in range(1, 5):
            freq = 10**decade  # 10,100,1000,10000
            x = w * (math.log10(freq) - math.log10(20)) / (math.log10(22000)-math.log10(20))
            if 0 <= x <= w:
                p.drawLine(int(x), 0, int(x), h)

        if not self._enabled:
            # Draw bypass text
            p.setPen(QColor(FG2))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'EQ disabled')
            return

        if not self._bands:
            return

        # Precompute points for each band and total
        steps = w
        xs = [i for i in range(steps)]
        freqs = [20.0 * (22000.0/20.0) ** (i/(steps-1)) for i in range(steps)]

        # Prepare colors for each band (distinct hues)
        band_colors = []
        for i in range(len(self._bands)):
            hue = (i * 360 / max(1, len(self._bands))) % 360
            color = QColor.fromHsvF(hue/360.0, 0.8, 1.0, 0.4)  # semi-transparent
            band_colors.append(color)

        # For each frequency point, compute gain contribution per band and total
        band_gains = [[] for _ in self._bands]
        total_gains = []
        for freq in freqs:
            total_db = 0.0
            for idx, (f0, g, q) in enumerate(self._bands):
                if g == 0:
                    band_gains[idx].append(0.0)
                    continue
                # Approximate bell shape: Gaussian in log frequency
                bw = 1.0 / q  # approximate bandwidth in octaves
                octave_diff = math.log2(freq / f0)
                weight = math.exp(- (octave_diff / bw)**2)
                contrib = g * weight
                band_gains[idx].append(contrib)
                total_db += contrib
            total_gains.append(total_db)

        # Draw each band's curve
        for idx, gains in enumerate(band_gains):
            if max(gains) == 0:
                continue
            points = []
            for i, g in enumerate(gains):
                y = h/2 - (g * (h/2) / EQ_GAIN_MAX_GRAPH)
                points.append(QPointF(xs[i], y))
            if len(points) > 1:
                pen = QPen(band_colors[idx], 1.5)
                pen.setStyle(Qt.PenStyle.DashLine)
                p.setPen(pen)
                p.drawPolyline(*points)

        # Draw total curve (white, solid)
        total_points = []
        for i, db in enumerate(total_gains):
            db_clipped = max(-EQ_GAIN_MAX_GRAPH, min(EQ_GAIN_MAX_GRAPH, db))
            y = h/2 - (db_clipped * (h/2) / EQ_GAIN_MAX_GRAPH)
            total_points.append(QPointF(xs[i], y))
        if len(total_points) > 1:
            p.setPen(QPen(Qt.GlobalColor.white, 2))
            p.drawPolyline(*total_points)


def _fmt_ms(ms: int) -> str:
    t = ms // 1000; h, r = divmod(t, 3600); m, s = divmod(r, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


# ══════════════════════════════════════════════════════════════════════════════
#  Blackout overlay
# ══════════════════════════════════════════════════════════════════════════════
class BlackoutOverlay(QWidget):
    """Full-screen OLED burn-in protection overlay.
    Shows time, track title/artist and a progress bar in red,
    fading in/out at random positions every ~10 seconds."""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.BypassWindowManagerHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)

        # Track / position state
        self._title  = ''
        self._artist = ''
        self._pos_ms = 0
        self._dur_ms = 0

        # Widget offset (randomised each cycle)
        self._ox = 0.3; self._oy = 0.35   # fractional position 0..1

        # Fade animation (opacity effect on a child container)
        self._container = QWidget(self)
        self._container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._opacity_effect = QGraphicsOpacityEffect(self._container)
        self._opacity_effect.setOpacity(0.0)
        self._container.setGraphicsEffect(self._opacity_effect)

        self._anim = QPropertyAnimation(self._opacity_effect, b'opacity', self)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)

        # Clock refresh timer (every second)
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._container.update)

        # Cycle timer: visible 8s, then fade out, reposition, fade in
        self._cycle_timer = QTimer(self)
        self._cycle_timer.setSingleShot(True)
        self._cycle_timer.timeout.connect(self._start_fade_out)

    # ── public api ────────────────────────────────────────────────────────────
    def set_track(self, title: str, artist: str):
        self._title = title; self._artist = artist
        if self.isVisible(): self._container.update()

    def set_pos(self, pos_ms: int, dur_ms: int):
        self._pos_ms = pos_ms; self._dur_ms = dur_ms
        if self.isVisible(): self._container.update()

    # ── dismiss ───────────────────────────────────────────────────────────────
    def _dismiss(self):
        self._cycle_timer.stop(); self._clock_timer.stop()
        self._anim.stop()
        self.hide()

    def mousePressEvent(self, e): self._dismiss()
    def keyPressEvent(self, e):   self._dismiss()

    def event(self, e):
        if e.type() in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate,
                        QEvent.Type.TouchEnd):
            self._dismiss(); return True
        return super().event(e)

    # ── show / cycle ──────────────────────────────────────────────────────────
    def show_blackout(self):
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self._reposition()
        self.showFullScreen(); self.raise_(); self.activateWindow()
        self._clock_timer.start()
        self._start_fade_in()

    def _reposition(self):
        """Randomise container position (keep it well inside screen bounds)."""
        import random as _rnd
        sw, sh = self.width() or 1920, self.height() or 1080
        cw, ch = self._container.width() or 320, self._container.height() or 120
        max_x = max(0, sw - cw); max_y = max(0, sh - ch)
        self._ox = _rnd.randint(0, max(1, max_x))
        self._oy = _rnd.randint(0, max(1, max_y))
        self._container.move(self._ox, self._oy)

    def _start_fade_in(self):
        self._reposition()
        self._anim.stop()
        self._anim.setDuration(800)
        self._anim.setStartValue(0.0); self._anim.setEndValue(1.0)
        self._anim.finished.disconnect() if self._anim.receivers(self._anim.finished) else None
        self._anim.start()
        self._cycle_timer.start(8000)    # stay visible 8 s

    def _start_fade_out(self):
        self._anim.stop()
        self._anim.setDuration(600)
        self._anim.setStartValue(1.0); self._anim.setEndValue(0.0)
        try: self._anim.finished.disconnect()
        except: pass
        self._anim.finished.connect(self._start_fade_in)
        self._anim.start()

    # ── layout / paint ────────────────────────────────────────────────────────
    def resizeEvent(self, e):
        super().resizeEvent(e)
        # Size the container to fit content (fixed size is fine)
        self._container.setFixedSize(min(520, self.width()-60), 140)
        self._reposition()

    def paintEvent(self, _):
        # Full-screen solid black
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#000000'))
        p.end()

    # ── container paint (drawn inside the opacity-animated child) ─────────────
    # We override the container's paintEvent via an event filter
    def _paint_info(self, p: QPainter):
        r = QRectF(self._container.rect())
        w, h = r.width(), r.height()
        if w < 10: return

        RED = QColor(ACC)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Clock (top)
        p.setPen(RED)
        font = p.font(); font.setPixelSize(22); font.setBold(True); p.setFont(font)
        now = QDateTime.currentDateTime().toString('HH:mm:ss')
        p.drawText(QRectF(0, 0, w, 30), Qt.AlignmentFlag.AlignCenter, now)

        # Title
        font.setPixelSize(18); font.setBold(True); p.setFont(font)
        title = self._title or '—'
        fm = QFontMetrics(font)
        title = fm.elidedText(title, Qt.TextElideMode.ElideRight, int(w))
        p.drawText(QRectF(0, 34, w, 26), Qt.AlignmentFlag.AlignCenter, title)

        # Artist
        font.setPixelSize(14); font.setBold(False); p.setFont(font)
        artist = self._artist or ''
        fm2 = QFontMetrics(font)
        artist = fm2.elidedText(artist, Qt.TextElideMode.ElideRight, int(w))
        p.drawText(QRectF(0, 62, w, 22), Qt.AlignmentFlag.AlignCenter, artist)

        # Progress bar
        if self._dur_ms > 0:
            frac = max(0.0, min(1.0, self._pos_ms / self._dur_ms))
            bar_y = 94.0; bar_h = 4.0; bar_w = w - 20
            # track
            p.setPen(Qt.PenStyle.NoPen)
            dark = QColor(ACC); dark.setAlpha(55)
            p.setBrush(QBrush(dark))
            p.drawRoundedRect(QRectF(10, bar_y, bar_w, bar_h), 2, 2)
            # fill
            p.setBrush(QBrush(RED))
            if frac > 0:
                p.drawRoundedRect(QRectF(10, bar_y, bar_w*frac, bar_h), 2, 2)
            # time labels
            p.setPen(RED)
            font.setPixelSize(12); p.setFont(font)
            p.drawText(QRectF(8, 101, 60, 18), Qt.AlignmentFlag.AlignLeft,
                       _fmt_ms(self._pos_ms))
            p.drawText(QRectF(w-70, 101, 62, 18), Qt.AlignmentFlag.AlignRight,
                       _fmt_ms(self._dur_ms))

    def showEvent(self, e):
        super().showEvent(e)
        # Install event filter on container to intercept paintEvent
        self._container.installEventFilter(self)

    def eventFilter(self, obj, e):
        if obj is self._container and e.type() == QEvent.Type.Paint:
            p = QPainter(self._container)
            self._paint_info(p)
            p.end()
            return True
        if e.type() in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate,
                        QEvent.Type.TouchEnd):
            self._dismiss(); return True
        return super().eventFilter(obj, e)


# ══════════════════════════════════════════════════════════════════════════════
#  Custom tab-bar close button (unchanged)
# ══════════════════════════════════════════════════════════════════════════════
class TabCloseButton(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def sizeHint(self): return QSize(16, 16)
    def enterEvent(self, e): self.update(); super().enterEvent(e)
    def leaveEvent(self, e): self.update(); super().leaveEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Blit parent pixels so our background matches the tab exactly
        if self.parent():
            pos = self.mapToParent(QPoint(0, 0))
            self.parent().render(p, QPoint(0, 0),
                                 QRegion(pos.x(), pos.y(), self.width(), self.height()))
        # X in accent color (dark shade, brighter on hover)
        acc = QColor(ACC)
        h, s, v, _ = acc.getHsvF()
        xcolor = QColor()
        xcolor.setHsvF(h, min(1.0, s), 0.85 if self.underMouse() else 0.55)
        pen = QPen(xcolor, 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        m = 3.5
        p.drawLine(QPointF(m, m), QPointF(16 - m, 16 - m))
        p.drawLine(QPointF(16 - m, m), QPointF(m, 16 - m))
        p.end()


# ══════════════════════════════════════════════════════════════════════════════
#  Data model (unchanged)
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class Track:
    filepath:    str
    title:       str   = ''
    artist:      str   = ''
    album:       str   = ''
    duration:    float = 0.0
    sample_rate: int   = 0
    bit_depth:   int   = 0
    file_type:   str   = ''

    def dur_str(self):
        t = int(self.duration); h, r = divmod(t, 3600); m, s = divmod(r, 60)
        return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'

    def sr_str(self):
        if not self.sample_rate: return ''
        k = self.sample_rate/1000
        return f'{k:.1f} kHz' if k % 1 else f'{int(k)} kHz'

    def bd_str(self): return f'{self.bit_depth}-bit' if self.bit_depth else ''

    def sort_key(self):
        return (self.artist.lower() or '\xff', self.album.lower() or '\xff',
                self.title.lower() or '\xff')


def _tag(tags, *keys):
    for k in keys:
        v = tags.get(k)
        if v: return str(v[0]) if isinstance(v, list) else str(v)
    return ''


def read_metadata(fp: str) -> Track:
    p = Path(fp); ext = p.suffix.lower()
    tr = Track(filepath=fp, title=p.stem, file_type=ext.lstrip('.').upper())
    try:
        af = MutagenFile(fp, easy=False)
        if af is None: return tr
        i = af.info
        tr.duration    = getattr(i, 'length', 0.0)
        tr.sample_rate = getattr(i, 'sample_rate', 0)
        for a in ('bits_per_sample', 'bits_per_raw_sample'):
            v = getattr(i, a, 0)
            if v: tr.bit_depth = v; break
        tg = af.tags
        if tg is None: return tr
        if ext == '.mp3':
            tr.title  = _tag(tg, 'TIT2') or tr.title
            tr.artist = _tag(tg, 'TPE1', 'TPE2'); tr.album = _tag(tg, 'TALB')
        elif ext in ('.flac', '.opus', '.ogg'):
            tr.title  = _tag(tg, 'title') or tr.title
            tr.artist = _tag(tg, 'artist', 'albumartist'); tr.album = _tag(tg, 'album')
        elif ext in ('.m4a', '.aac'):
            tr.title  = _tag(tg, '\xa9nam') or tr.title
            tr.artist = _tag(tg, '\xa9ART', 'aART'); tr.album = _tag(tg, '\xa9alb')
        else:
            tr.title  = _tag(tg, 'title',  'TITLE') or tr.title
            tr.artist = _tag(tg, 'artist', 'ARTIST'); tr.album = _tag(tg, 'album', 'ALBUM')
    except Exception:
        pass
    return tr



# ── Cover art ─────────────────────────────────────────────────────────────────
_cover_cache: dict = {}   # filepath → QPixmap | None  (keyed by (fp, size))

def extract_cover_bytes(fp: str) -> Optional[bytes]:
    """Return raw cover bytes from embedded tags, or None."""
    try:
        af = MutagenFile(fp, easy=False)
        if af is None: return None
        ext = Path(fp).suffix.lower()
        if ext == '.mp3':
            from mutagen.id3 import APIC
            for tag in af.tags.values():
                if isinstance(tag, APIC): return tag.data
        elif ext == '.flac':
            if hasattr(af, 'pictures') and af.pictures:
                return af.pictures[0].data
        elif ext in ('.m4a', '.aac'):
            covr = af.tags.get('covr')
            if covr: return bytes(covr[0])
        elif ext in ('.ogg', '.opus'):
            import base64
            from mutagen.flac import Picture
            pics = af.tags.get('metadata_block_picture', [])
            if pics:
                return Picture(base64.b64decode(pics[0])).data
    except Exception:
        pass
    return None


def _rounded_pixmap(pm: QPixmap, size: int, radius: int) -> QPixmap:
    """Scale pm to size×size with rounded corners."""
    pm = pm.scaled(size, size,
                   Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                   Qt.TransformationMode.SmoothTransformation)
    # Crop to exact square from centre
    x = (pm.width()  - size) // 2
    y = (pm.height() - size) // 2
    pm = pm.copy(x, y, size, size)
    # Apply rounded mask
    out = QPixmap(size, size); out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QBrush(pm)); p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(0, 0, size, size, radius, radius)
    p.end()
    return out


def _default_cover_disk_path(acc: str, size: int, radius: int) -> Path:
    safe = acc.lstrip('#')
    return CONFIG_PATH.parent / f'default_cover_{safe}_{size}_{radius}.jpg'


def draw_default_cover(size: int, radius: int) -> QPixmap:
    # Check disk cache first
    disk = _default_cover_disk_path(ACC, size, radius)
    if disk.exists():
        pm = QPixmap()
        if pm.load(str(disk)): return pm
    # Render
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QBrush(QColor(BG)))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(0, 0, size, size, radius, radius)
    p.setPen(QPen(QColor(ACC), 1))
    font = p.font()
    font.setPixelSize(int(size * 0.67))
    font.setFamily('Segoe UI Symbol, FreeSerif, Symbola, Arial Unicode MS')
    p.setFont(font)
    p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, '𝄞')
    p.end()
    # Save to disk cache
    try:
        disk.parent.mkdir(parents=True, exist_ok=True)
        pm.save(str(disk), 'JPEG', 90)
    except Exception:
        pass
    return pm


_COVER_DISK_DIR  = CONFIG_PATH.parent / 'covers'
_cover_fetch_on  = True   # module-level flag — updated by ControlBar
_cover_locked_set: set = set()   # filepaths that must not auto-fetch
_COVER_JPEG_QUALITY = 80


def _cover_disk_key(fp: str, size: int, radius: int) -> str:
    """Hash of filepath+mtime to detect stale covers."""
    import hashlib
    try:
        mtime = str(os.path.getmtime(fp))
    except Exception:
        mtime = '0'
    return hashlib.sha1(f'{fp}:{mtime}:{size}:{radius}'.encode()).hexdigest()


def get_cover_pixmap(fp: str, size: int = 48, radius: int = 4) -> Optional[QPixmap]:
    """Return cached rounded QPixmap (memory → disk → extract → default)."""
    key = (fp, size, radius)
    if key in _cover_cache:
        return _cover_cache[key]

    # L2: disk cache
    dkey = _cover_disk_key(fp, size, radius)
    disk_path = _COVER_DISK_DIR / f'{dkey}.jpg'
    if disk_path.exists():
        pm = QPixmap()
        if pm.load(str(disk_path)):
            _cover_cache[key] = pm
            return pm

    # L3: extract from audio file
    data = extract_cover_bytes(fp)
    if data:
        raw = QPixmap()
        if raw.loadFromData(data):
            pm = _rounded_pixmap(raw, size, radius)
            _cover_cache[key] = pm
            try:
                _COVER_DISK_DIR.mkdir(parents=True, exist_ok=True)
                pm.save(str(disk_path), 'JPEG', _COVER_JPEG_QUALITY)
            except Exception:
                pass
            return pm

    # No embedded cover — async fetch is triggered separately; return None so the caller
    # knows to show a placeholder and update the widget once the worker finishes.
    if _cover_fetch_on and fp not in _cover_locked_set:
        # Return None here; CoverFetchWorker will fill the cache and notify the UI.
        return None
    # Cover fetch disabled or path locked — show default clef icon
    default = draw_default_cover(size, radius)
    _cover_cache[key] = default
    return default



class CoverFetchWorker(QObject):
    """Background worker: fetch raw cover bytes for one track, emit to UI thread.
    QPixmap creation must happen on the main thread, so we only emit raw bytes here."""
    # Emit filepath, size, radius, raw image bytes
    cover_ready = pyqtSignal(str, int, int, bytes)

    def __init__(self, fp, artist, title, album, size, radius):
        super().__init__()
        self._fp = fp; self._artist = artist; self._title = title
        self._album = album; self._size = size; self._radius = radius

    def run(self):
        if not _cover_fetch_on or self._fp in _cover_locked_set:
            return
        data = fetch_cover_online(self._artist, self._title, self._album)
        if not data:
            return
        # Emit raw bytes — receiver builds QPixmap on the main (UI) thread
        self.cover_ready.emit(self._fp, self._size, self._radius, data)

def _clear_cover_disk_cache():
    """Wipe disk cover cache (call on rescan/new source added)."""
    global _cover_cache
    _cover_cache.clear()
    try:
        if _COVER_DISK_DIR.exists():
            for f in _COVER_DISK_DIR.glob('*.jpg'):
                f.unlink(missing_ok=True)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  Library Cover Fetch Popup
# ══════════════════════════════════════════════════════════════════════════════
class LibraryCoverFetchWorker(QObject):
    """Fetches covers for an entire track list sequentially in a worker thread.
    Emits raw bytes per track so the UI thread builds QPixmap objects."""
    progress    = pyqtSignal(int, int, str)   # current_index, total, track_name
    track_done  = pyqtSignal(str, bytes, bool) # filepath, raw_bytes, found_flag
    finished    = pyqtSignal(int, int)        # found_count, total_count

    def __init__(self, tracks: list):
        super().__init__()
        self._tracks   = list(tracks)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        # Only count tracks that actually need a fetch for the progress bar
        needs_fetch = [t for t in self._tracks
                       if extract_cover_bytes(t.filepath) is None
                       and t.filepath not in _cover_locked_set]
        total = len(needs_fetch)
        found = 0
        done  = 0
        for t in needs_fetch:
            if self._cancelled:
                break
            name = t.title or Path(t.filepath).stem
            done += 1
            self.progress.emit(done, total, name)
            data = fetch_cover_online(t.artist or '', t.title or '', t.album or '')
            if data:
                found += 1
                self.track_done.emit(t.filepath, data, True)
            else:
                self.track_done.emit(t.filepath, b'', False)
        self.finished.emit(found, total)


class CoverFetchPopup(QDialog):
    """Modal dialog that fetches covers for tracks missing a cover,
    with progress bar based only on tracks that need fetching and a scrollable log."""

    def __init__(self, tracks: list, table_pages: list, ctrlbar, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Fetch Covers')
        self.setModal(True)
        self.setMinimumWidth(520)
        self._tracks  = list(tracks)
        self._pages   = table_pages
        self._ctrlbar = ctrlbar
        self._thread  = None
        self._worker  = None
        self._found   = 0
        self._running = False
        self._needs   = [t for t in self._tracks
                         if extract_cover_bytes(t.filepath) is None
                         and t.filepath not in _cover_locked_set]

        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(20, 18, 20, 18)

        title_lbl = QLabel('Fetch Covers for Library')
        title_lbl.setStyleSheet(f'font-size:14px;font-weight:bold;color:{FG};')
        root.addWidget(title_lbl)

        info_lbl = QLabel(
            f'<b>{len(self._needs)}</b> tracks need a cover '
            f'(out of {len(self._tracks)} total — tracks with embedded covers skipped).')
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet(f'color:{FG2};font-size:12px;')
        root.addWidget(info_lbl)

        self._track_lbl = QLabel('')
        self._track_lbl.setStyleSheet(f'color:{FG};font-size:12px;')
        self._track_lbl.setWordWrap(True)
        root.addWidget(self._track_lbl)

        self._progress = QProgressBar()
        self._progress.setRange(0, max(1, len(self._needs)))
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFixedHeight(22)
        self._progress.setStyleSheet(
            f'QProgressBar{{background:{BG3};border:1px solid {B2};border-radius:4px;'
            f'color:{FG};font-size:11px;text-align:center;}}'
            f'QProgressBar::chunk{{background:{ACC};border-radius:3px;}}')
        root.addWidget(self._progress)

        self._log = QListWidget()
        self._log.setFixedHeight(140)
        self._log.setStyleSheet(
            'QListWidget{background:#000000;border:1px solid ' + B2 + ';border-radius:4px;'
            'color:' + FG2 + ';font-size:10px;outline:none;}'
            'QListWidget::item{padding:1px 6px;border:none;}'
            'QListWidget::item:selected{background:transparent;color:' + FG2 + ';}')
        # Enable touch/kinetic scrolling — critical for touch screens
        self._log.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        QScroller.grabGesture(self._log.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        _sp = QScrollerProperties()
        _sp.setScrollMetric(QScrollerProperties.ScrollMetric.DecelerationFactor,         0.35)
        _sp.setScrollMetric(QScrollerProperties.ScrollMetric.MaximumVelocity,            0.8)
        _sp.setScrollMetric(QScrollerProperties.ScrollMetric.VerticalOvershootPolicy,
                            QScrollerProperties.OvershootPolicy.OvershootAlwaysOff)
        _sp.setScrollMetric(QScrollerProperties.ScrollMetric.HorizontalOvershootPolicy,
                            QScrollerProperties.OvershootPolicy.OvershootAlwaysOff)
        QScroller.scroller(self._log.viewport()).setScrollerProperties(_sp)
        root.addWidget(self._log)

        self._result_lbl = QLabel('')
        self._result_lbl.setStyleSheet(f'color:{FG2};font-size:11px;')
        root.addWidget(self._result_lbl)

        btn_row = QHBoxLayout()
        self._btn_start  = QPushButton('Start')
        self._btn_cancel = QPushButton('Cancel')
        self._btn_cancel.setEnabled(False)
        self._btn_close  = QPushButton('Close')
        btn_row.addWidget(self._btn_start)
        btn_row.addWidget(self._btn_cancel)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_close)
        root.addLayout(btn_row)

        self._btn_start.clicked.connect(self._start)
        self._btn_cancel.clicked.connect(self._cancel)
        self._btn_close.clicked.connect(self._on_close)

    def _log_add(self, text: str, ok: bool):
        item = QListWidgetItem(text)
        item.setForeground(QColor('#55bb55') if ok else QColor('#bb3333'))
        self._log.addItem(item)
        self._log.scrollToBottom()

    def set_tracks(self, tracks: list):
        self._tracks = list(tracks)
        self._needs  = [t for t in self._tracks
                        if extract_cover_bytes(t.filepath) is None
                        and t.filepath not in _cover_locked_set]
        self._progress.setRange(0, max(1, len(self._needs)))

    def _start(self):
        if self._running: return
        self._running = True
        self._found   = 0
        self._log.clear()
        self._progress.setValue(0)
        self._result_lbl.setText('')
        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)

        worker = LibraryCoverFetchWorker(self._tracks)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.track_done.connect(self._on_track_done)
        worker.finished.connect(self._on_finished)
        worker.finished.connect(thread.quit)          # let thread finish normally
        # DO NOT connect thread.finished to deleteLater – thread is child of dialog
        self._thread = thread
        self._worker = worker
        thread.start()

    def _cancel(self):
        if self._worker: self._worker.cancel()
        self._btn_cancel.setEnabled(False)
        self._track_lbl.setText('Cancelling…')

    def _on_close(self):
        self._cancel()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
        self._thread = None   # avoid accessing deleted object
        self.accept()

    def closeEvent(self, e):
        self._cancel()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
        self._thread = None
        super().closeEvent(e)

    def _on_progress(self, current: int, total: int, name: str):
        self._progress.setValue(current)
        self._track_lbl.setText(f'[{current}/{total}]  {name}')

    def _on_track_done(self, fp: str, data: bytes, found: bool):
        name = Path(fp).stem
        if not found:
            self._log_add(f'FAIL  {name}', False)
            return
        self._log_add(f'OK    {name}', True)
        for size, radius in [(28, 4), (64, 8)]:
            key = (fp, size, radius)
            raw = QPixmap()
            if raw.loadFromData(data):
                pm = _rounded_pixmap(raw, size, radius)
                _cover_cache[key] = pm
                try:
                    dkey = _cover_disk_key(fp, size, radius)
                    disk_path = _COVER_DISK_DIR / f'{dkey}.jpg'
                    _COVER_DISK_DIR.mkdir(parents=True, exist_ok=True)
                    pm.save(str(disk_path), 'JPEG', _COVER_JPEG_QUALITY)
                except Exception:
                    pass
        threading.Thread(target=embed_cover_bytes, args=(fp, data), daemon=True).start()
        for page in self._pages:
            tracks = page.tracks if hasattr(page, 'tracks') else []
            for r, t in enumerate(tracks):
                if t.filepath == fp and r < page.table.rowCount():
                    item = page.table.item(r, C_TIT)
                    pm28 = _cover_cache.get((fp, 28, 4))
                    if item and pm28:
                        item.setIcon(QIcon(pm28))
                    break
        if self._ctrlbar and self._ctrlbar._cur_track:
            if self._ctrlbar._cur_track.filepath == fp:
                pm64 = _cover_cache.get((fp, 64, 8))
                if pm64 and self._ctrlbar._cover_lbl.isVisible():
                    self._ctrlbar._cover_lbl.setPixmap(pm64)
        self._found += 1

    def _on_finished(self, found: int, total: int):
        self._running = False
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._track_lbl.setText('Done.')
        self._result_lbl.setText(f'Found covers for {found} out of {total} tracks.')
        self._progress.setValue(total)


# ══════════════════════════════════════════════════════════════════════════════
#  Library Tag Fetch Worker + Popup
# ══════════════════════════════════════════════════════════════════════════════

class LibraryTagFetchWorker(QObject):
    """Fetches missing tags (title/artist/album) for library tracks sequentially.
    Progress is based only on tracks that are missing at least one tag."""
    progress   = pyqtSignal(int, int, str)        # current, total, track_name
    track_done = pyqtSignal(str, dict, bool)       # filepath, tags_dict, found_flag
    finished   = pyqtSignal(int, int)              # updated_count, total_needs

    def __init__(self, tracks: list):
        super().__init__()
        self._tracks    = list(tracks)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        needs = [t for t in self._tracks
                 if not (t.title.strip() and t.artist.strip() and t.album.strip())]
        total   = len(needs)
        updated = 0
        for i, t in enumerate(needs):
            if self._cancelled:
                break
            name = t.title or Path(t.filepath).stem
            self.progress.emit(i + 1, total, name)
            tags = lookup_tags_online(t.artist or '', t.title or Path(t.filepath).stem)
            if tags:
                result = {}
                if not t.title.strip()  and tags.get('title'):  result['title']  = tags['title']
                if not t.artist.strip() and tags.get('artist'): result['artist'] = tags['artist']
                if not t.album.strip()  and tags.get('album'):  result['album']  = tags['album']
                if result:
                    updated += 1
                    self.track_done.emit(t.filepath, result, True)
                else:
                    self.track_done.emit(t.filepath, {}, False)
            else:
                self.track_done.emit(t.filepath, {}, False)
        self.finished.emit(updated, total)


class TagFetchPopup(QDialog):
    """Modal dialog that looks up missing tags for library tracks.
    Progress bar counts only tracks with at least one missing tag."""

    tags_updated = pyqtSignal(str, dict)

    def __init__(self, tracks: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Fetch Missing Tags')
        self.setModal(True)
        self.setMinimumWidth(520)
        self._tracks  = list(tracks)
        self._thread  = None
        self._worker  = None
        self._updated = 0
        self._running = False
        self._needs   = [t for t in self._tracks
                         if not (t.title.strip() and t.artist.strip() and t.album.strip())]

        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(20, 18, 20, 18)

        title_lbl = QLabel('Fetch Missing Tags for Library')
        title_lbl.setStyleSheet(f'font-size:14px;font-weight:bold;color:{FG};')
        root.addWidget(title_lbl)

        info_lbl = QLabel(
            f'<b>{len(self._needs)}</b> tracks have at least one missing tag '
            f'(out of {len(self._tracks)} total — tracks with all tags are skipped).')
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet(f'color:{FG2};font-size:12px;')
        root.addWidget(info_lbl)

        self._track_lbl = QLabel('')
        self._track_lbl.setStyleSheet(f'color:{FG};font-size:12px;')
        self._track_lbl.setWordWrap(True)
        root.addWidget(self._track_lbl)

        self._progress = QProgressBar()
        self._progress.setRange(0, max(1, len(self._needs)))
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFixedHeight(22)
        self._progress.setStyleSheet(
            f'QProgressBar{{background:{BG3};border:1px solid {B2};border-radius:4px;'
            f'color:{FG};font-size:11px;text-align:center;}}'
            f'QProgressBar::chunk{{background:{ACC};border-radius:3px;}}')
        root.addWidget(self._progress)

        self._log = QListWidget()
        self._log.setFixedHeight(140)
        self._log.setStyleSheet(
            'QListWidget{background:#000000;border:1px solid ' + B2 + ';border-radius:4px;'
            'color:' + FG2 + ';font-size:10px;outline:none;}'
            'QListWidget::item{padding:1px 6px;border:none;}'
            'QListWidget::item:selected{background:transparent;color:' + FG2 + ';}')
        self._log.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        QScroller.grabGesture(self._log.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        _sp = QScrollerProperties()
        _sp.setScrollMetric(QScrollerProperties.ScrollMetric.DecelerationFactor,         0.35)
        _sp.setScrollMetric(QScrollerProperties.ScrollMetric.MaximumVelocity,            0.8)
        _sp.setScrollMetric(QScrollerProperties.ScrollMetric.VerticalOvershootPolicy,
                            QScrollerProperties.OvershootPolicy.OvershootAlwaysOff)
        _sp.setScrollMetric(QScrollerProperties.ScrollMetric.HorizontalOvershootPolicy,
                            QScrollerProperties.OvershootPolicy.OvershootAlwaysOff)
        QScroller.scroller(self._log.viewport()).setScrollerProperties(_sp)
        root.addWidget(self._log)

        self._result_lbl = QLabel('')
        self._result_lbl.setStyleSheet(f'color:{FG2};font-size:11px;')
        root.addWidget(self._result_lbl)

        btn_row = QHBoxLayout()
        self._btn_start  = QPushButton('Start')
        self._btn_cancel = QPushButton('Cancel')
        self._btn_cancel.setEnabled(False)
        self._btn_close  = QPushButton('Close')
        btn_row.addWidget(self._btn_start)
        btn_row.addWidget(self._btn_cancel)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_close)
        root.addLayout(btn_row)

        self._btn_start.clicked.connect(self._start)
        self._btn_cancel.clicked.connect(self._cancel)
        self._btn_close.clicked.connect(self._on_close)

    def _log_add(self, text: str, ok: bool):
        item = QListWidgetItem(text)
        item.setForeground(QColor('#55bb55') if ok else QColor('#bb3333'))
        self._log.addItem(item)
        self._log.scrollToBottom()

    def set_tracks(self, tracks: list):
        self._tracks = list(tracks)
        self._needs  = [t for t in self._tracks
                        if not (t.title.strip() and t.artist.strip() and t.album.strip())]
        self._progress.setRange(0, max(1, len(self._needs)))

    def _start(self):
        if self._running: return
        self._running = True
        self._updated = 0
        self._log.clear()
        self._progress.setValue(0)
        self._result_lbl.setText('')
        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)

        worker = LibraryTagFetchWorker(self._tracks)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.track_done.connect(self._on_track_done)
        worker.finished.connect(self._on_finished)
        worker.finished.connect(thread.quit)          # let thread finish normally
        # DO NOT connect thread.finished to deleteLater – thread is child of dialog
        self._thread = thread
        self._worker = worker
        thread.start()

    def _cancel(self):
        if self._worker: self._worker.cancel()
        self._btn_cancel.setEnabled(False)
        self._track_lbl.setText('Cancelling…')

    def _on_close(self):
        self._cancel()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
        self._thread = None   # avoid accessing deleted object
        self.accept()

    def closeEvent(self, e):
        self._cancel()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
        self._thread = None
        super().closeEvent(e)

    def _on_progress(self, current: int, total: int, name: str):
        self._progress.setValue(current)
        self._track_lbl.setText(f'[{current}/{total}]  {name}')

    def _on_track_done(self, fp: str, tags: dict, found: bool):
        name = Path(fp).stem
        if not found or not tags:
            self._log_add(f'FAIL  {name}', False)
            return
        filled = ', '.join(f'{k}={v}' for k, v in tags.items())
        self._log_add(f'OK    {name}  [{filled}]', True)
        def _write():
            write_tags_to_file(fp, tags)
        threading.Thread(target=_write, daemon=True).start()
        self._updated += 1
        self.tags_updated.emit(fp, tags)

    def _on_finished(self, updated: int, total: int):
        self._running = False
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._track_lbl.setText('Done.')
        self._result_lbl.setText(f'Updated tags for {updated} out of {total} tracks.')
        self._progress.setValue(total)


def scan_folder(folder: str) -> List[Track]:
    out = []
    for root, dirs, files in os.walk(folder):
        dirs.sort()
        for f in sorted(files):
            if Path(f).suffix.lower() in SUPPORTED_EXT:
                out.append(read_metadata(os.path.join(root, f)))
    out.sort(key=lambda t: t.sort_key())
    return out


def parse_m3u(path: str) -> List[Track]:
    out, base = [], os.path.dirname(path)
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith('#'): continue
                fp = line if os.path.isabs(line) else os.path.join(base, line)
                if os.path.isfile(fp) and Path(fp).suffix.lower() in SUPPORTED_EXT:
                    out.append(read_metadata(fp))
    except Exception as e:
        print(f'M3U error: {e}')
    out.sort(key=lambda t: t.sort_key())
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  Scanner thread (unchanged)
# ══════════════════════════════════════════════════════════════════════════════
class ScanThread(QThread):
    done     = pyqtSignal(list, str)
    progress = pyqtSignal(str)

    def __init__(self, path: str, is_m3u: bool = False):
        super().__init__()
        self._path, self._is_m3u = path, is_m3u

    def run(self):
        self.progress.emit(f'Scanning: {os.path.basename(self._path)} …')
        if self._is_m3u:
            tracks = parse_m3u(self._path); label = Path(self._path).stem
        else:
            tracks = scan_folder(self._path)
            label  = os.path.basename(self._path.rstrip('/\\'))
        self.done.emit(tracks, label)


# ══════════════════════════════════════════════════════════════════════════════
#  GStreamer Player with Parametric EQ (using audioiirfilter with coefficient calculation)
# ══════════════════════════════════════════════════════════════════════════════
class RepeatMode(enum.Enum):
    NONE = 0; ALL = 1; ONE = 2


def peaking_coefficients(fs, f0, gain_db, Q):
    """Return biquad coefficients (b0,b1,b2,a1,a2) for a peaking filter."""
    A = 10.0**(gain_db/40.0)
    w0 = 2.0 * math.pi * f0 / fs
    alpha = math.sin(w0) / (2.0 * Q)

    b0 = 1.0 + alpha * A
    b1 = -2.0 * math.cos(w0)
    b2 = 1.0 - alpha * A
    a0 = 1.0 + alpha / A
    a1 = -2.0 * math.cos(w0)
    a2 = 1.0 - alpha / A

    # Normalize to a0
    b0 /= a0
    b1 /= a0
    b2 /= a0
    a1 /= a0
    a2 /= a0
    # a0 is now 1

    return (b0, b1, b2, a1, a2)


class Player(QObject):
    sig_pos      = pyqtSignal(int)
    sig_dur      = pyqtSignal(int)
    sig_end      = pyqtSignal()
    sig_err      = pyqtSignal(str)
    sig_spectrum = pyqtSignal(list)

    _SPEC_INTERVAL_NS = 16_666_667   # 60 fps

    # (pre-spectrum chain, output sink)
    # 0=direct(bit-perfect) 1=audioconvert(format only, no rate) 2=+audioresample
    _CHAINS = ['', 'audioconvert', 'audioconvert ! audioresample']
    _OUTS   = ['pipewiresink', 'pipewiresink', 'pipewiresink']
    _FALLBACK = ('audioconvert ! audioresample', 'autoaudiosink')

    import re as _re
    _SPEC_RE = _re.compile(r'magnitude=\s*\(float\)\s*[<{]\s*([^}>]+)\s*[>}]')

    def __init__(self):
        super().__init__()
        self._pipe:    Optional[Gst.Element] = None
        self._spec_el: Optional[Gst.Element] = None
        self._playing: bool  = False
        self._volume:  float = 0.8
        self._viz_on:  bool  = True
        self._spec_lock   = threading.Lock()
        self._spec_latest: Optional[list] = None

        # EQ related
        self._eq_enabled = True
        self._eq_bands = []               # list of (freq, gain, Q)
        self._eq_filters = []              # list of Gst.Element for each band (size MAX_EQ_BANDS)
        self._current_fs = 48000           # default sample rate, will update from track

        self._chain, self._out = self._detect_chain()
        print(f'[Player] chain: "{self._chain or "(none)"}" → {self._out}')

        self._has_spec = Gst.ElementFactory.find('spectrum') is not None
        print(f'[Player] spectrum: {"OK" if self._has_spec else "not found"}')

        self._glib_loop = GLib.MainLoop()
        threading.Thread(target=self._glib_loop.run, daemon=True, name='glib').start()

        self._pos_timer  = QTimer(self)
        self._pos_timer.setInterval(250)
        self._pos_timer.timeout.connect(self._tick_pos)

        self._spec_timer = QTimer(self)
        self._spec_timer.setInterval(16)
        self._spec_timer.timeout.connect(self._tick_spec)
        if self._viz_on and self._has_spec:
            self._spec_timer.start()

    @staticmethod
    def _detect_chain():
        for chain, out in zip(Player._CHAINS, Player._OUTS):
            desc = f'{chain} ! {out}' if chain else out
            try:
                b = Gst.parse_bin_from_description(desc, True)
                b.set_state(Gst.State.NULL); return chain, out
            except Exception:
                continue
        return Player._FALLBACK

    def load(self, filepath: str):
        self._destroy()
        with self._spec_lock: self._spec_latest = None
        self._pipe = Gst.ElementFactory.make('playbin', None)
        if not self._pipe:
            self.sig_err.emit('playbin unavailable'); return
        self._pipe.set_property('uri', Path(filepath).as_uri())
        self._pipe.set_property('volume', self._volume)

        # Get sample rate from track metadata
        track = read_metadata(filepath)
        self._current_fs = track.sample_rate if track.sample_rate > 0 else 48000

        # Build sink bin with EQ and spectrum
        sink_bin, eq_filters = self._make_sink_bin()
        if sink_bin:
            self._pipe.set_property('audio-sink', sink_bin)
            self._eq_filters = eq_filters
            if self._has_spec:
                self._spec_el = sink_bin.get_by_name('bp_spec')
                if self._spec_el:
                    self._spec_el.set_property('post-messages', self._viz_on)
            # Apply current EQ settings
            self._apply_eq_to_filters()

        bus = self._pipe.get_bus()
        bus.add_signal_watch(); bus.connect('message', self._on_msg)
        self._pipe.set_state(Gst.State.PLAYING)
        self._playing = True; self._pos_timer.start()

    def play_pause(self):
        if not self._pipe: return
        if self._playing:
            self._pipe.set_state(Gst.State.PAUSED)
            self._playing = False; self._pos_timer.stop()
        else:
            self._pipe.set_state(Gst.State.PLAYING)
            self._playing = True; self._pos_timer.start()

    def stop(self): self._destroy()

    def seek(self, ms: int):
        if not self._pipe:
            return
        # Only seek when the pipeline is in PAUSED or PLAYING state to avoid hangs/crashes
        ok, state, _pending = self._pipe.get_state(0)
        if state not in (Gst.State.PAUSED, Gst.State.PLAYING):
            # Defer seek until pipeline reaches a seekable state
            QTimer.singleShot(120, lambda: self.seek(ms))
            return
        try:
            self._pipe.seek_simple(
                Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                max(0, ms) * Gst.MSECOND)
            if self._playing:
                self._pipe.set_state(Gst.State.PLAYING)
        except Exception as ex:
            print(f'[Player] seek error: {ex}')

    def set_volume(self, v: float):
        self._volume = max(0.0, min(1.0, v))
        if self._pipe: self._pipe.set_property('volume', self._volume)

    def set_viz_active(self, on: bool):
        self._viz_on = on
        if self._spec_el: self._spec_el.set_property('post-messages', on)
        if on: self._spec_timer.start()
        else:
            self._spec_timer.stop()
            with self._spec_lock: self._spec_latest = None

    # --- EQ methods ---
    def set_eq_enabled(self, enabled: bool):
        if self._eq_enabled == enabled:
            return
        self._eq_enabled = enabled
        # Rebuild the pipeline so EQ filters are added/removed (bit-perfect when off)
        if self._pipe:
            self._reload_current()
        else:
            self._apply_eq_to_filters()

    def _reload_current(self):
        """Reload the currently-playing track to rebuild the pipeline."""
        if not self._pipe:
            return
        # Query current position before destroying
        ok, pos = self._pipe.query_position(Gst.Format.TIME)
        pos_ms = pos // Gst.MSECOND if ok else 0
        was_playing = self._playing
        # Get URI
        uri = self._pipe.get_property('uri')
        if not uri:
            return
        # Rebuild
        self._destroy()
        import urllib.parse
        filepath = urllib.parse.unquote(uri.replace('file://', ''))
        self.load(filepath)
        # Seek to saved position
        if pos_ms > 0:
            QTimer.singleShot(200, lambda: self.seek(pos_ms))
        if not was_playing:
            QTimer.singleShot(250, self.play_pause)

    def set_eq_bands(self, bands: List[tuple]):
        """bands: list of (freq, gain, Q)"""
        self._eq_bands = bands[:MAX_EQ_BANDS]  # truncate if too many
        self._apply_eq_to_filters()

    def _apply_eq_to_filters(self):
        """Update the properties of existing EQ filter elements (from GLib thread)."""
        if not self._eq_filters:
            return
        GLib.idle_add(self._apply_eq_to_filters_glib)
        self._apply_eq_to_filters_glib()  # also apply immediately

    def _apply_eq_to_filters_glib(self):
        if not self._eq_filters:
            return False
        fs = self._current_fs
        for i, filt in enumerate(self._eq_filters):
            if i < len(self._eq_bands) and self._eq_enabled:
                f0, gain, q = self._eq_bands[i]
                if gain == 0.0:
                    # Bypass: set coefficients for unit gain
                    b = [1.0, 0.0, 0.0]
                    a = [1.0, 0.0, 0.0]
                else:
                    try:
                        b0, b1, b2, a1, a2 = peaking_coefficients(fs, f0, gain, q)
                        b = [b0, b1, b2]
                        a = [1.0, a1, a2]
                    except Exception:
                        b = [1.0, 0.0, 0.0]
                        a = [1.0, 0.0, 0.0]
            else:
                # Bypass
                b = [1.0, 0.0, 0.0]
                a = [1.0, 0.0, 0.0]
            # Set coefficients using Python lists (GStreamer will convert)
            filt.set_property('b', b)
            filt.set_property('a', a)
        return False

    def _make_sink_bin(self):
        """Create a bin containing EQ (if any), spectrum (if available), and sink.
           Returns (bin, list_of_eq_filter_elements)."""
        elements = []
        # Start with EQ bin if we have filters
        eq_bin, eq_filters = self._create_eq_bin()
        if eq_bin:
            elements.append(eq_bin)

        # Then spectrum if available
        if self._has_spec:
            spec_desc = (f'spectrum name=bp_spec bands={VIZ_BANDS} '
                         f'threshold={int(MIN_DB)} interval={self._SPEC_INTERVAL_NS} '
                         f'post-messages=false message-magnitude=true message-phase=false')
            try:
                spec = Gst.parse_bin_from_description(spec_desc, True)
                elements.append(spec)
            except Exception as e:
                print(f'[Player] spectrum creation failed: {e}')

        # Then the output sink
        try:
            sink = Gst.parse_bin_from_description(self._out, True)
            elements.append(sink)
        except Exception as e:
            print(f'[Player] sink creation failed: {e}')
            return None, []

        # Now chain them together in a single bin
        bin = Gst.Bin.new()
        prev_pad = None
        for el in elements:
            bin.add(el)
            if prev_pad:
                # Link previous element's src pad to this element's sink pad
                src_pad = prev_pad.get_parent().get_static_pad('src')
                sink_pad = el.get_static_pad('sink')
                if src_pad and sink_pad:
                    src_pad.link(sink_pad)
                else:
                    print('[Player] linking error')
                    return None, []
            prev_pad = el.get_static_pad('src') if el != elements[-1] else None

        # Add ghost pad for sink
        ghost_pad = Gst.GhostPad.new('sink', elements[0].get_static_pad('sink'))
        if not ghost_pad:
            print('[Player] ghost pad failed')
            return None, []
        bin.add_pad(ghost_pad)

        return bin, eq_filters

    def _create_eq_bin(self):
        """Create a bin containing MAX_EQ_BANDS audioiirfilter in series.
           Returns (bin, list_of_filters). Returns (None, []) when EQ is disabled
           so the pipeline remains bit-perfect (no float conversion forced)."""
        if MAX_EQ_BANDS == 0 or not self._eq_enabled:
            return None, []
        bin = Gst.Bin.new('eq_bin')
        filters = []
        prev = None
        for i in range(MAX_EQ_BANDS):
            filt = Gst.ElementFactory.make('audioiirfilter', f'eq_filter_{i}')
            if not filt:
                print(f'[Player] could not create audioiirfilter')
                return None, []
            # Default settings (bypassed) using Python lists
            filt.set_property('b', [1.0, 0.0, 0.0])
            filt.set_property('a', [1.0, 0.0, 0.0])
            bin.add(filt)
            filters.append(filt)
            if prev:
                # Link previous filter's src to this filter's sink
                prev_src = prev.get_static_pad('src')
                this_sink = filt.get_static_pad('sink')
                prev_src.link(this_sink)
            prev = filt

        # Add ghost pads
        if filters:
            sink_pad = filters[0].get_static_pad('sink')
            src_pad = filters[-1].get_static_pad('src')
            if sink_pad:
                ghost_sink = Gst.GhostPad.new('sink', sink_pad)
                bin.add_pad(ghost_sink)
            if src_pad:
                ghost_src = Gst.GhostPad.new('src', src_pad)
                bin.add_pad(ghost_src)
        return bin, filters

    @property
    def playing(self)     -> bool: return self._playing
    @property
    def has_pipe(self)    -> bool: return self._pipe is not None
    @property
    def has_spectrum(self)-> bool: return self._has_spec
    @property
    def glib_loop(self)         : return self._glib_loop

    def position_ms(self) -> int:
        if self._pipe:
            ok, p = self._pipe.query_position(Gst.Format.TIME)
            return p // Gst.MSECOND if ok else 0
        return 0

    def duration_ms(self) -> int:
        if self._pipe:
            ok, d = self._pipe.query_duration(Gst.Format.TIME)
            return d // Gst.MSECOND if ok else 0
        return 0

    def _destroy(self):
        if self._pipe:
            self._pipe.set_state(Gst.State.NULL); self._pipe = None
        self._spec_el = None; self._playing = False; self._pos_timer.stop()
        self._eq_filters = []

    def _tick_pos(self):
        self.sig_pos.emit(self.position_ms())
        d = self.duration_ms()
        if d > 0: self.sig_dur.emit(d)

    def _tick_spec(self):
        with self._spec_lock:
            data = self._spec_latest; self._spec_latest = None
        if data is not None: self.sig_spectrum.emit(data)

    def _on_msg(self, _bus, msg):
        if msg.type == Gst.MessageType.EOS:
            self._playing = False; self._pos_timer.stop(); self.sig_end.emit()
        elif msg.type == Gst.MessageType.ERROR:
            err, _ = msg.parse_error(); self._destroy(); self.sig_err.emit(str(err))
        elif msg.type == Gst.MessageType.ELEMENT:
            if not self._viz_on: return
            s = msg.get_structure()
            if s and s.get_name() == 'spectrum': self._parse_spectrum(s)

    def _parse_spectrum(self, s):
        try:
            m = self._SPEC_RE.search(s.to_string())
            if m:
                data = [float(x.strip()) for x in m.group(1).split(',') if x.strip()]
                with self._spec_lock: self._spec_latest = data[:VIZ_BANDS]
                return
        except Exception: pass
        try:
            for i in range(s.n_fields()):
                if s.nth_field_name(i) == 'magnitude':
                    val = s.get_value('magnitude')
                    if val is not None and hasattr(val, '__len__'):
                        with self._spec_lock:
                            self._spec_latest = [float(val[j])
                                                 for j in range(min(VIZ_BANDS, len(val)))]
                    break
        except Exception: pass


# ══════════════════════════════════════════════════════════════════════════════
#  MPRIS2 D-Bus server (unchanged)
# ══════════════════════════════════════════════════════════════════════════════
_MPRIS_XML = """
<node>
  <interface name="org.mpris.MediaPlayer2">
    <method name="Raise"/> <method name="Quit"/>
    <property name="CanQuit"             type="b"  access="read"/>
    <property name="CanRaise"            type="b"  access="read"/>
    <property name="HasTrackList"        type="b"  access="read"/>
    <property name="Identity"            type="s"  access="read"/>
    <property name="DesktopEntry"        type="s"  access="read"/>
    <property name="SupportedUriSchemes" type="as" access="read"/>
    <property name="SupportedMimeTypes"  type="as" access="read"/>
  </interface>
  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="Next"/>  <method name="Previous"/>
    <method name="Pause"/> <method name="PlayPause"/>
    <method name="Stop"/>  <method name="Play"/>
    <method name="Seek">
      <arg name="Offset"   type="x" direction="in"/>
    </method>
    <method name="SetPosition">
      <arg name="TrackId"  type="o" direction="in"/>
      <arg name="Position" type="x" direction="in"/>
    </method>
    <method name="OpenUri"><arg name="Uri" type="s" direction="in"/></method>
    <signal name="Seeked"><arg name="Position" type="x"/></signal>
    <property name="PlaybackStatus" type="s"     access="read"/>
    <property name="LoopStatus"     type="s"     access="readwrite"/>
    <property name="Rate"           type="d"     access="readwrite"/>
    <property name="Shuffle"        type="b"     access="readwrite"/>
    <property name="Metadata"       type="a{sv}" access="read"/>
    <property name="Volume"         type="d"     access="readwrite"/>
    <property name="Position"       type="x"     access="read"/>
    <property name="MinimumRate"    type="d"     access="read"/>
    <property name="MaximumRate"    type="d"     access="read"/>
    <property name="CanGoNext"      type="b"     access="read"/>
    <property name="CanGoPrevious"  type="b"     access="read"/>
    <property name="CanPlay"        type="b"     access="read"/>
    <property name="CanPause"       type="b"     access="read"/>
    <property name="CanSeek"        type="b"     access="read"/>
    <property name="CanControl"     type="b"     access="read"/>
  </interface>
</node>
"""


class MprisServer(QObject):
    def __init__(self, player: Player, win: 'MainWindow', parent=None):
        super().__init__(parent)
        self._player = player; self._win = win
        self._conn: Optional[Gio.DBusConnection] = None
        self._reg_ids: list = []
        self._cur_track: Optional[Track] = None
        self._track_serial = 0
        GLib.idle_add(self._setup)

    def _setup(self):
        try:
            self._conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            node = Gio.DBusNodeInfo.new_for_xml(_MPRIS_XML)
            for iface in node.interfaces:
                rid = self._conn.register_object('/org/mpris/MediaPlayer2', iface,
                    self._handle_method, self._handle_get, self._handle_set)
                self._reg_ids.append(rid)
            Gio.bus_own_name_on_connection(self._conn,
                'org.mpris.MediaPlayer2.blackplayer',
                Gio.BusNameOwnerFlags.NONE, None, None)
        except Exception as e:
            print(f'[MPRIS] {e}')
        return False

    def _handle_method(self, conn, sender, obj, iface, method, params, inv):
        inv.return_value(None)
        QTimer.singleShot(0, lambda m=method, p=params: self._dispatch(m, p))

    def _dispatch(self, method, params):
        w = self._win; p = self._player
        if   method == 'PlayPause': w._play_pause()
        elif method == 'Play':
            if not p.playing: w._play_pause()
        elif method == 'Pause':
            if p.playing: w._play_pause()
        elif method == 'Stop':   p.stop(); w._ctrlbar.set_play_icon(False); self.notify_status()
        elif method == 'Next':   w._next_track()
        elif method == 'Previous': w._prev_track()
        elif method == 'Raise':  w.raise_(); w.activateWindow()
        elif method == 'Quit':   w.close()
        elif method == 'Seek':   p.seek(max(0, p.position_ms()+params[0]//1000))
        elif method == 'SetPosition': p.seek(params[1]//1000)

    def _handle_get(self, conn, sender, obj, iface, prop):
        if iface == 'org.mpris.MediaPlayer2':
            d = {'CanQuit': GLib.Variant('b', True), 'CanRaise': GLib.Variant('b', True),
                 'HasTrackList': GLib.Variant('b', False),
                 'Identity': GLib.Variant('s', 'BlackPlayer'),
                 'DesktopEntry': GLib.Variant('s', 'blackplayer'),
                 'SupportedUriSchemes': GLib.Variant('as', ['file']),
                 'SupportedMimeTypes': GLib.Variant('as',
                    ['audio/mpeg','audio/flac','audio/ogg','audio/opus','audio/mp4'])}
            return d.get(prop)
        if iface == 'org.mpris.MediaPlayer2.Player':
            return self._pp(prop)
        return None

    def _pp(self, prop):
        p = self._player; w = self._win
        if prop == 'PlaybackStatus':
            return GLib.Variant('s',
                'Playing' if p.playing else 'Paused' if p.has_pipe else 'Stopped')
        if prop == 'LoopStatus':
            m = w._ctrlbar.btn_rep.current_mode()
            return GLib.Variant('s', 'Track' if m==RepeatMode.ONE
                                else 'Playlist' if m==RepeatMode.ALL else 'None')
        if prop == 'Rate':        return GLib.Variant('d', 1.0)
        if prop == 'Shuffle':     return GLib.Variant('b', w._shuffle)
        if prop == 'Metadata':    return self._meta()
        if prop == 'Volume':      return GLib.Variant('d', p._volume)
        if prop == 'Position':    return GLib.Variant('x', p.position_ms()*1000)
        if prop in ('MinimumRate','MaximumRate'): return GLib.Variant('d', 1.0)
        if prop in ('CanGoNext','CanGoPrevious','CanPlay','CanPause',
                    'CanSeek','CanControl'):    return GLib.Variant('b', True)
        return None

    def _meta(self):
        tid = f'/org/blackplayer/track/{self._track_serial}'; t = self._cur_track
        if t is None:
            return GLib.Variant('a{sv}', {'mpris:trackid': GLib.Variant('o', tid)})
        return GLib.Variant('a{sv}', {
            'mpris:trackid': GLib.Variant('o', tid),
            'xesam:title':   GLib.Variant('s', t.title or ''),
            'xesam:artist':  GLib.Variant('as', [t.artist] if t.artist else []),
            'xesam:album':   GLib.Variant('s', t.album or ''),
            'mpris:length':  GLib.Variant('x', int(t.duration*1_000_000)),
            'xesam:url':     GLib.Variant('s', Path(t.filepath).as_uri()),
        })

    def _handle_set(self, conn, sender, obj, iface, prop, value):
        if iface != 'org.mpris.MediaPlayer2.Player': return
        if prop == 'Volume':
            QTimer.singleShot(0, lambda v=value.unpack(): self._player.set_volume(v))
        elif prop == 'Shuffle':
            QTimer.singleShot(0, lambda v=value.unpack(): setattr(self._win, '_shuffle', v))

    def notify_track(self, track: Optional[Track]):
        self._cur_track = track; self._track_serial += 1
        GLib.idle_add(self._emit, ['Metadata', 'PlaybackStatus'])

    def notify_status(self):
        GLib.idle_add(self._emit, ['PlaybackStatus'])

    def _emit(self, props):
        if not self._conn: return False
        try:
            changed = {p: v for p in props if (v := self._pp(p)) is not None}
            if changed:
                self._conn.emit_signal(None, '/org/mpris/MediaPlayer2',
                    'org.freedesktop.DBus.Properties', 'PropertiesChanged',
                    GLib.Variant('(sa{sv}as)', ('org.mpris.MediaPlayer2.Player', changed, [])))
        except Exception: pass
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  Seek slider (unchanged)
# ══════════════════════════════════════════════════════════════════════════════
class SeekSlider(QSlider):
    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setObjectName('seek'); self.setRange(0, 1000)
        self.setMinimumHeight(26)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)
        self._pressed = False
        self.setStyleSheet(f"""
            QSlider           {{ background: transparent; }}
            QSlider::groove:horizontal {{
                background: rgba(80,80,80,160); height: 4px; border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{ background: {ACC}; border-radius: 2px; }}
            QSlider::handle:horizontal {{
                background: {BG4}; border: 2px solid {ACC};
                width: 18px; height: 18px; border-radius: 9px; margin: -7px 0;
            }}
            QSlider::handle:horizontal:hover {{
                background: {BG4}; border-color: {ACCH};
                width: 22px; height: 22px; border-radius: 11px; margin: -9px 0;
            }}
        """)

    def _val_at(self, x: float) -> int:
        return QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(), int(max(0.0, x)), self.width())

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.sliderPressed.emit()
            val = self._val_at(e.position().x())
            self.setValue(val)
            self.sliderMoved.emit(val)
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._pressed:
            val = self._val_at(e.position().x())
            self.setValue(val)
            self.sliderMoved.emit(val)
            e.accept()
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            val = self._val_at(e.position().x())
            self.setValue(val)
            self.sliderReleased.emit()
            e.accept()
        else:
            super().mouseReleaseEvent(e)

    def update_accent(self, acc: str, acch: str):
        self.setStyleSheet(f"""
            QSlider           {{ background: transparent; }}
            QSlider::groove:horizontal {{
                background: rgba(80,80,80,160); height: 4px; border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{ background: {acc}; border-radius: 2px; }}
            QSlider::handle:horizontal {{
                background: {BG4}; border: 2px solid {acc};
                width: 18px; height: 18px; border-radius: 9px; margin: -7px 0;
            }}
            QSlider::handle:horizontal:hover {{
                background: {BG4}; border-color: {acch};
                width: 22px; height: 22px; border-radius: 11px; margin: -9px 0;
            }}
        """)

    def event(self, e: QEvent) -> bool:
        t = e.type()
        if t == QEvent.Type.TouchBegin:
            e.accept(); pts = e.points()
            if pts:
                self._pressed = True
                self.sliderPressed.emit()
                val = self._val_at(pts[0].position().x())
                self.setValue(val); self.sliderMoved.emit(val)
            return True
        if t == QEvent.Type.TouchUpdate:
            e.accept(); pts = e.points()
            if pts and self._pressed:
                val = self._val_at(pts[0].position().x())
                self.setValue(val); self.sliderMoved.emit(val)
            return True
        if t == QEvent.Type.TouchEnd:
            e.accept(); pts = e.points()
            if pts and self._pressed:
                val = self._val_at(pts[0].position().x())
                self.setValue(val)
            self._pressed = False
            self.sliderReleased.emit()
            return True
        return super().event(e)


# ══════════════════════════════════════════════════════════════════════════════
#  Long-press filter (unchanged)
# ══════════════════════════════════════════════════════════════════════════════
class LongPressFilter(QObject):
    triggered = pyqtSignal(int, QPoint)
    DELAY_MS = 550; DRIFT_PX = 10

    def __init__(self, table):
        super().__init__(table)
        self._table = table; self._row = -1; self._gpos = QPoint(); self._start = QPoint()
        self._timer = QTimer(self); self._timer.setSingleShot(True)
        self._timer.setInterval(self.DELAY_MS); self._timer.timeout.connect(self._fire)
        # Touch double-tap detection
        self._last_tap_row = -1; self._last_tap_ms = 0

    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            item = self._table.itemAt(event.pos())
            self._row = item.row() if item else -1
            if self._row >= 0:
                self._start = QPoint(event.pos())
                self._gpos  = self._table.viewport().mapToGlobal(event.pos())
                self._timer.start()
        elif t == QEvent.Type.MouseMove:
            if self._timer.isActive():
                d = event.pos() - self._start
                if abs(d.x())+abs(d.y()) > self.DRIFT_PX: self._timer.stop(); self._row = -1
        elif t in (QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick):
            self._timer.stop()
        # Touch tap → synthesise double-click via rapid second tap on same row
        elif t == QEvent.Type.TouchEnd:
            pts = event.points()
            if pts:
                pos = pts[0].position().toPoint()
                item = self._table.itemAt(pos)
                row = item.row() if item else -1
                if row >= 0:
                    now = QDateTime.currentMSecsSinceEpoch()
                    if row == self._last_tap_row and (now - self._last_tap_ms) < 400:
                        self._table.row_activated.emit(row)
                        self._last_tap_row = -1
                    else:
                        self._last_tap_row = row; self._last_tap_ms = now
        return False

    def _fire(self):
        if self._row >= 0: self.triggered.emit(self._row, self._gpos); self._row = -1


# ══════════════════════════════════════════════════════════════════════════════
#  Track table (unchanged)
# ══════════════════════════════════════════════════════════════════════════════
COLS  = ['Length', 'Title', 'Artist', 'Album', 'Sample Rate', 'Bit Depth', 'Type']
C_LEN=0; C_TIT=1; C_ART=2; C_ALB=3; C_SR=4; C_BD=5; C_TYP=6


class TrackTable(QTableWidget):
    row_activated = pyqtSignal(int)
    ctx_requested = pyqtSignal(int, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(COLS)); self.setHorizontalHeaderLabels(COLS)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False); self.setAlternatingRowColors(False); self.setWordWrap(False)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda pos: self._emit_ctx(pos))
        self.setIconSize(QSize(28, 28))
        hh = self.horizontalHeader()
        for col, mode in [(C_LEN, QHeaderView.ResizeMode.Fixed),
                          (C_TIT, QHeaderView.ResizeMode.Stretch),
                          (C_ART, QHeaderView.ResizeMode.Stretch),
                          (C_ALB, QHeaderView.ResizeMode.Stretch),
                          (C_SR,  QHeaderView.ResizeMode.Fixed),
                          (C_BD,  QHeaderView.ResizeMode.Fixed),
                          (C_TYP, QHeaderView.ResizeMode.Fixed)]:
            hh.setSectionResizeMode(col, mode)
        self.setColumnWidth(C_LEN, 72); self.setColumnWidth(C_SR, 92)
        self.setColumnWidth(C_BD, 82);  self.setColumnWidth(C_TYP, 62)
        self.verticalHeader().setDefaultSectionSize(44)
        QScroller.grabGesture(self.viewport(), QScroller.ScrollerGestureType.TouchGesture)
        sp = QScrollerProperties()
        sp.setScrollMetric(QScrollerProperties.ScrollMetric.DecelerationFactor,           0.35)
        sp.setScrollMetric(QScrollerProperties.ScrollMetric.MaximumVelocity,              0.8)
        sp.setScrollMetric(QScrollerProperties.ScrollMetric.AcceleratingFlickMaximumTime, 0.15)
        sp.setScrollMetric(QScrollerProperties.ScrollMetric.DragStartDistance,            0.005)
        sp.setScrollMetric(QScrollerProperties.ScrollMetric.VerticalOvershootPolicy,
                           QScrollerProperties.OvershootPolicy.OvershootAlwaysOff)
        sp.setScrollMetric(QScrollerProperties.ScrollMetric.HorizontalOvershootPolicy,
                           QScrollerProperties.OvershootPolicy.OvershootAlwaysOff)
        QScroller.scroller(self.viewport()).setScrollerProperties(sp)
        self._lp = LongPressFilter(self); self.viewport().installEventFilter(self._lp)
        self._lp.triggered.connect(self.ctx_requested)
        self.doubleClicked.connect(lambda idx: self.row_activated.emit(idx.row()))
        # Manual sort — we keep _tracks in sync with visual order so row index is always correct
        self._sort_col = -1; self._sort_asc = True
        self.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self._covers_on = True

    def _emit_ctx(self, pos):
        item = self.itemAt(pos)
        if item: self.ctx_requested.emit(item.row(), self.viewport().mapToGlobal(pos))

    def populate(self, tracks, playing_idx=-1):
        self.setSortingEnabled(False)
        self.setRowCount(0); self.setRowCount(len(tracks))
        self._tracks_ref = tracks  # keep ref so cover_ready can find the row
        for r, t in enumerate(tracks):
            self._fill_row(r, t)
        self.set_playing_row(playing_idx)
        # Never re-enable Qt's built-in sorting; we sort _tracks manually

    def _on_header_clicked(self, col: int):
        """Sort the underlying PlaylistPage._tracks via the page reference."""
        # Find the PlaylistPage parent
        page = self.parent()
        while page and not isinstance(page, PlaylistPage):
            page = page.parent()
        if page is None:
            return
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col; self._sort_asc = True
        # Key functions per column
        def sort_key(t):
            if col == C_LEN: return t.duration
            if col == C_TIT: return t.title.lower()
            if col == C_ART: return t.artist.lower()
            if col == C_ALB: return t.album.lower()
            if col == C_SR:  return t.sample_rate
            if col == C_BD:  return t.bit_depth
            if col == C_TYP: return t.file_type.lower()
            return ''
        # Remember currently playing track so we can update its index
        cur_fp = None
        if 0 <= page.playing_idx < len(page.tracks):
            cur_fp = page.tracks[page.playing_idx].filepath
        sorted_tracks = sorted(page.tracks, key=sort_key, reverse=not self._sort_asc)
        new_playing = next((i for i, t in enumerate(sorted_tracks) if t.filepath == cur_fp), -1)
        page.set_tracks(sorted_tracks, new_playing)
        # Update header indicator
        hh = self.horizontalHeader()
        hh.setSortIndicatorShown(True)
        hh.setSortIndicator(col, Qt.SortOrder.AscendingOrder if self._sort_asc
                                  else Qt.SortOrder.DescendingOrder)

    def _fill_row(self, row, t):
        for col, txt in enumerate([t.dur_str(), t.title, t.artist, t.album,
                                    t.sr_str(), t.bd_str(), t.file_type]):
            item = QTableWidgetItem(txt)
            if col == C_TIT and self._covers_on:
                pm = get_cover_pixmap(t.filepath, 28, 4)
                # pm is None when cover fetch is enabled but no embedded cover yet;
                # show the default clef placeholder in that case.
                if pm is None:
                    pm = draw_default_cover(28, 4)
                item.setIcon(QIcon(pm))
            align = Qt.AlignmentFlag.AlignVCenter | (
                Qt.AlignmentFlag.AlignRight if col in (C_LEN, C_SR, C_BD, C_TYP)
                else Qt.AlignmentFlag.AlignLeft)
            item.setTextAlignment(align); self.setItem(row, col, item)

    def set_covers_on(self, on: bool, tracks: list):
        self._covers_on = on
        self._tracks_ref = tracks  # keep ref for cover_ready slot
        self.setIconSize(QSize(28, 28) if on else QSize(0, 0))
        # Process in small chunks so the event loop stays responsive
        CHUNK = 80
        total = min(self.rowCount(), len(tracks))

        def _process_chunk(start: int):
            end = min(start + CHUNK, total)
            for r in range(start, end):
                t = tracks[r]
                item = self.item(r, C_TIT)
                if item:
                    if on:
                        pm = get_cover_pixmap(t.filepath, 28, 4)
                        item.setIcon(QIcon(pm if pm is not None else draw_default_cover(28, 4)))
                    else:
                        item.setIcon(QIcon())
            if end < total:
                QTimer.singleShot(0, lambda s=end: _process_chunk(s))

        if total > 0:
            _process_chunk(0)



    def set_playing_row(self, row):
        for r in range(self.rowCount()):
            pl = (r == row)
            for c in range(self.columnCount()):
                item = self.item(r, c)
                if not item: continue
                item.setForeground(QColor(ACC if pl else FG))
                f = item.font(); f.setBold(pl); item.setFont(f)

    def filter(self, query, tracks):
        q = query.lower().strip()
        for r in range(self.rowCount()):
            if r >= len(tracks): self.setRowHidden(r, True); continue
            t = tracks[r]
            ok = (not q or q in t.title.lower() or q in t.artist.lower()
                  or q in t.album.lower() or q in Path(t.filepath).name.lower())
            self.setRowHidden(r, not ok)


# ══════════════════════════════════════════════════════════════════════════════
#  Playlist page (unchanged)
# ══════════════════════════════════════════════════════════════════════════════
class PlaylistPage(QWidget):
    play_track    = pyqtSignal(object, int)
    ctx_requested = pyqtSignal(object, int, QPoint)

    def __init__(self, tracks=None, label='', parent=None):
        super().__init__(parent)
        self._tracks = list(tracks or []); self._label = label; self._playing_idx = -1
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
        self.table = TrackTable(self); lay.addWidget(self.table)
        self.table.row_activated.connect(lambda r: self.play_track.emit(self, r))
        self.table.ctx_requested.connect(lambda r, pos: self.ctx_requested.emit(self, r, pos))

    @property
    def tracks(self):      return self._tracks
    @property
    def label(self):       return self._label
    @property
    def playing_idx(self): return self._playing_idx

    def set_tracks(self, tracks, playing_idx=-1):
        self._tracks = list(tracks); self._playing_idx = playing_idx
        self.table.populate(self._tracks, playing_idx)

    def set_playing(self, idx):
        self._playing_idx = idx; self.table.set_playing_row(idx)

    def set_covers_on(self, on: bool):
        self.table.set_covers_on(on, self._tracks)

    def apply_filter(self, query): self.table.filter(query, self._tracks)


# ══════════════════════════════════════════════════════════════════════════════
#  Sidebar (unchanged)
# ══════════════════════════════════════════════════════════════════════════════
class _PlaylistRowWidget(QWidget):
    """A sidebar playlist row: [X btn] [label] — delete button on the far left."""
    delete_clicked = pyqtSignal()
    select_clicked = pyqtSignal()

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 10, 0)
        lay.setSpacing(4)

        # Accent-coloured X button on the far left
        self._del_btn = QPushButton('✕')
        self._del_btn.setFixedSize(22, 22)
        self._del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_btn.setStyleSheet(
            f'QPushButton {{ background:transparent; border:none; color:{ACC};'
            f' font-size:12px; font-weight:bold; border-radius:11px; padding:0; }}'
            f'QPushButton:hover {{ background:{BG4}; color:{ACCH}; }}'
            f'QPushButton:pressed {{ background:{BG3}; }}')
        self._del_btn.setToolTip('Remove playlist')
        self._del_btn.clicked.connect(self.delete_clicked)

        self._lbl = QLabel(label)
        self._lbl.setStyleSheet(f'color:{FG}; font-size:12px; background:transparent;')

        lay.addWidget(self._del_btn)
        lay.addWidget(self._lbl, 1)

    def set_selected(self, on: bool):
        c = ACC if on else FG
        self._lbl.setStyleSheet(f'color:{c}; font-size:12px; font-weight:{"bold" if on else "normal"}; background:transparent;')

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.select_clicked.emit()
        super().mousePressEvent(e)

    def update_accent(self):
        self._del_btn.setStyleSheet(
            f'QPushButton {{ background:transparent; border:none; color:{ACC};'
            f' font-size:12px; font-weight:bold; border-radius:11px; padding:0; }}'
            f'QPushButton:hover {{ background:{BG4}; color:{ACCH}; }}'
            f'QPushButton:pressed {{ background:{BG3}; }}')


class Sidebar(QWidget):
    add_folder_req    = pyqtSignal()
    add_m3u_req       = pyqtSignal()
    new_playlist_req  = pyqtSignal()
    refresh_req       = pyqtSignal()
    remove_req        = pyqtSignal(int)
    source_selected   = pyqtSignal(int)
    search_changed    = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('sidebar'); self.setFixedWidth(230)
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        logo = QLabel('BLACK PLAYER')
        logo.setObjectName('logo_lbl')
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet(f'color:{ACC}; font-size:15px; font-weight:900;'
                           f' letter-spacing:5px; padding:16px 0 10px 0; background:{BG2};')
        root.addWidget(logo)

        sf = QWidget(); sf.setStyleSheet(f'background:{BG2};')
        sfl = QHBoxLayout(sf); sfl.setContentsMargins(10,4,10,10)
        self._search = QLineEdit()
        self._search.setPlaceholderText('🔍  Search…'); self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self.search_changed)
        sfl.addWidget(self._search); root.addWidget(sf)

        div = QFrame(); div.setFixedHeight(1); div.setStyleSheet(f'background:{BORD};')
        root.addWidget(div)

        lbl1 = QLabel('LIBRARY'); lbl1.setObjectName('sect_lbl'); root.addWidget(lbl1)

        self._lib_btn = QPushButton('  All Tracks')
        self._lib_btn.setStyleSheet(
            f'QPushButton {{ background:{BG3}; color:{ACC}; border:none;'
            f' border-left:3px solid {ACC}; border-radius:6px; text-align:left;'
            f' padding:13px 16px; font-weight:bold; }}'
            f'QPushButton:hover {{ background:{BG4}; }}')
        self._lib_btn.clicked.connect(lambda: self.source_selected.emit(-1))
        root.addWidget(self._lib_btn)

        lbl2 = QLabel("PLAYLISTS"); lbl2.setObjectName('sect_lbl'); root.addWidget(lbl2)

        # Scrollable playlist list using a QScrollArea with custom row widgets
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet('background:transparent; border:none;')
        self._pl_container = QWidget(); self._pl_container.setStyleSheet('background:transparent;')
        self._pl_layout = QVBoxLayout(self._pl_container)
        self._pl_layout.setContentsMargins(0,0,0,0); self._pl_layout.setSpacing(0)
        self._pl_layout.addStretch()
        scroll.setWidget(self._pl_container)
        root.addWidget(scroll, 1)

        self._pl_rows: list = []   # list of _PlaylistRowWidget
        self._selected_pl_idx = -1

        bdiv = QFrame(); bdiv.setFixedHeight(1); bdiv.setStyleSheet(f'background:{BORD};')
        root.addWidget(bdiv)

        bf = QWidget(); bf.setStyleSheet(f'background:{BG2};')
        bfl = QVBoxLayout(bf); bfl.setContentsMargins(10,12,10,12); bfl.setSpacing(6)
        add_f    = QPushButton('＋  Add Folder')
        add_m    = QPushButton('＋  Import M3U / M3U8')
        new_pl   = QPushButton('+ Create New Playlist')
        new_pl.setToolTip('Create an empty playlist and save as M3U8')
        refresh  = QPushButton('↺  Refresh Library')
        refresh.setToolTip('Rescan all saved folders')
        add_f.clicked.connect(self.add_folder_req); add_m.clicked.connect(self.add_m3u_req)
        new_pl.clicked.connect(self.new_playlist_req)
        refresh.clicked.connect(self.refresh_req)
        bfl.addWidget(add_f); bfl.addWidget(add_m); bfl.addWidget(new_pl); bfl.addWidget(refresh)
        root.addWidget(bf)

    def add_playlist(self, label: str):
        row = _PlaylistRowWidget(label)
        idx = len(self._pl_rows)
        self._pl_rows.append(row)
        # Insert before the trailing stretch
        self._pl_layout.insertWidget(self._pl_layout.count() - 1, row)
        row.select_clicked.connect(lambda i=idx: self._on_select(i))
        row.delete_clicked.connect(lambda i=idx: self._on_delete_clicked(i))

    def remove_playlist(self, idx: int):
        if not (0 <= idx < len(self._pl_rows)): return
        row = self._pl_rows.pop(idx)
        self._pl_layout.removeWidget(row); row.deleteLater()
        # Re-wire indices for remaining rows
        for i, r in enumerate(self._pl_rows):
            try: r.select_clicked.disconnect()
            except Exception: pass
            try: r.delete_clicked.disconnect()
            except Exception: pass
            r.select_clicked.connect(lambda _i=i: self._on_select(_i))
            r.delete_clicked.connect(lambda _i=i: self._on_delete_clicked(_i))
        if self._selected_pl_idx >= len(self._pl_rows):
            self._selected_pl_idx = -1

    def _on_select(self, idx: int):
        if self._selected_pl_idx >= 0 and self._selected_pl_idx < len(self._pl_rows):
            self._pl_rows[self._selected_pl_idx].set_selected(False)
        self._selected_pl_idx = idx
        self._pl_rows[idx].set_selected(True)
        self.source_selected.emit(idx)

    def _on_delete_clicked(self, idx: int):
        if not (0 <= idx < len(self._pl_rows)): return
        name = self._pl_rows[idx]._lbl.text()
        reply = QMessageBox.question(
            self, 'Remove Playlist',
            f'Remove "{name}" from the player?\n(Files will not be deleted)',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.remove_req.emit(idx)


# ══════════════════════════════════════════════════════════════════════════════
#  Repeat button (unchanged)
# ══════════════════════════════════════════════════════════════════════════════
def _ctrl(text, checkable=False, sz=44):
    b = QPushButton(text); b.setObjectName('ctrl')
    b.setCheckable(checkable); b.setMinimumSize(sz,sz); b.setMaximumSize(sz,sz)
    return b


class RepeatButton(QAbstractButton):
    mode_changed = pyqtSignal(RepeatMode)
    _TIPS  = ['No repeat', 'Repeat all', 'Repeat one']
    _MODES = [RepeatMode.NONE, RepeatMode.ALL, RepeatMode.ONE]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(44,44); self._idx = 0
        self.clicked.connect(self._cycle)
        self.setCursor(Qt.CursorShape.PointingHandCursor); self.setToolTip(self._TIPS[0])

    def _cycle(self):
        self._idx = (self._idx+1)%3; self.setToolTip(self._TIPS[self._idx])
        self.update(); self.mode_changed.emit(self._MODES[self._idx])

    def set_mode(self, m): self._idx = self._MODES.index(m); self.setToolTip(self._TIPS[self._idx]); self.update()
    def current_mode(self): return self._MODES[self._idx]

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        idx = self._idx; col = QColor(ACC if idx > 0 else FG2)
        cx, cy, r = self.width()//2, self.height()//2, 7
        if self.underMouse(): p.fillRect(self.rect(), QColor(BG3))
        pen = QPen(col, 2.0); pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(cx-r, cy-r, r*2, r*2, 60*16, 300*16)
        ang = math.radians(60); tx = cx+r*math.cos(ang); ty = cy-r*math.sin(ang)
        L, W = 4.5, 2.0; bx, by = 0.866, 0.5; px, py = -0.5, 0.866
        p.drawLine(QPointF(tx,ty), QPointF(tx+L*bx+W*px, ty+L*by+W*py))
        p.drawLine(QPointF(tx,ty), QPointF(tx+L*bx-W*px, ty+L*by-W*py))
        if idx == 2:
            f = QFont(p.font()); f.setPixelSize(8); f.setBold(True); p.setFont(f)
            p.setPen(col); p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '1')
        p.end()


# ══════════════════════════════════════════════════════════════════════════════
#  Control bar (with EQ button)
# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
#  Full-screen toggle button (painted 4 outward arrows)
# ══════════════════════════════════════════════════════════════════════════════
class _FullscreenBtn(QAbstractButton):
    """Draws 4 outward-pointing corner arrows; toggles on click."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_full = False
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._noop)

    def _noop(self): pass  # click handled by ControlBar._toggle_fullscreen

    def set_fullscreen(self, v: bool):
        self._is_full = v
        self.setToolTip('Exit Fullscreen' if v else 'Fullscreen')
        self.update()

    def sizeHint(self): return QSize(36, 36)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Background on hover
        if self.underMouse():
            p.setBrush(QBrush(QColor('#141414')))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(0, 0, 36, 36))
        col = QColor('#f0f0f0') if self.underMouse() else QColor('#909090')
        pen = QPen(col, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                   Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        # Arrow size and margin
        m = 8.0; a = 5.0   # margin from edge, arrow arm length
        # outward arrows when fullscreen → "compress/exit"; inward when normal → "expand"
        # Note: corner (cx,cy) is at the edge; arm goes cx+dx*a, cy+dy*a
        # For the icon to read as "expand", arms at each corner should point INWARD
        # (toward center) because that's the conventional "go fullscreen" arrows.
        s = 1 if self._is_full else -1
        # Four corners: (cx, cy, dx, dy) where d = outward direction
        corners = [
            (m,      m,      -s,  -s),   # top-left
            (36-m,   m,       s,  -s),   # top-right
            (m,      36-m,   -s,   s),   # bottom-left
            (36-m,   36-m,    s,   s),   # bottom-right
        ]
        for cx, cy, dx, dy in corners:
            # L-shaped arrow: horizontal arm + vertical arm + diagonal tip
            p.drawLine(QPointF(cx, cy), QPointF(cx + dx*a, cy))
            p.drawLine(QPointF(cx, cy), QPointF(cx, cy + dy*a))
        p.end()


class ControlBar(QFrame):
    cover_on_changed = pyqtSignal(bool)
    accent_changed   = pyqtSignal(str)

    def __init__(self, player: Player, parent=None):
        super().__init__(parent)
        self.setObjectName('ctrlbar'); self.setFixedHeight(172)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

        self._player    = player
        self._dur_ms    = 0
        self._seeking   = False
        self._viz_on    = True
        self._log_scale = True
        self._spec      = [MIN_DB] * VIZ_BANDS
        self._bar_pos:  list = []
        self._bar_color = QColor(44, 36, 36)
        self._cur_track: Optional[Track] = None
        self._inertia   = 0.5
        self._viz_paused= False

        self._frame_queue = deque(maxlen=240)
        self._delay_ms    = 0
        self._delay_timer = QTimer(self)
        self._delay_timer.setInterval(16)
        self._delay_timer.timeout.connect(self._update_delayed_frame)
        self._delay_timer.start()

        # Settings and EQ popups (lazy-created)
        self._settings_popup: Optional[SettingsPopup] = None
        self._eq_popup: Optional[EqPopup] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(18,14,18,12); root.setSpacing(10)

        # Row 1: seek
        row1 = QHBoxLayout(); row1.setSpacing(6)
        self._lbl_cur = QLabel('0:00'); self._lbl_cur.setObjectName('time_lbl')
        self._lbl_tot = QLabel('0:00'); self._lbl_tot.setObjectName('time_lbl')
        for lbl in (self._lbl_cur, self._lbl_tot):
            lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            lbl.setStyleSheet('background:transparent;')
        self._lbl_cur.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._lbl_tot.setAlignment(Qt.AlignmentFlag.AlignLeft  | Qt.AlignmentFlag.AlignVCenter)
        self._seek = SeekSlider(self)
        row1.addWidget(self._lbl_cur); row1.addWidget(self._seek, 1); row1.addWidget(self._lbl_tot)
        root.addLayout(row1)

        # Row 2: now-playing | transport | right buttons
        row2 = QHBoxLayout(); row2.setSpacing(0)

        # Now-playing
        info = QWidget(); info.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        info.setStyleSheet('background:transparent;')
        # Horizontal layout: cover thumbnail (optional) + title/artist stack
        info_h = QHBoxLayout(info); info_h.setContentsMargins(8, 0, 0, 0); info_h.setSpacing(10)
        _COVER_SZ = 64
        # Cover thumbnail — QGraphicsOpacityEffect at 65% (no per-pixel loop)
        self._cover_lbl = QLabel()
        self._cover_lbl.setFixedSize(_COVER_SZ, _COVER_SZ)
        self._cover_lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._cover_lbl.setStyleSheet('background:transparent;')
        self._cover_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover_lbl.setVisible(True)
        _cov_eff = QGraphicsOpacityEffect(self._cover_lbl); _cov_eff.setOpacity(0.65)
        self._cover_lbl.setGraphicsEffect(_cov_eff)
        info_h.addWidget(self._cover_lbl)
        # Title pinned to cover top, artist pinned to cover bottom
        txt_w = QWidget(); txt_w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        txt_w.setStyleSheet('background:transparent;'); txt_w.setFixedHeight(_COVER_SZ)
        il = QVBoxLayout(txt_w); il.setContentsMargins(0, 3, 0, 3); il.setSpacing(0)
        self._lbl_title  = QLabel('—'); self._lbl_title.setObjectName('now_title')
        self._lbl_artist = QLabel('');  self._lbl_artist.setObjectName('now_artist')
        for lbl in (self._lbl_title, self._lbl_artist):
            lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            lbl.setStyleSheet('background:transparent;')
            sh = QGraphicsDropShadowEffect(lbl)
            sh.setBlurRadius(8); sh.setOffset(0,0); sh.setColor(QColor(0,0,0,220))
            lbl.setGraphicsEffect(sh)
        self._lbl_title.setMaximumWidth(240); self._lbl_title.setWordWrap(False)
        self._lbl_title.setTextFormat(Qt.TextFormat.PlainText)
        il.addWidget(self._lbl_title, 0, Qt.AlignmentFlag.AlignTop)
        il.addStretch(1)
        il.addWidget(self._lbl_artist, 0, Qt.AlignmentFlag.AlignBottom)
        info_h.addWidget(txt_w, 1)
        row2.addWidget(info, 3)

        # Transport
        centre_w = QWidget(); centre_w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        centre_w.setStyleSheet('background:transparent;')
        centre = QHBoxLayout(centre_w); centre.setSpacing(6); centre.setContentsMargins(0,0,0,0)
        centre.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.btn_shuf = _ctrl('⇌', checkable=True)
        self.btn_prev = _ctrl('⏮')
        self.btn_play = QPushButton('▶'); self.btn_play.setObjectName('play')
        self.btn_play.setMinimumSize(52,52); self.btn_play.setMaximumSize(52,52)
        self.btn_next = _ctrl('⏭')
        self.btn_rep  = RepeatButton(self)
        _ts = (f'QPushButton#ctrl {{ background:transparent; border:none; color:{FG2};'
               f' font-size:20px; border-radius:22px; padding:0; text-align:center; }}'
               f'QPushButton#ctrl:hover {{ color:{FG}; background:rgba(40,40,40,180); }}'
               f'QPushButton#ctrl:checked {{ color:{ACC}; background:transparent; }}'
               f'QPushButton#ctrl:pressed {{ background:rgba(50,50,50,180); }}')
        for b in (self.btn_shuf, self.btn_prev, self.btn_next): b.setStyleSheet(_ts)
        self.btn_play.setStyleSheet(
            f'QPushButton#play {{ background:rgba(20,20,20,210); color:{ACC};'
            f' border:2px solid {ACC}; border-radius:26px;'
            f' min-width:52px; max-width:52px; min-height:52px; max-height:52px;'
            f' font-size:22px; padding:0 0 0 3px; text-align:center; }}'
            f'QPushButton#play:hover {{ border-color:{ACCH}; color:{ACCH};'
            f' background:rgba(35,35,35,210); }}'
            f'QPushButton#play:pressed {{ background:rgba(40,40,40,210); }}')
        for b in (self.btn_shuf, self.btn_prev, self.btn_play, self.btn_next, self.btn_rep):
            centre.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        row2.addWidget(centre_w, 2)

        # Right: blackout, eq, settings
        right = QWidget(); right.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        right.setStyleSheet('background:transparent;')
        rl = QHBoxLayout(right); rl.setContentsMargins(0,0,0,0); rl.setSpacing(6)
        rl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.btn_blackout = QPushButton('⬛'); self.btn_blackout.setObjectName('icon_btn')
        self.btn_blackout.setToolTip('Dim Screen (OLED protection)')
        self.btn_eq = QPushButton('EQ'); self.btn_eq.setObjectName('icon_btn')
        self.btn_eq.setToolTip('Equalizer')
        self.btn_lyrics = QPushButton('≡'); self.btn_lyrics.setObjectName('icon_btn')
        self.btn_lyrics.setToolTip('Lyrics')
        self.btn_lyrics.setCheckable(True)
        self.btn_fullscreen = _FullscreenBtn(self)
        self.btn_fullscreen.setObjectName('icon_btn')
        self.btn_fullscreen.setToolTip('Fullscreen')
        self.btn_settings = QPushButton('...');  self.btn_settings.setObjectName('icon_btn')
        self.btn_settings.setToolTip('Settings')
        for b in (self.btn_blackout, self.btn_eq, self.btn_lyrics,
                  self.btn_fullscreen, self.btn_settings):
            b.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.btn_eq.clicked.connect(self._toggle_eq)
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        self.btn_settings.clicked.connect(self._toggle_settings)
        rl.addWidget(self.btn_blackout); rl.addWidget(self.btn_eq)
        rl.addWidget(self.btn_lyrics)
        rl.addWidget(self.btn_fullscreen); rl.addWidget(self.btn_settings)
        row2.addWidget(right, 3)
        root.addLayout(row2)

        # signals
        player.sig_pos.connect(self._on_pos)
        player.sig_dur.connect(self._on_dur)
        player.sig_spectrum.connect(self._on_spectrum)
        self._seek.sliderPressed.connect(self._on_press)
        self._seek.sliderReleased.connect(self._on_release)
        self._seek.sliderMoved.connect(self._on_moved)

    # --- EQ popup ---
    def _ensure_eq_popup(self):
        if self._eq_popup is None:
            pop = EqPopup()
            pop.eq_changed.connect(self._on_eq_changed)
            self._eq_popup = pop
        return self._eq_popup

    def _toggle_eq(self):
        pop = self._ensure_eq_popup()
        # If popup was just hidden by clicking outside (which hit the button),
        # consume that flag and do nothing (leave closed)
        if pop._hidden_by_outside:
            pop._hidden_by_outside = False
            return
        # Load current EQ state from player
        pop.set_bands(self._player._eq_bands, self._player._eq_enabled)
        if pop.isVisible():
            pop.hide()
        else:
            pop.show_center()

    def _on_eq_changed(self, bands, enabled):
        self._player.set_eq_enabled(enabled)
        self._player.set_eq_bands(bands)

    # --- Settings popup ---
    def _ensure_settings_popup(self):
        if self._settings_popup is None:
            pop = SettingsPopup()
            pop.viz_toggled.connect(self._on_viz_toggle)
            pop.log_toggled.connect(self._on_log_toggle)
            pop.volume_changed.connect(lambda v: self._player.set_volume(v/100))
            pop.delay_changed.connect(self._on_delay_change)
            pop.inertia_changed.connect(self._on_inertia_change)
            pop.brightness_changed.connect(self._on_brightness_change)
            pop.cover_toggled.connect(self._on_cover_toggle)
            pop.accent_changed.connect(self._on_accent_change)
            pop.lyrics_fetch_toggled.connect(self._on_lyrics_fetch_toggle)
            pop.cover_fetch_toggled.connect(self._on_cover_fetch_btn)
            pop.tag_fetch_toggled.connect(self._on_tag_fetch_btn)
            if not self._player.has_spectrum:
                pop._viz_sw.setEnabled(False); pop._log_sw.setEnabled(False)
            self._settings_popup = pop
        return self._settings_popup

    @property
    def lyrics_fetch_enabled(self) -> bool:
        pop = self._settings_popup
        return pop.lyrics_fetch_on() if pop else True

    @property
    def cover_fetch_enabled(self) -> bool:
        pop = self._settings_popup
        return pop.cover_fetch_on() if pop else True

    def _on_lyrics_fetch_toggle(self, on: bool): pass  # LyricsPanel reads ctrlbar flag

    def _on_cover_fetch_btn(self):
        """Open the CoverFetchPopup — triggered by the Settings button."""
        win = self.window()
        pages = []
        if hasattr(win, '_lib_page') and win._lib_page:
            pages = [win._lib_page] + list(getattr(win, '_playlists', []))
        all_tracks = list(win._lib_page.tracks) if hasattr(win, '_lib_page') and win._lib_page else []
        if not all_tracks:
            QMessageBox.information(win, 'No Tracks', 'Add a folder to the library first.')
            return
        if self._settings_popup: self._settings_popup.hide()
        dlg = CoverFetchPopup(all_tracks, pages, self, parent=win)
        dlg.exec()

    def _on_tag_fetch_btn(self):
        """Open the TagFetchPopup — triggered by the Settings button."""
        win = self.window()
        all_tracks = list(win._lib_page.tracks) if hasattr(win, '_lib_page') and win._lib_page else []
        if not all_tracks:
            QMessageBox.information(win, 'No Tracks', 'Add a folder to the library first.')
            return
        if self._settings_popup: self._settings_popup.hide()
        dlg = TagFetchPopup(all_tracks, parent=win)
        # When tags are written, refresh the Track objects in all pages
        dlg.tags_updated.connect(lambda fp, tags: win._on_tags_fetched(fp, tags))
        dlg.exec()

    def _toggle_fullscreen(self):
        win = self.window()
        if win.isFullScreen():
            win.showMaximized()
            self.btn_fullscreen.set_fullscreen(False)
        else:
            win.showFullScreen()
            self.btn_fullscreen.set_fullscreen(True)

    def _toggle_settings(self):
        pop = self._ensure_settings_popup()
        if pop._hidden_by_outside:
            pop._hidden_by_outside = False
            return
        if pop.isVisible(): pop.hide()
        else: pop.show_above(self.btn_settings)

    def init_from_config(self, cfg: dict):
        # Settings popup
        pop = self._ensure_settings_popup()
        pop.set_volume(cfg.get('volume', 80))
        pop.set_delay(cfg.get('viz_delay_ms', 0))
        pop.set_inertia(cfg.get('inertia', 50))
        viz = cfg.get('viz_on', True); log = cfg.get('log_on', True)
        pop.set_viz(viz); pop.set_log(log)
        self._on_viz_toggle(viz); self._on_log_toggle(log)
        self._on_delay_change(cfg.get('viz_delay_ms', 0))
        self._on_inertia_change(cfg.get('inertia', 50))
        acc_color = cfg.get('accent_color', ACC)
        pop.set_accent_color(acc_color)
        if acc_color != '#e03030': self._on_accent_change(acc_color)
        bright = cfg.get('brightness', 40)
        pop.set_brightness(bright); self._on_brightness_change(bright)
        cover = cfg.get('cover_on', True)
        pop.set_cover(cover); self._on_cover_toggle(cover)
        pop.set_lyrics_fetch(cfg.get('lyrics_fetch_on', True))
        _cf = cfg.get('cover_fetch_on', True)
        pop.set_cover_fetch(_cf)
        global _cover_fetch_on; _cover_fetch_on = _cf
        self._player.set_volume(cfg.get('volume', 80) / 100)

        # EQ popup profiles and default state
        eq_pop = self._ensure_eq_popup()
        eq_profiles = cfg.get('eq_profiles', {})
        eq_pop.set_profiles(eq_profiles)

        # Load default EQ (if any) and apply it
        default_bands = cfg.get('default_eq_bands', [])
        default_enabled = cfg.get('default_eq_enabled', True)
        default_name = cfg.get('default_eq_profile', '')
        eq_pop.set_default(default_bands, default_enabled, default_name)
        eq_pop.set_bands(default_bands, default_enabled, default_name)
        # Apply to player
        self._player.set_eq_enabled(default_enabled)
        self._player.set_eq_bands(default_bands)

    def config_state(self) -> dict:
        cfg = {}
        pop = self._ensure_settings_popup()
        cfg.update({'volume': pop.volume(), 'viz_delay_ms': pop.delay(),
                    'viz_on': pop.viz_on(), 'log_on': pop.log_on(),
                    'inertia': pop.inertia(), 'brightness': pop.brightness(),
                    'cover_on': pop.cover_on(), 'accent_color': pop.accent_color(),
                    'lyrics_fetch_on': pop.lyrics_fetch_on(),
                    'cover_fetch_on': pop.cover_fetch_on()})
        eq_pop = self._ensure_eq_popup()
        cfg['eq_profiles'] = eq_pop.get_profiles()
        default_bands, default_enabled = eq_pop.get_default()
        cfg['default_eq_bands'] = default_bands
        cfg['default_eq_enabled'] = default_enabled
        cfg['default_eq_profile'] = eq_pop.get_default_name()
        return cfg

    # Rest of ControlBar methods (unchanged)...
    def resizeEvent(self, e): super().resizeEvent(e); self._precompute_bars()

    def _precompute_bars(self):
        w   = float(self.width())
        gap = 1.0 if w >= VIZ_BANDS * 3 else 0.0
        total_gap = gap * (VIZ_BANDS - 1)
        bw  = max(1.0, (w - total_gap) / VIZ_BANDS)
        stride = bw + gap
        self._bar_pos = [(i * stride, bw) for i in range(VIZ_BANDS)]

    def _on_viz_toggle(self, on: bool):
        self._viz_on = on; self._player.set_viz_active(on and not self._viz_paused)
        if not on:
            self._frame_queue.clear()
            for i in range(VIZ_BANDS): self._spec[i] = MIN_DB
        self.update()

    def _on_log_toggle(self, on: bool):
        self._log_scale = on; self.update()

    def _on_delay_change(self, v: int):
        self._delay_ms = v

    def _on_inertia_change(self, v: int):
        self._inertia = v / 100.0

    def _on_brightness_change(self, v: int):
        self._brightness_v = v
        # Desaturated tint: mix accent hue with neutral grey at 50% saturation
        base = QColor(ACC)
        h, s, lv, _ = base.getHsvF()
        tint = QColor()
        tint.setHsvF(h, s * 0.50, lv * (v / 100.0) * 0.55)
        self._bar_color = tint
        self.update()

    def _on_accent_change(self, color: str):
        global ACC, ACCH, SS
        ACC  = color
        ACCH = make_acch(color)
        SS   = make_stylesheet(ACC, ACCH)
        QApplication.instance().setStyleSheet(SS)
        self._on_brightness_change(getattr(self, '_brightness_v', 40))
        _cover_cache.clear()
        # Remove stale default cover disk cache (will regenerate with new color)
        for f in CONFIG_PATH.parent.glob('default_cover_*.jpg'):
            try: f.unlink()
            except Exception: pass
        self.accent_changed.emit(color)
    def _on_cover_toggle(self, on: bool):
        self._cover_lbl.setVisible(on)
        if on and self._cur_track:
            pm = get_cover_pixmap(self._cur_track.filepath, 64, 8)
            self._cover_lbl.setPixmap(pm if pm is not None else draw_default_cover(64, 8))
        # Propagate to main window via signal
        self.cover_on_changed.emit(on)

    def set_focus_paused(self, paused: bool):
        self._viz_paused = paused
        self._player.set_viz_active(self._viz_on and not paused)
        if paused:
            self._frame_queue.clear()
            for i in range(VIZ_BANDS): self._spec[i] = MIN_DB
            self.update()

    @pyqtSlot(list)
    def _on_spectrum(self, data: list):
        self._frame_queue.append((QDateTime.currentMSecsSinceEpoch(), data))

    def _update_delayed_frame(self):
        if not self._viz_on or self._viz_paused or not self._frame_queue: return
        target = QDateTime.currentMSecsSinceEpoch() - self._delay_ms
        best = None; best_diff = float('inf')
        for ts, frame in self._frame_queue:
            diff = target - ts
            if 0 <= diff < best_diff: best_diff = diff; best = frame
        if best is not None:
            alpha = self._inertia; n = min(VIZ_BANDS, len(best))
            for i in range(n):
                self._spec[i] = (1-alpha)*best[i] + alpha*self._spec[i]
            self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.fillRect(self.rect(), QColor('#000000'))
        if self._viz_on and not self._viz_paused and self._bar_pos:
            h = float(self.height()); w = float(self.width()); span = -MIN_DB
            _bw = self._bar_pos[0][1] if self._bar_pos else 2.0
            # Radius ≤ half bar width so semicircle fits cleanly
            rad = min(3.0, _bw * 0.5)
            use_aa = _bw >= 1.5
            p.setPen(Qt.PenStyle.NoPen)
            if use_aa:
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
            # Clip to widget so that bars drawn *below* h are cut off;
            # this makes the bottom corners invisible → only tops are rounded.
            p.setClipRect(QRectF(0, 0, w, h))
            brush = QBrush(self._bar_color)
            for i, (x, bw) in enumerate(self._bar_pos):
                if i >= VIZ_BANDS: break
                db = self._spec[i]
                if db <= MIN_DB: continue
                norm = (math.log10(1.0 + ((db-MIN_DB)/span)*9.0)
                        if self._log_scale else (db-MIN_DB)/span)
                if norm < 0.01: continue
                bar_h = norm * h
                if use_aa and bar_h > rad:
                    # Extend by rad below h — bottom rounding is clipped away
                    p.setBrush(brush)
                    p.drawRoundedRect(QRectF(x, h - bar_h, bw, bar_h + rad), rad, rad)
                else:
                    p.setBrush(brush)
                    p.drawRect(QRectF(x, h - bar_h, bw, bar_h))
            p.setClipping(False)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setPen(QPen(QColor(BORD), 1)); p.drawLine(0, 0, self.width(), 0)
        p.end()

    def _on_press(self):   self._seeking = True
    def _on_release(self):
        if self._dur_ms > 0 and self._player.has_pipe:
            self._player.seek(int(self._seek.value() * self._dur_ms / 1000))
        self._seeking = False

    def _on_moved(self, val):
        if self._dur_ms > 0: self._lbl_cur.setText(self._fmt(int(val*self._dur_ms/1000)))

    def _on_pos(self, ms):
        if self._seeking or self._seek.isSliderDown() or self._dur_ms == 0: return
        self._seek.setValue(int(ms*1000/self._dur_ms)); self._lbl_cur.setText(self._fmt(ms))

    def _on_dur(self, ms): self._dur_ms = ms; self._lbl_tot.setText(self._fmt(ms))

    def set_track(self, t: Track):
        self._lbl_title.setText(t.title or Path(t.filepath).name)
        self._lbl_artist.setText(t.artist)
        self._seek.setValue(0); self._lbl_cur.setText('0:00')
        self._dur_ms = int(t.duration*1000); self._lbl_tot.setText(t.dur_str())
        self._frame_queue.clear()
        for i in range(VIZ_BANDS): self._spec[i] = MIN_DB
        # Update cover thumbnail — always show whatever is in cache (or default)
        if self._cover_lbl.isVisible():
            pm = get_cover_pixmap(t.filepath, 64, 8)
            self._cover_lbl.setPixmap(pm if pm is not None else draw_default_cover(64, 8))
        self._cur_track = t



    def set_play_icon(self, playing: bool):
        self.btn_play.setText('⏸' if playing else '▶')

    @staticmethod
    def _fmt(ms):
        t = ms//1000; h, r = divmod(t, 3600); m, s = divmod(r, 60)
        return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


# ══════════════════════════════════════════════════════════════════════════════
#  Main window (with tag editing)
# ══════════════════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('BlackPlayer'); self.resize(1280, 760)

        self._player        = Player()
        self._playlists:    List[PlaylistPage] = []
        self._lib_page:     Optional[PlaylistPage] = None
        self._cur_page:     Optional[PlaylistPage] = None
        self._cur_idx:      int  = -1
        self._shuffle:      bool = False
        self._scan_threads: List[ScanThread] = []
        self._known_paths:  set  = set()
        self._cover_locked_paths: set = set()
        self._cur_track_mw: Track = None
        self._blackout = BlackoutOverlay()

        self._build_ui()
        self._connect_signals()
        self._load_config()
        self._mpris = MprisServer(self._player, self)


    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        body = QSplitter(Qt.Orientation.Horizontal); body.setHandleWidth(1)
        self._sidebar = Sidebar(); body.addWidget(self._sidebar)

        right = QWidget()
        rl = QVBoxLayout(right); rl.setContentsMargins(0,0,0,0); rl.setSpacing(0)

        cbar = QWidget(); cbar.setStyleSheet(f'background:{BG2}; border-bottom:1px solid {BORD};')
        cbar.setFixedHeight(28)
        cbl = QHBoxLayout(cbar); cbl.setContentsMargins(12,0,12,0)
        self._count_lbl = QLabel('')
        self._count_lbl.setStyleSheet(f'color:{FG2}; font-size:11px; background:transparent;')
        cbl.addStretch(); cbl.addWidget(self._count_lbl)
        rl.addWidget(cbar)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(False)   # Tabs are never shown for playlists
        self._tabs.tabBar().setVisible(False)   # Hide tab bar entirely; nav via sidebar
        rl.addWidget(self._tabs, 1)
        body.addWidget(right)

        # ctrlbar created just before root.addWidget; use late binding
        self._lyrics_panel = LyricsPanel(self._player, ctrlbar=None)
        self._lyrics_panel.setVisible(False)
        body.addWidget(self._lyrics_panel)

        body.setStretchFactor(0, 0); body.setStretchFactor(1, 1); body.setStretchFactor(2, 0)
        body.setSizes([230, 1050, 0])
        root.addWidget(body, 1)

        self._lib_page = PlaylistPage(label='Library')
        self._lib_page.play_track.connect(self._play_from_page)
        self._lib_page.ctx_requested.connect(self._show_ctx_menu)
        self._tabs.addTab(self._lib_page, '  Library')
        self._cur_page = self._lib_page

        self._ctrlbar = ControlBar(self._player)
        self._lyrics_panel._ctrlbar = self._ctrlbar
        root.addWidget(self._ctrlbar)
        self._status = self.statusBar()
        # Tab bar hidden; update count when tab changes programmatically
        self._tabs.currentChanged.connect(self._on_tab_change)

    def _install_close_btn(self, idx: int):
        if idx == 0: return
        btn = TabCloseButton()
        btn.clicked.connect(lambda: self._tabs.tabCloseRequested.emit(
            self._tabs.tabBar().tabAt(btn.pos())))
        self._tabs.tabBar().setTabButton(idx, QTabBar.ButtonPosition.RightSide, btn)

    def _update_tab_close_buttons(self, idx): pass

    def _connect_signals(self):
        self._sidebar.add_folder_req.connect(self._add_folder_dialog)
        self._sidebar.add_m3u_req.connect(self._import_m3u_dialog)
        self._sidebar.new_playlist_req.connect(self._new_playlist_dialog)
        self._sidebar.remove_req.connect(self._remove_playlist)
        self._sidebar.source_selected.connect(self._select_source)
        self._sidebar.search_changed.connect(self._apply_search)
        self._sidebar.refresh_req.connect(self._refresh_library)

        self._player.sig_end.connect(self._on_track_end)
        self._player.sig_err.connect(lambda e: self._status.showMessage(f'Error: {e}', 5000))
        self._ctrlbar.btn_play.clicked.connect(self._play_pause)
        self._ctrlbar.btn_prev.clicked.connect(self._prev_track)
        self._ctrlbar.btn_next.clicked.connect(self._next_track)
        self._ctrlbar.btn_shuf.toggled.connect(lambda v: setattr(self, '_shuffle', v))
        self._ctrlbar.btn_rep.mode_changed.connect(lambda _: None)
        self._ctrlbar.btn_blackout.clicked.connect(self._blackout.show_blackout)
        # Feed track info + position updates to the overlay
        self._player.sig_pos.connect(
            lambda ms: self._blackout.set_pos(ms, self._player.duration_ms()))
        self._ctrlbar.cover_on_changed.connect(self._on_cover_toggle)
        self._ctrlbar.accent_changed.connect(self._on_accent_refresh)
        self._ctrlbar.btn_lyrics.clicked.connect(self._toggle_lyrics)
        self._player.sig_pos.connect(self._lyrics_panel.on_position)
        self._lyrics_panel.status_msg.connect(
            lambda m: self._status.showMessage(m, 0) if m else self._status.clearMessage())
        self._lyrics_panel.seek_requested.connect(self._player.seek)

    def _on_cover_toggle(self, on: bool):
        self._lib_page.set_covers_on(on)
        for pl in self._playlists:
            pl.set_covers_on(on)

    def _on_tags_fetched(self, fp: str, tags: dict):
        """Called by TagFetchPopup when tags for a track have been written to disk.
        Refreshes the Track object in every page that contains this filepath."""
        if not tags: return
        for page in [self._lib_page] + self._playlists:
            if page is None: continue
            for i, t in enumerate(page.tracks):
                if t.filepath == fp:
                    # Apply only the fields that were updated
                    if tags.get('title'):  t.title  = tags['title']
                    if tags.get('artist'): t.artist = tags['artist']
                    if tags.get('album'):  t.album  = tags['album']
                    page.table._fill_row(i, t)
                    # If this is the currently playing track, update the control bar
                    if (self._cur_page is page and self._cur_idx == i):
                        self._ctrlbar.set_track(t)
                        self.setWindowTitle(f'{t.title}  —  BlackPlayer')
                    break

    def _on_accent_refresh(self, color: str):
        logo = self._sidebar.findChild(QLabel, 'logo_lbl')
        if logo: logo.setStyleSheet(
            f'color:{ACC}; font-size:15px; font-weight:900;'
            f' letter-spacing:3px; padding:14px 0 10px 0; background:transparent;')
        self._sidebar._lib_btn.setStyleSheet(
            f'QPushButton {{ background:{BG3}; color:{ACC}; border:none;'
            f' border-left:3px solid {ACC}; border-radius:6px; text-align:left;'
            f' padding:13px 16px; font-weight:bold; }}'
            f'QPushButton:hover {{ background:{BG4}; }}')
        self._ctrlbar._seek.update_accent(ACC, ACCH)
        self._ctrlbar.btn_play.setStyleSheet(
            f'QPushButton#play {{ background:rgba(20,20,20,210); color:{ACC};'
            f' border:2px solid {ACC}; border-radius:26px;'
            f' min-width:52px; max-width:52px; min-height:52px; max-height:52px;'
            f' font-size:22px; padding:0 0 0 3px; text-align:center; }}'
            f'QPushButton#play:hover {{ border-color:{ACCH}; color:{ACCH};'
            f' background:rgba(35,35,35,210); }}'
            f'QPushButton#play:pressed {{ background:rgba(40,40,40,210); }}')
        _ts = (f'QPushButton#ctrl {{ background:transparent; border:none; color:{FG2};'
               f' font-size:20px; border-radius:22px; padding:0; text-align:center; }}'
               f'QPushButton#ctrl:hover {{ color:{FG}; background:rgba(40,40,40,180); }}'
               f'QPushButton#ctrl:checked {{ color:{ACC}; background:transparent; }}'
               f'QPushButton#ctrl:pressed {{ background:rgba(50,50,50,180); }}')
        for b in (self._ctrlbar.btn_shuf, self._ctrlbar.btn_prev, self._ctrlbar.btn_next):
            b.setStyleSheet(_ts)
        self._lyrics_panel.set_accent(ACC)
        for row in self._sidebar._pl_rows:
            row.update_accent()
        for page in [self._lib_page] + self._playlists:
            if page and page.playing_idx >= 0:
                page.table.set_playing_row(page.playing_idx)

    def _open_lyrics_panel_from_config(self):
        """Restore lyrics panel open state from config."""
        if not self._lyrics_panel.isVisible():
            self._toggle_lyrics()

    def _toggle_lyrics(self, _checked=False):
        panel = self._lyrics_panel
        body  = self.findChild(QSplitter)
        if not body: return
        vis = panel.isVisible()
        panel.setVisible(not vis)
        self._ctrlbar.btn_lyrics.setChecked(not vis)
        sizes = body.sizes()
        if not vis:   # opening
            total = sum(sizes)
            body.setSizes([sizes[0], max(100, total - sizes[0] - 290), 290])
            if self._cur_track_mw:
                deferred = not self.isActiveWindow() or self._blackout.isVisible()
                panel.set_track(self._cur_track_mw, deferred=deferred)
        else:         # closing
            body.setSizes([sizes[0], sizes[1] + sizes[2], 0])

    # --- Context menu with tag editing ---
    def _show_ctx_menu(self, src_page, row, pos):
        if not (0 <= row < len(src_page.tracks)): return
        track = src_page.tracks[row]; m = QMenu(self)
        m.addAction('▶  Play').triggered.connect(lambda: self._play_from_page(src_page, row))
        m.addSeparator()
        add_sub = m.addMenu("Add to Playlist")
        for pl in self._playlists:
            if pl is not src_page:
                def _add(_, _pl=pl, _tr=track):
                    fps = {t.filepath for t in _pl.tracks}
                    if _tr.filepath not in fps:
                        tracks = sorted(list(_pl.tracks)+[_tr], key=lambda t: t.sort_key())
                        _pl.set_tracks(tracks, _pl.playing_idx); self._save_config()
                add_sub.addAction(pl.label).triggered.connect(_add)
        if src_page is not self._lib_page:
            m.addSeparator()
            def _rem(_, _p=src_page, _r=row):
                tracks = list(_p.tracks); tracks.pop(_r)
                _p.set_tracks(tracks, -1); self._rebuild_library(); self._save_config()
            m.addAction("Remove from Playlist").triggered.connect(_rem)
        m.addSeparator()
        m.addAction("✎  Edit Tags...").triggered.connect(
            lambda: self._edit_tags(src_page, row))
        m.exec(pos)

    def _edit_tags(self, page, row):
        track = page.tracks[row]
        dlg = TagEditDialog(track, locked_paths=self._cover_locked_paths, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_title, new_artist, new_album = dlg.get_tags()
            cover_action, cover_bytes, cover_locked = dlg.get_cover_result()
            # Update cover lock set
            if cover_locked:
                self._cover_locked_paths.add(track.filepath)
                _cover_locked_set.add(track.filepath)
            else:
                self._cover_locked_paths.discard(track.filepath)
                _cover_locked_set.discard(track.filepath)
            # Write to file using mutagen
            try:
                af = MutagenFile(track.filepath, easy=False)
                if af is None:
                    self._status.showMessage('Could not open file', 3000)
                    return
                ext = Path(track.filepath).suffix.lower()

                # Helper to delete a tag
                def del_tag(key):
                    if ext == '.mp3':
                        if key in af.tags:
                            del af.tags[key]
                    elif ext in ('.flac', '.ogg', '.opus'):
                        if key in af.tags:
                            del af.tags[key]
                    elif ext in ('.m4a', '.aac'):
                        if key in af.tags:
                            del af.tags[key]
                    else:
                        if key in af.tags:
                            del af.tags[key]

                # Update title
                if new_title == '':
                    # Delete title tag
                    if ext == '.mp3': del_tag('TIT2')
                    elif ext in ('.flac', '.ogg', '.opus'): del_tag('title')
                    elif ext in ('.m4a', '.aac'): del_tag('\xa9nam')
                    else: del_tag('title')
                elif new_title != track.title:
                    if ext == '.mp3': af['TIT2'] = new_title
                    elif ext in ('.flac', '.ogg', '.opus'): af['title'] = new_title
                    elif ext in ('.m4a', '.aac'): af['\xa9nam'] = new_title
                    else: af['title'] = new_title

                # Update artist
                if new_artist == '':
                    if ext == '.mp3': del_tag('TPE1')
                    elif ext in ('.flac', '.ogg', '.opus'): del_tag('artist')
                    elif ext in ('.m4a', '.aac'): del_tag('\xa9ART')
                    else: del_tag('artist')
                elif new_artist != track.artist:
                    if ext == '.mp3': af['TPE1'] = new_artist
                    elif ext in ('.flac', '.ogg', '.opus'): af['artist'] = new_artist
                    elif ext in ('.m4a', '.aac'): af['\xa9ART'] = new_artist
                    else: af['artist'] = new_artist

                # Update album
                if new_album == '':
                    if ext == '.mp3': del_tag('TALB')
                    elif ext in ('.flac', '.ogg', '.opus'): del_tag('album')
                    elif ext in ('.m4a', '.aac'): del_tag('\xa9alb')
                    else: del_tag('album')
                elif new_album != track.album:
                    if ext == '.mp3': af['TALB'] = new_album
                    elif ext in ('.flac', '.ogg', '.opus'): af['album'] = new_album
                    elif ext in ('.m4a', '.aac'): af['\xa9alb'] = new_album
                    else: af['album'] = new_album

                af.save()

                # Handle cover changes
                if cover_action == 'set' and cover_bytes:
                    embed_cover_bytes(track.filepath, cover_bytes)
                    # Invalidate disk cache for this track
                    _cover_cache.pop((track.filepath, 64, 8), None)
                    _cover_cache.pop((track.filepath, 28, 4), None)
                elif cover_action == 'remove':
                    try:
                        af2 = MutagenFile(track.filepath, easy=False)
                        ext2 = Path(track.filepath).suffix.lower()
                        if af2 and af2.tags:
                            if ext2 == '.mp3': af2.tags.delall('APIC')
                            elif ext2 == '.flac': af2.clear_pictures()
                            elif ext2 in ('.m4a','.aac'): af2.tags.pop('covr', None)
                            elif ext2 in ('.ogg','.opus'):
                                af2.tags.pop('metadata_block_picture', None)
                            af2.save()
                        _cover_cache.pop((track.filepath, 64, 8), None)
                        _cover_cache.pop((track.filepath, 28, 4), None)
                    except Exception: pass

                # Re-read metadata to get updated track
                updated_track = read_metadata(track.filepath)
                # Update in source page
                page.tracks[row] = updated_track
                page.table._fill_row(row, updated_track)
                # Also update in library if it's a different page
                if page is not self._lib_page:
                    # Find this track in library and update it
                    for i, t in enumerate(self._lib_page.tracks):
                        if t.filepath == updated_track.filepath:
                            self._lib_page.tracks[i] = updated_track
                            self._lib_page.table._fill_row(i, updated_track)
                            break
                # If this track is currently playing, update now-playing display
                if self._cur_page is page and self._cur_idx == row:
                    self._ctrlbar.set_track(updated_track)
                    self.setWindowTitle(f'{updated_track.title}  —  BlackPlayer')
                    self._mpris.notify_track(updated_track)
                self._status.showMessage('Tags updated', 3000)
                self._save_config()
            except Exception as e:
                self._status.showMessage(f'Error: {e}', 5000)

    # --- Scan methods (unchanged) ---
    def _new_playlist_dialog(self):
        """Ask for name, create an empty M3U8 in the first known folder, load it."""
        name, ok = QInputDialog.getText(self, 'New Playlist', 'Playlist name:')
        if not ok or not name.strip():
            return
        name = name.strip()
        # Find a writable folder — prefer first known non-m3u folder
        save_dir = None
        for p in self._known_paths:
            if not p.endswith(('.m3u', '.m3u8')) and os.path.isdir(p):
                save_dir = p; break
        if save_dir is None:
            # No known folder: ask user
            save_dir = QFileDialog.getExistingDirectory(self, 'Select Playlist Folder')
            if not save_dir:
                return
        # Build safe filename
        safe = ''.join(c for c in name if c.isalnum() or c in ' _-').strip() or 'playlist'
        m3u_path = str(Path(save_dir) / f'{safe}.m3u8')
        # Write empty M3U8
        try:
            with open(m3u_path, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U\n')
        except Exception as e:
            self._status.showMessage(f'Could not create M3U8: {e}', 4000); return
        # Create empty PlaylistPage directly (no scan needed — file is empty)
        page = PlaylistPage([], label=name)
        page.play_track.connect(self._play_from_page)
        page.ctx_requested.connect(self._show_ctx_menu)
        self._playlists.append(page)
        ti = self._tabs.addTab(page, f' {name} ')
        self._sidebar.add_playlist(name)
        self._tabs.setCurrentIndex(ti)
        # Remember the m3u8 path so "Refresh" can re-scan it
        self._known_paths.add(m3u_path); _clear_cover_disk_cache()
        # Store m3u path on page for later save
        page._m3u_path = m3u_path
        self._status.showMessage(f'"{name}" playlist created — {m3u_path}', 5000)
        self._save_config()

    def _add_folder_dialog(self):
        f = QFileDialog.getExistingDirectory(self, 'Select Music Folder', str(Path.home()))
        if f:
            self._known_paths.add(f); _clear_cover_disk_cache(); self._scan_path(f, False)

    def _import_m3u_dialog(self):
        f, _ = QFileDialog.getOpenFileName(self, 'Import Playlist', str(Path.home()),
            'Playlist (*.m3u *.m3u8);;All Files (*)')
        if f:
            self._known_paths.add(f); self._scan_path(f, True)

    def _refresh_library(self):
        if not self._known_paths:
            self._status.showMessage('No folders added.', 3000); return
        self._status.showMessage('Refreshing library…')
        _clear_cover_disk_cache()
        for path in list(self._known_paths):
            if not path.endswith(('.m3u', '.m3u8')):
                self._scan_path(path, False, refresh=True)

    def _scan_path(self, path, is_m3u, refresh=False):
        self._status.showMessage('Scanning…')
        t = ScanThread(path, is_m3u)
        t.done.connect(lambda tracks, label, r=refresh, p=path:
                       self._on_scan_done(tracks, label, r, p))
        t.progress.connect(lambda m: self._status.showMessage(m))
        self._scan_threads.append(t); t.start()

    def _on_scan_done(self, tracks, label, refresh=False, path=''):
        if not tracks:
            self._status.showMessage('No supported audio files found.', 3000); return

        if refresh:
            for pl in self._playlists:
                if pl.label == label:
                    pl.set_tracks(tracks); self._rebuild_library()
                    self._status.showMessage(f'"{label}" refreshed — {len(tracks)} tracks', 4000)
                    self._save_config(); return

        page = PlaylistPage(tracks, label=label)
        page.play_track.connect(self._play_from_page)
        page.ctx_requested.connect(self._show_ctx_menu)
        page.set_tracks(tracks)
        # Apply current cover preference
        pop = self._ctrlbar._ensure_settings_popup()
        page.set_covers_on(pop.cover_on())
        self._playlists.append(page)
        ti = self._tabs.addTab(page, f' {label} ')
        self._sidebar.add_playlist(label)
        self._tabs.setCurrentIndex(ti)
        self._rebuild_library()
        self._status.showMessage(f'"{label}" — {len(tracks)} tracks loaded', 4000)
        self._save_config()

    def _rebuild_library(self):
        all_tracks = []
        for pl in self._playlists: all_tracks.extend(pl.tracks)
        seen = set(); dedup = []
        for t in all_tracks:
            if t.filepath not in seen: seen.add(t.filepath); dedup.append(t)
        dedup.sort(key=lambda t: t.sort_key())
        pidx = -1
        if (self._cur_page is self._lib_page and
                0 <= self._cur_idx < len(self._lib_page.tracks)):
            fp = self._lib_page.tracks[self._cur_idx].filepath
            for i, t in enumerate(dedup):
                if t.filepath == fp: pidx = i; break
        self._lib_page.set_tracks(dedup, pidx); self._update_count()

    def _remove_playlist(self, idx):
        if not (0 <= idx < len(self._playlists)): return
        page = self._playlists.pop(idx)
        # Remove tab first (fast)
        for i in range(self._tabs.count()):
            if self._tabs.widget(i) is page:
                self._tabs.removeTab(i)
                break
        self._sidebar.remove_playlist(idx)
        # Defer library rebuild so the UI unblocks immediately
        QTimer.singleShot(0, lambda: (self._rebuild_library(), self._save_config()))

    def _close_tab(self, tab_idx):
        if tab_idx == 0: return
        page = self._tabs.widget(tab_idx)
        if page in self._playlists: self._remove_playlist(self._playlists.index(page))

    def _select_source(self, idx):
        if idx == -1: self._tabs.setCurrentIndex(0)
        else:
            ti = idx+1
            if ti < self._tabs.count(): self._tabs.setCurrentIndex(ti)

    # --- Playback ---
    def _play_from_page(self, page, row):
        self._cur_page = page; self._cur_idx = row; self._start_playback()

    def _start_playback(self):
        if not self._cur_page: return
        tracks = self._cur_page.tracks
        if not tracks or not (0 <= self._cur_idx < len(tracks)): return
        t = tracks[self._cur_idx]
        self._player.load(t.filepath)
        self._ctrlbar.set_track(t); self._ctrlbar.set_play_icon(True)
        self._cur_track_mw = t
        if self._lyrics_panel.isVisible():
            deferred = not self.isActiveWindow() or self._blackout.isVisible()
            self._lyrics_panel.set_track(t, deferred=deferred)
        self._cur_page.set_playing(self._cur_idx)
        self.setWindowTitle(f'{t.title}  —  BlackPlayer')
        self._status.showMessage(f'▶  {t.artist}  —  {t.title}', 0)
        self._mpris.notify_track(t); self._mpris.notify_status()
        self._blackout.set_track(t.title or Path(t.filepath).name, t.artist)

    def _play_pause(self):
        if not self._player.has_pipe:
            if self._cur_page and self._cur_page.tracks:
                if self._cur_idx < 0: self._cur_idx = 0
                self._start_playback()
        else:
            self._player.play_pause(); self._ctrlbar.set_play_icon(self._player.playing)
            self._mpris.notify_status()

    def _prev_track(self):
        self._sync_cur_idx()
        if self._cur_page and self._cur_idx > 0:
            self._cur_idx -= 1; self._start_playback()

    def _next_track(self): self._advance(forced=True)

    def _sync_cur_idx(self):
        """After a sort the page reorders _tracks; sync our _cur_idx to match."""
        if not self._cur_page: return
        pi = self._cur_page.playing_idx
        if pi >= 0:
            self._cur_idx = pi

    def _advance(self, forced=False):
        if not self._cur_page: return
        self._sync_cur_idx()          # always use the post-sort index
        n = len(self._cur_page.tracks)
        if n == 0: return
        repeat = self._ctrlbar.btn_rep.current_mode()
        if not forced and repeat == RepeatMode.ONE: self._start_playback(); return
        if self._shuffle: self._cur_idx = random.randint(0, n-1)
        else:
            self._cur_idx += 1
            if self._cur_idx >= n:
                if repeat == RepeatMode.ALL: self._cur_idx = 0
                else:
                    self._player.stop(); self._ctrlbar.set_play_icon(False)
                    self._mpris.notify_status(); return
        self._start_playback()

    def _on_track_end(self): self._advance()

    # --- Focus handling ---
    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.Type.ActivationChange:
            # Don't pause viz just because EQ/Settings Tool window is focused
            eq_vis  = self._ctrlbar._eq_popup is not None and self._ctrlbar._eq_popup.isVisible()
            set_vis = self._ctrlbar._settings_popup is not None and self._ctrlbar._settings_popup.isVisible()
            if not self.isActiveWindow() and not eq_vis and not set_vis:
                self._ctrlbar.set_focus_paused(True)
            elif self.isActiveWindow() or eq_vis or set_vis:
                self._ctrlbar.set_focus_paused(False)
                # Trigger deferred lyrics fetch if panel is visible
                if self._lyrics_panel.isVisible():
                    self._lyrics_panel.on_focus_gained()

    # --- Search / tab ---
    def _apply_search(self, q):
        page = self._tabs.currentWidget()
        if isinstance(page, PlaylistPage): page.apply_filter(q)

    def _on_tab_change(self, idx):
        page = self._tabs.widget(idx)
        if isinstance(page, PlaylistPage): self._cur_page = page; self._update_count(page)

    def _update_count(self, page=None):
        if page is None: page = self._tabs.currentWidget()
        if isinstance(page, PlaylistPage):
            self._count_lbl.setText(f'{len(page.tracks)} tracks')

    # --- Config ---
    def _save_config(self):
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            cfg = self._ctrlbar.config_state()
            cfg['playlists'] = [{'label': pl.label, 'tracks': [t.filepath for t in pl.tracks]}
                                 for pl in self._playlists]
            cfg['known_paths'] = list(self._known_paths)
            cfg['lyrics_panel_open'] = self._lyrics_panel.isVisible()
            cfg['cover_locked_paths'] = list(self._cover_locked_paths)
            CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
            # Write M3U8 for user-created playlists (those with _m3u_path attribute)
            for pl in self._playlists:
                if hasattr(pl, '_m3u_path'):
                    try:
                        lines = ['#EXTM3U\n']
                        for t in pl.tracks:
                            lines.append(f'#EXTINF:{int(t.duration)},{t.artist} - {t.title}\n')
                            lines.append(t.filepath + '\n')
                        with open(pl._m3u_path, 'w', encoding='utf-8') as f:
                            f.writelines(lines)
                    except Exception as e2:
                        print(f'M3U8 save error for {pl.label}: {e2}')
        except Exception as e:
            print(f'Config save error: {e}')

    def _load_config(self):
        if not CONFIG_PATH.exists():
            QTimer.singleShot(0, self._rebuild_library)
            return
        try:
            data = json.loads(CONFIG_PATH.read_text())
            for kp in data.get('known_paths', []):
                self._known_paths.add(kp)
            for pd in data.get('playlists', []):
                label  = pd.get('label', 'Playlist')
                tracks = sorted(
                    [read_metadata(fp) for fp in pd.get('tracks', []) if os.path.isfile(fp)],
                    key=lambda t: t.sort_key())
                if not tracks: continue
                page = PlaylistPage(tracks, label=label)
                page.play_track.connect(self._play_from_page)
                page.ctx_requested.connect(self._show_ctx_menu)
                page.set_tracks(tracks)
                self._playlists.append(page)
                ti = self._tabs.addTab(page, f' {label} ')
                self._sidebar.add_playlist(label)
            self._cover_locked_paths = set(data.get('cover_locked_paths', []))
            _cover_locked_set.update(self._cover_locked_paths)
            _cover_fetch_on = data.get('cover_fetch_on', True)
            self._ctrlbar.init_from_config(data)
            if data.get('lyrics_panel_open', False):
                QTimer.singleShot(200, self._open_lyrics_panel_from_config)
        except Exception as e:
            print(f'Config load error: {e}')
        finally:
            QTimer.singleShot(0, self._rebuild_library)

    # --- Keyboard ---
    def keyPressEvent(self, e):
        k, mod = e.key(), e.modifiers()
        if   k == Qt.Key.Key_Space:                                       self._play_pause()
        elif k == Qt.Key.Key_Left:   self._player.seek(max(0, self._player.position_ms()-5000))
        elif k == Qt.Key.Key_Right:  self._player.seek(self._player.position_ms()+5000)
        elif k in (Qt.Key.Key_BracketLeft,  Qt.Key.Key_MediaPrevious):   self._prev_track()
        elif k in (Qt.Key.Key_BracketRight, Qt.Key.Key_MediaNext):       self._next_track()
        elif k == Qt.Key.Key_MediaPlay:                                   self._play_pause()
        elif k == Qt.Key.Key_MediaStop:
            self._player.stop(); self._ctrlbar.set_play_icon(False); self._mpris.notify_status()
        elif k == Qt.Key.Key_F and mod == Qt.KeyboardModifier.ControlModifier:
            self._sidebar._search.setFocus(); self._sidebar._search.selectAll()
        else: super().keyPressEvent(e)

    def closeEvent(self, e): self._save_config(); self._player.stop(); super().closeEvent(e)


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════
def main():
    os.environ.setdefault('QT_QPA_PLATFORM', 'wayland;xcb')
    os.environ.setdefault('QT_WAYLAND_DISABLE_WINDOWDECORATION', '0')

    app = QApplication(sys.argv)
    app.setApplicationName('BlackPlayer')
    app.setStyleSheet(SS)

    pal = QPalette()
    for role, col in [
        (QPalette.ColorRole.Window,          BG),
        (QPalette.ColorRole.WindowText,      FG),
        (QPalette.ColorRole.Base,            BG),
        (QPalette.ColorRole.AlternateBase,   BG2),
        (QPalette.ColorRole.Text,            FG),
        (QPalette.ColorRole.Button,          BG3),
        (QPalette.ColorRole.ButtonText,      FG),
        (QPalette.ColorRole.Highlight,       SEL),
        (QPalette.ColorRole.HighlightedText, FG),
        (QPalette.ColorRole.Link,            ACC),
        (QPalette.ColorRole.ToolTipBase,     BG3),
        (QPalette.ColorRole.ToolTipText,     FG),
    ]: pal.setColor(role, QColor(col))
    app.setPalette(pal)

    win = MainWindow(); win.showMaximized()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
