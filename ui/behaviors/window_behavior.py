"""
Window behavior implementation (e.g., dragging).
"""

import ctypes
import sys
from ctypes import wintypes

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QWidget


GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
LONG_PTR = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long


def hide_window_from_alt_tab(window: QWidget):
    """Hide a top-level window from the Windows Alt+Tab switcher."""
    if sys.platform != "win32":
        return

    hwnd = int(window.winId())
    if hwnd == 0:
        return

    user32 = ctypes.windll.user32
    get_window_long_ptr = user32.GetWindowLongPtrW
    set_window_long_ptr = user32.SetWindowLongPtrW
    set_window_pos = user32.SetWindowPos

    get_window_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int]
    get_window_long_ptr.restype = LONG_PTR
    set_window_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int, LONG_PTR]
    set_window_long_ptr.restype = LONG_PTR
    set_window_pos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    set_window_pos.restype = wintypes.BOOL

    ex_style = get_window_long_ptr(hwnd, GWL_EXSTYLE)
    ex_style |= WS_EX_TOOLWINDOW
    ex_style &= ~WS_EX_APPWINDOW
    set_window_long_ptr(hwnd, GWL_EXSTYLE, ex_style)
    set_window_pos(
        hwnd,
        0,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
    )


class DraggableWindowBehavior:
    """Mixin to enable window dragging for frameless windows."""

    def __init__(self, window: QWidget):
        self._window = window
        self._drag_pos: QPoint | None = None
        self._did_drag = False

    def mouse_press_event(self, event: QMouseEvent):
        """Handle mouse press for window dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            )
            self._did_drag = False

    def mouse_move_event(self, event: QMouseEvent):
        """Handle mouse move for window dragging."""
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_pos)
            self._did_drag = True

    def mouse_release_event(self, event: QMouseEvent) -> bool:
        """Handle mouse release. Returns True if the window was actually dragged."""
        did_drag = self._did_drag
        self._drag_pos = None
        self._did_drag = False
        return did_drag
