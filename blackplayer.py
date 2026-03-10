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
MAX_EQ_BANDS = 10
EQ_FREQ_MIN  = 20.0
EQ_FREQ_MAX  = 22000.0
EQ_GAIN_MIN  = -10.0
EQ_GAIN_MAX  = 10.0
EQ_Q_MIN     = 0.1
EQ_Q_MAX     = 10.0
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
        base_on = QColor(ACC)
        tc = QColor(
            int(0x20 + t*(base_on.red()-0x20)),
            int(0x20 + t*(base_on.green()-0x20)),
            int(0x20 + t*(base_on.blue()-0x20)))
        bc = QColor(
            int(0x3e + t*(base_on.red()-0x3e)),
            int(0x3e + t*(base_on.green()-0x3e)),
            int(0x3e + t*(base_on.blue()-0x3e)))
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
    """Slider that jumps immediately to the click/touch position."""
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('settings_popup')
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 16); root.setSpacing(10)

        hdr = QLabel('SETTINGS'); hdr.setObjectName('popup_title')
        root.addWidget(hdr)

        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet(f'background:{BORD}; margin:0;')
        root.addWidget(div)

        # Volume
        vol_row = QHBoxLayout(); vol_row.setSpacing(6)
        vol_lbl = QLabel('🔈  Volume'); vol_lbl.setObjectName('setting_lbl')
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

        # VIZ + LOG + COVER
        sw_row = QHBoxLayout(); sw_row.setSpacing(16)
        sw_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._viz_sw   = ToggleSwitch('VIZ',   self)
        self._log_sw   = ToggleSwitch('LOG',   self)
        self._cover_sw = ToggleSwitch('COVER', self)
        self._viz_sw.setChecked(True); self._log_sw.setChecked(True)
        self._cover_sw.setChecked(True)
        self._viz_sw.toggled.connect(self.viz_toggled)
        self._log_sw.toggled.connect(self.log_toggled)
        self._cover_sw.toggled.connect(self.cover_toggled)
        sw_row.addWidget(self._viz_sw); sw_row.addWidget(self._log_sw)
        sw_row.addWidget(self._cover_sw)
        root.addLayout(sw_row)

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

    def show_above(self, btn: QWidget):
        self.adjustSize()
        gpos = btn.mapToGlobal(QPoint(0, 0))
        x = gpos.x() + btn.width()//2 - self.width()//2
        y = gpos.y() - self.height() - 6
        screen = QApplication.primaryScreen().availableGeometry()
        x = max(screen.left()+4, min(x, screen.right()-self.width()-4))
        y = max(screen.top()+4, y)
        self.move(x, y)
        self.show()
        self.raise_()


# ══════════════════════════════════════════════════════════════════════════════
#  Tag edit dialog
# ══════════════════════════════════════════════════════════════════════════════
class TagEditDialog(QDialog):
    def __init__(self, track: 'Track', parent=None):
        super().__init__(parent)
        self.setWindowTitle('Edit Tags')
        self.setModal(True)
        self.setMinimumWidth(350)
        self._track = track

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Title
        title_lay = QHBoxLayout()
        title_lay.addWidget(QLabel('Title:'))
        self._title_edit = QLineEdit(track.title)
        title_lay.addWidget(self._title_edit)
        layout.addLayout(title_lay)

        # Artist
        artist_lay = QHBoxLayout()
        artist_lay.addWidget(QLabel('Artist:'))
        self._artist_edit = QLineEdit(track.artist)
        artist_lay.addWidget(self._artist_edit)
        layout.addLayout(artist_lay)

        # Album
        album_lay = QHBoxLayout()
        album_lay.addWidget(QLabel('Album:'))
        self._album_edit = QLineEdit(track.album)
        album_lay.addWidget(self._album_edit)
        layout.addLayout(album_lay)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_tags(self):
        return self._title_edit.text(), self._artist_edit.text(), self._album_edit.text()


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

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 9, 6, 9)
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


