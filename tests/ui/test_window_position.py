from PyQt6.QtCore import QPoint, QRect, QSize

from ui.behaviors.window_behavior import normalize_window_position


def test_normalize_window_position_keeps_valid_negative_screen_coordinates():
    screens = [
        QRect(-1920, 0, 1920, 1080),
        QRect(0, 0, 1920, 1080),
    ]

    result = normalize_window_position(QPoint(-1800, 100), QSize(160, 300), screens)

    assert result == QPoint(-1800, 100)


def test_normalize_window_position_clamps_offscreen_coordinates_to_nearest_screen():
    screens = [
        QRect(-1920, 0, 1920, 1080),
        QRect(0, 0, 1920, 1080),
    ]

    result = normalize_window_position(QPoint(-2500, -300), QSize(160, 300), screens)

    assert result == QPoint(-1920, 0)