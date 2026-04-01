"""Auto-hide window behavior – slides the main window off screen when near a desktop edge."""

import logging

from PyQt6.QtCore import (
    QEasingCurve,
    QObject,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QCursor, QMouseEvent, QPainter, QPolygon
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget

logger = logging.getLogger(__name__)

EDGE_THRESHOLD = 60   # px – distance from screen edge to trigger auto-hide
ANIM_DURATION = 220   # ms – slide animation duration
POLL_INTERVAL = 80    # ms – cursor polling interval
HIDE_DELAY = 450      # ms – debounce before auto-hiding


class EdgeToggleButton(QWidget):
    """Semi-transparent button pinned to the screen edge while the window is hidden."""

    clicked = pyqtSignal()

    _THICK = 20  # px – dimension perpendicular to the edge
    _LEN = 60    # px – dimension parallel to the edge

    # Visual states
    STATE_HIDDEN = "hidden"   # window is off-screen: blue, arrow pointing in
    STATE_HOVER  = "hover"    # visible via hover, not pinned: orange, arrow pointing in
    STATE_PINNED = "pinned"   # pinned visible: green, pin icon

    def __init__(self, edge: str, win_center: QPoint):
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._edge = edge
        self._state = self.STATE_HIDDEN
        self._place(win_center)

    def set_state(self, state: str):
        if self._state != state:
            self._state = state
            self.update()

    def _place(self, win_center: QPoint):
        screens = QApplication.screens()
        screen = (QApplication.primaryScreen() or screens[0]).availableGeometry()
        T, L = self._THICK, self._LEN
        if self._edge in ("left", "right"):
            w, h = T, L
            y = max(screen.top(), min(win_center.y() - h // 2, screen.bottom() - h))
            x = screen.left() if self._edge == "left" else screen.right() - w + 1
        else:
            w, h = L, T
            x = max(screen.left(), min(win_center.x() - w // 2, screen.right() - w))
            y = screen.top() if self._edge == "top" else screen.bottom() - h + 1
        self.setGeometry(x, y, w, h)

    def _hovered(self) -> bool:
        return self.geometry().contains(QCursor.pos())

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        hovered = self._hovered()
        state = self._state

        # Background colour per state
        if state == self.STATE_PINNED:
            base = QColor(46, 160, 67)   # green
        elif state == self.STATE_HOVER:
            base = QColor(210, 120, 20)  # orange
        else:
            base = QColor(70, 110, 230)  # blue

        alpha = 230 if hovered else 140
        base.setAlpha(alpha)

        p.setBrush(base)
        p.setPen(Qt.PenStyle.NoPen)
        r = self.rect().adjusted(1, 1, -1, -1)
        p.drawRoundedRect(r, 5, 5)

        # Icon: pinned state → pin symbol; others → directional arrow
        p.setBrush(QColor(255, 255, 255, 240))
        cx, cy = r.center().x(), r.center().y()

        if state == self.STATE_PINNED:
            # Pin icon: filled circle + vertical stick
            head_r = 4
            p.drawEllipse(cx - head_r, cy - head_r - 2, head_r * 2, head_r * 2)
            p.fillRect(cx - 1, cy + 2, 3, 6, QColor(255, 255, 255, 240))
        else:
            # Arrow pointing inward (toward where the window will appear)
            s = 5
            e = self._edge
            if e == "left":
                pts = [QPoint(cx - s + 3, cy - s), QPoint(cx + s - 1, cy), QPoint(cx - s + 3, cy + s)]
            elif e == "right":
                pts = [QPoint(cx + s - 3, cy - s), QPoint(cx - s + 1, cy), QPoint(cx + s - 3, cy + s)]
            elif e == "top":
                pts = [QPoint(cx - s, cy - s + 3), QPoint(cx, cy + s - 1), QPoint(cx + s, cy - s + 3)]
            else:
                pts = [QPoint(cx - s, cy + s - 3), QPoint(cx, cy - s + 1), QPoint(cx + s, cy + s - 3)]
            p.drawPolygon(QPolygon(pts))

        p.end()

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class AutoHideBehavior(QObject):
    """Manages auto-hide for a frameless main window.

    State:
      _active        – auto-hide mode is on (triggered by edge drag).
      _is_hidden     – window is currently off-screen.
      _pinned        – user clicked to pin window visible; hover-hide suppressed.
    """

    def __init__(self, window: QMainWindow):
        super().__init__(window)
        self._window = window
        self._active = False
        self._hidden_edge: str | None = None
        self._restored_pos: QPoint | None = None
        self._is_hidden = False
        self._pinned = False
        self._animating = False
        self._btn: EdgeToggleButton | None = None

        # Slide animation on the window's pos property
        self._anim = QPropertyAnimation(window, b"pos")
        self._anim.setDuration(ANIM_DURATION)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.finished.connect(self._on_anim_done)

        # Cursor polling
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_INTERVAL)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start()

        # Debounce before auto-hiding
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(HIDE_DELAY)
        self._hide_timer.timeout.connect(self._do_hide)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_drag_released(self):
        """Call this after the user actually dragged (moved) the window."""
        edge = self._detect_edge()
        if edge:
            self._start(edge)
        elif self._active:
            self._stop()

    def get_visible_pos(self) -> QPoint | None:
        """Return the visible (restored) position, or None if not in auto-hide mode.
        Used by MainWindow._close_app to persist the correct window position."""
        if self._active and self._restored_pos is not None:
            return QPoint(self._restored_pos)
        return None

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _start(self, edge: str):
        """Enter auto-hide mode at *edge*."""
        self._restored_pos = QPoint(self._window.pos())
        self._hidden_edge = edge
        self._is_hidden = False
        self._pinned = False
        self._active = True
        self._kill_button()
        self._do_hide()
        logger.debug(f"AutoHide activated at edge={edge}")

    def _stop(self):
        """Exit auto-hide mode completely (window must be visible when called)."""
        self._anim.stop()
        self._animating = False
        self._hide_timer.stop()
        self._active = False
        self._is_hidden = False
        self._pinned = False
        self._hidden_edge = None
        self._restored_pos = None
        self._kill_button()
        logger.debug("AutoHide deactivated")

    def _do_hide(self, force: bool = False):
        """Slide the window off the screen toward *_hidden_edge*.

        Args:
            force: skip the button-under-cursor guard (use for click-triggered hides).
        """
        if not self._active or self._is_hidden or self._animating:
            return
        # Don't hide if cursor is already over the button area,
        # unless this is an explicit click-triggered hide.
        if not force and self._btn and self._btn.geometry().contains(QCursor.pos()):
            return

        screen = self._screen_rect()
        p = self._window.pos()
        w, h = self._window.width(), self._window.height()

        if self._hidden_edge == "left":
            target = QPoint(screen.left() - w - 2, p.y())
        elif self._hidden_edge == "right":
            target = QPoint(screen.right() + 2, p.y())
        elif self._hidden_edge == "top":
            target = QPoint(p.x(), screen.top() - h - 2)
        else:  # bottom
            target = QPoint(p.x(), screen.bottom() + 2)

        self._is_hidden = True
        self._animate(target)
        if self._btn:
            self._btn.set_state(EdgeToggleButton.STATE_HIDDEN)
        logger.debug(f"AutoHide: hiding toward {self._hidden_edge}")

    def _do_show(self):
        """Slide the window back to *_restored_pos*."""
        if not self._active or not self._is_hidden or self._animating:
            return
        if self._restored_pos is None:
            return
        self._is_hidden = False
        self._animate(self._restored_pos)
        if self._btn:
            # showing via hover → orange; showing via click (pinned) → will be updated in _on_toggle_clicked
            state = EdgeToggleButton.STATE_PINNED if self._pinned else EdgeToggleButton.STATE_HOVER
            self._btn.set_state(state)
        logger.debug("AutoHide: showing window")

    def _animate(self, target: QPoint):
        self._anim.stop()
        self._animating = True
        self._anim.setStartValue(self._window.pos())
        self._anim.setEndValue(target)
        self._anim.start()

    def _on_anim_done(self):
        self._animating = False
        if self._is_hidden:
            # Just finished hiding → ensure toggle button is visible
            if self._btn is None:
                self._make_button()
        else:
            # Just finished showing → only kill button when pinned via click
            if self._pinned:
                self._kill_button()

    # ------------------------------------------------------------------
    # Toggle button
    # ------------------------------------------------------------------

    def _make_button(self):
        self._kill_button()
        wg = self._window.frameGeometry()
        if self._hidden_edge in ("left", "right"):
            center = QPoint(0, wg.center().y())
        else:
            center = QPoint(wg.center().x(), 0)
        self._btn = EdgeToggleButton(self._hidden_edge, center)
        self._btn.clicked.connect(self._on_toggle_clicked)
        self._btn.show()

    def _kill_button(self):
        if self._btn is not None:
            self._btn.close()
            self._btn.deleteLater()
            self._btn = None

    def _on_toggle_clicked(self):
        if not self._active:
            return
        if self._is_hidden:
            # Hidden → show and pin
            self._pinned = True
            self._hide_timer.stop()
            self._do_show()
            if self._btn:
                self._btn.set_state(EdgeToggleButton.STATE_PINNED)
        elif not self._pinned:
            # Visible via hover (not pinned) → pin: keep visible, cancel auto-hide
            self._pinned = True
            self._hide_timer.stop()
            if self._btn:
                self._btn.set_state(EdgeToggleButton.STATE_PINNED)
        else:
            # Visible and pinned → un-pin and hide
            self._pinned = False
            self._hide_timer.stop()
            self._do_hide(force=True)

    # ------------------------------------------------------------------
    # Cursor polling
    # ------------------------------------------------------------------

    def _poll(self):
        if not self._active:
            return
        if self._btn:
            self._btn.update()  # repaint to reflect hover state
        if self._animating:
            return

        cursor = QCursor.pos()
        btn_hit = self._btn is not None and self._btn.geometry().contains(cursor)
        win_hit = self._window.geometry().contains(cursor)

        if self._is_hidden:
            if btn_hit:
                self._do_show()
        else:
            if not self._pinned:
                # Update button to hover state when cursor is over button or window
                if self._btn and (btn_hit or win_hit):
                    self._btn.set_state(EdgeToggleButton.STATE_HOVER)
                if btn_hit or win_hit:
                    self._hide_timer.stop()
                elif not self._hide_timer.isActive():
                    self._hide_timer.start()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _detect_edge(self) -> str | None:
        """Return the closest screen edge if within EDGE_THRESHOLD, else None."""
        screen = self._screen_rect()
        win = self._window.frameGeometry()
        dists = {
            "left":   win.left() - screen.left(),
            "right":  screen.right() - win.right(),
            "top":    win.top() - screen.top(),
            "bottom": screen.bottom() - win.bottom(),
        }
        eligible = {e: d for e, d in dists.items() if d <= EDGE_THRESHOLD}
        return min(eligible, key=eligible.__getitem__) if eligible else None

    def _screen_rect(self):
        center = self._window.frameGeometry().center()
        screen = QApplication.screenAt(center) or QApplication.primaryScreen()
        return screen.availableGeometry()