class _TableTouchScroll(QObject):
    """Touch filter: drag scrolls the table; short tap selects the row."""
    DRAG_THRESH = 12
    def __init__(self, table, parent=None):
        super().__init__(parent)
        self._table = table; self._start = None
        self._dragging = False; self._last_y = 0.0
    def eventFilter(self, obj, e):
        t = e.type()
        if t == QEvent.Type.TouchBegin:
            pts = e.points()
            if not pts: return False
            self._start = pts[0].position()
            self._last_y = self._start.y(); self._dragging = False
            e.accept(); return True
        if t == QEvent.Type.TouchUpdate:
            pts = e.points()
            if not pts or self._start is None: return False
            dy = pts[0].position().y() - self._start.y()
            if not self._dragging and abs(dy) > self.DRAG_THRESH:
                self._dragging = True
            if self._dragging:
                delta = pts[0].position().y() - self._last_y
                sb = self._table.verticalScrollBar()
                sb.setValue(sb.value() - int(delta))
                self._last_y = pts[0].position().y()
            e.accept(); return True
        if t == QEvent.Type.TouchEnd:
            pts = e.points()
            if not self._dragging and pts and self._start is not None:
                pos = pts[0].position().toPoint()
                idx = self._table.indexAt(pos)
                if idx.isValid(): self._table.setCurrentIndex(idx)
            self._start = None; self._dragging = False
            e.accept(); return True
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  EQ Popup – parametric equalizer with profiles
# ══════════════════════════════════════════════════════════════════════════════
class EqPopup(QFrame):
    eq_changed = pyqtSignal(list, bool)   # bands, enabled

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('eq_popup')
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(False)

        self._bands = []          # list of (freq, gain, Q)
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
        main.setContentsMargins(20, 18, 20, 18)
        main.setSpacing(12)

        # Header
        hdr = QLabel('PARAMETRIC EQ')
        hdr.setObjectName('popup_title')
        main.addWidget(hdr)

        # Profile management
        prof_layout = QHBoxLayout()
        prof_label = QLabel('Profile:')
        prof_layout.addWidget(prof_label)
        # "Loaded:" indicator
        self._loaded_lbl = QLabel('Loaded: —')
        self._loaded_lbl.setObjectName('setting_lbl')
        self._loaded_lbl.setFixedWidth(160)

        self._NEW = '＋ New'   # sentinel — always first item
        self._profile_combo = QComboBox()
        self._profile_combo.setEditable(True)
        self._profile_combo.setMinimumWidth(150)
        self._profile_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._profile_combo.setCompleter(None)   # no autocomplete / no filter while typing
        self._profile_combo.setStyleSheet("QComboBox { background-color: #000000; color: #f0f0f0; }")
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
        prof_layout.addSpacing(12)
        prof_layout.addWidget(self._loaded_lbl)
        prof_layout.addStretch()
        main.addLayout(prof_layout)

        # Enable toggle and default button
        ena_layout = QHBoxLayout()
        self._enable_sw = ToggleSwitch('EQ Active')
        self._enable_sw.setChecked(True)
        self._enable_sw.toggled.connect(self._on_enable_toggled)
        ena_layout.addWidget(self._enable_sw)

        self._btn_default = QPushButton('Set as Default')
        self._btn_default.clicked.connect(self._set_as_default)
        ena_layout.addWidget(self._btn_default)
        ena_layout.addStretch()
        main.addLayout(ena_layout)

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
        # Touch-scroll: drag → scroll, tap → select
        self._band_table.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)
        self._tscroll = _TableTouchScroll(self._band_table)
        self._band_table.viewport().installEventFilter(self._tscroll)
        main.addWidget(self._band_table)

        # Add/Remove buttons
        btn_row = QHBoxLayout()
        self._btn_add = QPushButton('➕ Add Band')
        self._btn_add.clicked.connect(self._add_band)
        self._btn_remove = QPushButton('✕ Remove')
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

    def _add_band(self):
        if len(self._bands) >= MAX_EQ_BANDS:
            QMessageBox.warning(self, 'Warning', f'Maximum {MAX_EQ_BANDS} bands can be added.')
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
            self._loaded_lbl.setText('Loaded: —')
            self._refresh_table()
            self._update_graph()
            self._apply_timer.start()
        elif name and name in self._profiles:
            self._bands = [list(b) for b in self._profiles[name]]
            self._refresh_table()
            self._update_graph()
            self._current_profile = name
            self._loaded_lbl.setText(f'Loaded: {name}')
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
        self._loaded_lbl.setText(f'Loaded: {name}')

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
            self._loaded_lbl.setText('Loaded: —')
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
            self._loaded_lbl.setText(f'Loaded: {name}')
        self.eq_changed.emit(self._bands, self._enabled)

    def set_profiles(self, profiles):
        self._profiles = profiles
        self._profile_combo.clear()
        self._profile_combo.addItem(self._NEW)  # always first
        for name in sorted(profiles.keys()):
            self._profile_combo.addItem(name)

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

    def sizeHint(self): return QSize(16, 16)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.underMouse():
            p.setBrush(QBrush(QColor(ACC))); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(0, 0, 16, 16))
            pen = QPen(QColor('#ffffff'), 1.8)
        else:
            pen = QPen(QColor(FG2), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        m = 4.5
        p.drawLine(QPointF(m, m), QPointF(16-m, 16-m))
        p.drawLine(QPointF(16-m, m), QPointF(m, 16-m))
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


def draw_default_cover(size: int, radius: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # Black rounded background
    p.setBrush(QBrush(QColor(BG)))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(0, 0, size, size, radius, radius)
    # Draw treble clef character in red
    p.setPen(QPen(QColor(ACC), 1))
    font = p.font()
    font.setPixelSize(int(size * 0.7))
    # Try to use a font that contains the treble clef
    font.setFamily("Segoe UI Symbol, FreeSerif, Symbola, Arial Unicode MS")
    p.setFont(font)
    p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "𝄞")
    p.end()
    return pm


def get_cover_pixmap(fp: str, size: int = 48, radius: int = 4) -> Optional[QPixmap]:
    """Return cached rounded QPixmap or a default clef pixmap if no cover."""
    key = (fp, size, radius)
    if key in _cover_cache:
        return _cover_cache[key]

    data = extract_cover_bytes(fp)
    if data:
        raw = QPixmap()
        if raw.loadFromData(data):
            pm = _rounded_pixmap(raw, size, radius)
            _cover_cache[key] = pm
            return pm

    # No embedded cover – use default clef image
    default = draw_default_cover(size, radius)
    _cover_cache[key] = default
    return default


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
        if self._pipe:
            self._pipe.seek_simple(Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, ms*Gst.MSECOND)
            if self._playing: self._pipe.set_state(Gst.State.PLAYING)

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
        sp.setScrollMetric(QScrollerProperties.ScrollMetric.DecelerationFactor,           0.25)
        sp.setScrollMetric(QScrollerProperties.ScrollMetric.MaximumVelocity,              0.6)
        sp.setScrollMetric(QScrollerProperties.ScrollMetric.AcceleratingFlickMaximumTime, 0.15)
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
        for r, t in enumerate(tracks): self._fill_row(r, t)
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
                if pm: item.setIcon(QIcon(pm))
            align = Qt.AlignmentFlag.AlignVCenter | (
                Qt.AlignmentFlag.AlignRight if col in (C_LEN, C_SR, C_BD, C_TYP)
                else Qt.AlignmentFlag.AlignLeft)
            item.setTextAlignment(align); self.setItem(row, col, item)

    def set_covers_on(self, on: bool, tracks: list):
        self._covers_on = on
        self.setIconSize(QSize(28, 28) if on else QSize(0, 0))
        for r, t in enumerate(tracks):
            if r >= self.rowCount(): break
            item = self.item(r, C_TIT)
            if item:
                if on:
                    pm = get_cover_pixmap(t.filepath, 28, 4)
                    item.setIcon(QIcon(pm) if pm else QIcon())
                else:
                    item.setIcon(QIcon())

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

        self._lib_btn = QPushButton('  ♪  All Tracks')
        self._lib_btn.setStyleSheet(
            f'QPushButton {{ background:{BG3}; color:{ACC}; border:none;'
            f' border-left:3px solid {ACC}; border-radius:6px; text-align:left;'
            f' padding:13px 16px; font-weight:bold; }}'
            f'QPushButton:hover {{ background:{BG4}; }}')
        self._lib_btn.clicked.connect(lambda: self.source_selected.emit(-1))
        root.addWidget(self._lib_btn)

        lbl2 = QLabel("PLAYLISTS"); lbl2.setObjectName('sect_lbl'); root.addWidget(lbl2)
        self._list = QListWidget()
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._ctx_menu)
        self._list.currentRowChanged.connect(
            lambda r: self.source_selected.emit(r) if r >= 0 else None)
        QScroller.grabGesture(self._list.viewport(), QScroller.ScrollerGestureType.TouchGesture)
        root.addWidget(self._list, 1)

        bdiv = QFrame(); bdiv.setFixedHeight(1); bdiv.setStyleSheet(f'background:{BORD};')
        root.addWidget(bdiv)

        bf = QWidget(); bf.setStyleSheet(f'background:{BG2};')
        bfl = QVBoxLayout(bf); bfl.setContentsMargins(10,12,10,12); bfl.setSpacing(6)
        add_f    = QPushButton('＋  Add Folder')
        add_m    = QPushButton('＋  Import M3U / M3U8')
        new_pl   = QPushButton('♫  Create New Playlist')
        new_pl.setToolTip('Create an empty playlist and save as M3U8')
        refresh  = QPushButton('↺  Refresh Library')
        refresh.setToolTip('Rescan all saved folders')
        add_f.clicked.connect(self.add_folder_req); add_m.clicked.connect(self.add_m3u_req)
        new_pl.clicked.connect(self.new_playlist_req)
        refresh.clicked.connect(self.refresh_req)
        bfl.addWidget(add_f); bfl.addWidget(add_m); bfl.addWidget(new_pl); bfl.addWidget(refresh)
        root.addWidget(bf)

    def add_playlist(self, label):   self._list.addItem(f'  {label}')
    def remove_playlist(self, idx):  self._list.takeItem(idx)

    def _ctx_menu(self, pos):
        item = self._list.itemAt(pos)
        if not item: return
        m = QMenu(self)
        m.addAction('Remove').triggered.connect(
            lambda: self.remove_req.emit(self._list.row(item)))
        m.exec(self._list.viewport().mapToGlobal(pos))


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
        self.btn_eq = QPushButton('🎚️'); self.btn_eq.setObjectName('icon_btn')
        self.btn_eq.setToolTip('Equalizer')
        self.btn_fullscreen = _FullscreenBtn(self)
        self.btn_fullscreen.setObjectName('icon_btn')
        self.btn_fullscreen.setToolTip('Fullscreen')
        self.btn_settings = QPushButton('⚙');  self.btn_settings.setObjectName('icon_btn')
        self.btn_settings.setToolTip('Settings')
        for b in (self.btn_blackout, self.btn_eq, self.btn_fullscreen, self.btn_settings):
            b.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.btn_eq.clicked.connect(self._toggle_eq)
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        self.btn_settings.clicked.connect(self._toggle_settings)
        rl.addWidget(self.btn_blackout); rl.addWidget(self.btn_eq)
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
            if not self._player.has_spectrum:
                pop._viz_sw.setEnabled(False); pop._log_sw.setEnabled(False)
            self._settings_popup = pop
        return self._settings_popup

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
                    'cover_on': pop.cover_on(), 'accent_color': pop.accent_color()})
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
        self.accent_changed.emit(color)
    def _on_cover_toggle(self, on: bool):
        self._cover_lbl.setVisible(on)
        if on and self._cur_track:
            pm = get_cover_pixmap(self._cur_track.filepath, 64, 8)
            self._cover_lbl.setPixmap(pm if pm else QPixmap())
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
        if self._dur_ms > 0: self._player.seek(int(self._seek.value()*self._dur_ms/1000))
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
        # Update cover thumbnail (opacity via QGraphicsOpacityEffect)
        if self._cover_lbl.isVisible():
            pm = get_cover_pixmap(t.filepath, 64, 8)
            self._cover_lbl.setPixmap(pm if pm else QPixmap())
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
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        rl.addWidget(self._tabs, 1)
        body.addWidget(right)
        body.setStretchFactor(0,0); body.setStretchFactor(1,1); body.setSizes([230, 1050])
        root.addWidget(body, 1)

        self._lib_page = PlaylistPage(label='Library')
        self._lib_page.play_track.connect(self._play_from_page)
        self._lib_page.ctx_requested.connect(self._show_ctx_menu)
        self._tabs.addTab(self._lib_page, '♪  Library')
        self._tabs.tabBar().setTabButton(0, QTabBar.ButtonPosition.RightSide, None)
        self._cur_page = self._lib_page

        self._ctrlbar = ControlBar(self._player)
        root.addWidget(self._ctrlbar)
        self._status = self.statusBar()

        self._tabs.tabBar().tabBarClicked.connect(self._update_tab_close_buttons)

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
        self._tabs.currentChanged.connect(self._on_tab_change)
        self._ctrlbar.cover_on_changed.connect(self._on_cover_toggle)
        self._ctrlbar.accent_changed.connect(self._on_accent_refresh)

    def _on_cover_toggle(self, on: bool):
        self._lib_page.set_covers_on(on)
        for pl in self._playlists:
            pl.set_covers_on(on)

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
        for page in [self._lib_page] + self._playlists:
            if page and page.playing_idx >= 0:
                page.table.set_playing_row(page.playing_idx)

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
        dlg = TagEditDialog(track, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_title, new_artist, new_album = dlg.get_tags()
            # Write to file using mutagen
            try:
                af = MutagenFile(track.filepath, easy=False)
                if af is None:
                    self._status.showMessage('Could not open file', 3000)
                    return
                # Update tags based on file type
                ext = Path(track.filepath).suffix.lower()
                if ext == '.mp3':
                    if new_title: af['TIT2'] = new_title
                    if new_artist: af['TPE1'] = new_artist
                    if new_album: af['TALB'] = new_album
                elif ext in ('.flac', '.opus', '.ogg'):
                    if new_title: af['title'] = new_title
                    if new_artist: af['artist'] = new_artist
                    if new_album: af['album'] = new_album
                elif ext in ('.m4a', '.aac'):
                    if new_title: af['\xa9nam'] = new_title
                    if new_artist: af['\xa9ART'] = new_artist
                    if new_album: af['\xa9alb'] = new_album
                else:
                    if new_title: af['title'] = new_title
                    if new_artist: af['artist'] = new_artist
                    if new_album: af['album'] = new_album
                af.save()
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
        close_btn = TabCloseButton()
        close_btn.clicked.connect(lambda checked=False, idx=ti: self._close_tab(idx))
        self._tabs.tabBar().setTabButton(ti, QTabBar.ButtonPosition.RightSide, close_btn)
        self._sidebar.add_playlist(name)
        self._tabs.setCurrentIndex(ti)
        # Remember the m3u8 path so "Refresh" can re-scan it
        self._known_paths.add(m3u_path)
        # Store m3u path on page for later save
        page._m3u_path = m3u_path
        self._status.showMessage(f'"{name}" playlist created — {m3u_path}', 5000)
        self._save_config()

    def _add_folder_dialog(self):
        f = QFileDialog.getExistingDirectory(self, 'Select Music Folder', str(Path.home()))
        if f:
            self._known_paths.add(f); self._scan_path(f, False)

    def _import_m3u_dialog(self):
        f, _ = QFileDialog.getOpenFileName(self, 'Import Playlist', str(Path.home()),
            'Playlist (*.m3u *.m3u8);;All Files (*)')
        if f:
            self._known_paths.add(f); self._scan_path(f, True)

    def _refresh_library(self):
        if not self._known_paths:
            self._status.showMessage('No folders added.', 3000); return
        self._status.showMessage('Refreshing library…')
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
        close_btn = TabCloseButton()
        tab_idx = ti
        close_btn.clicked.connect(lambda checked=False, idx=tab_idx: self._close_tab(idx))
        self._tabs.tabBar().setTabButton(ti, QTabBar.ButtonPosition.RightSide, close_btn)
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
        for i in range(self._tabs.count()):
            if self._tabs.widget(i) is page: self._tabs.removeTab(i); break
        self._sidebar.remove_playlist(idx)
        self._rebuild_library(); self._save_config()

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
            self._ctrlbar.set_focus_paused(not self.isActiveWindow())

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
        if not CONFIG_PATH.exists(): return
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
                close_btn = TabCloseButton()
                tab_idx = ti
                close_btn.clicked.connect(lambda checked=False, idx=tab_idx: self._close_tab(idx))
                self._tabs.tabBar().setTabButton(ti, QTabBar.ButtonPosition.RightSide, close_btn)
                self._sidebar.add_playlist(label)
            self._ctrlbar.init_from_config(data)
            self._rebuild_library()
        except Exception as e:
            print(f'Config load error: {e}')

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
