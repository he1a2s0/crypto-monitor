from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication, QMainWindow

from ui.behaviors.auto_hide_behavior import AutoHideBehavior


def _get_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_restore_hidden_state_moves_window_offscreen_and_keeps_visible_position():
    app = _get_app()
    window = QMainWindow()
    window.resize(240, 180)
    window.move(80, 120)

    behavior = AutoHideBehavior(window)
    try:
        behavior.restore_hidden_state("left")

        hidden, edge = behavior.get_hidden_state()

        assert hidden is True
        assert edge == "left"
        assert behavior.get_visible_pos() == QPoint(80, 120)
        assert window.pos().x() < 80
        assert behavior._btn is not None
    finally:
        behavior.shutdown()
        window.close()
        app.processEvents()


def test_persisted_state_stays_enabled_while_hover_visible():
    app = _get_app()
    window = QMainWindow()
    window.resize(240, 180)
    window.move(80, 120)

    behavior = AutoHideBehavior(window)
    try:
        behavior.restore_hidden_state("right")
        behavior._is_hidden = False

        should_restore_hidden, edge = behavior.get_persisted_state()

        assert should_restore_hidden is True
        assert edge == "right"
    finally:
        behavior.shutdown()
        window.close()
        app.processEvents()