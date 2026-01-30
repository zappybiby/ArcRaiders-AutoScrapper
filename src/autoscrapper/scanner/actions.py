from __future__ import annotations

from typing import Tuple

from ..interaction.ui_windows import (
    SELL_RECYCLE_ACTION_DELAY,
    SELL_RECYCLE_MOVE_DURATION,
    SELL_RECYCLE_POST_DELAY,
    click_absolute,
    click_window_relative,
    move_absolute,
    move_window_relative,
    sleep_with_abort,
)
from ..ocr.inventory_vision import (
    recycle_confirm_button_center,
    rect_center,
    sell_confirm_button_center,
)

MENU_APPEAR_DELAY = 0.15


def _perform_sell(
    infobox_rect: Tuple[int, int, int, int],
    action_bbox_rel: Tuple[int, int, int, int],
    window_left: int,
    window_top: int,
    window_width: int,
    window_height: int,
) -> None:
    bx, by, bw, bh = action_bbox_rel
    sell_bbox_win = (infobox_rect[0] + bx, infobox_rect[1] + by, bw, bh)
    sx, sy = rect_center(sell_bbox_win)
    move_window_relative(
        sx,
        sy,
        window_left,
        window_top,
        duration=SELL_RECYCLE_MOVE_DURATION,
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    click_window_relative(
        sx,
        sy,
        window_left,
        window_top,
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    sleep_with_abort(MENU_APPEAR_DELAY)

    cx, cy = sell_confirm_button_center(
        window_left, window_top, window_width, window_height
    )
    move_absolute(
        cx,
        cy,
        duration=SELL_RECYCLE_MOVE_DURATION,
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    click_absolute(cx, cy, pause=SELL_RECYCLE_ACTION_DELAY)
    sleep_with_abort(SELL_RECYCLE_POST_DELAY)


def _perform_recycle(
    infobox_rect: Tuple[int, int, int, int],
    action_bbox_rel: Tuple[int, int, int, int],
    window_left: int,
    window_top: int,
    window_width: int,
    window_height: int,
) -> None:
    bx, by, bw, bh = action_bbox_rel
    recycle_bbox_win = (infobox_rect[0] + bx, infobox_rect[1] + by, bw, bh)
    rx, ry = rect_center(recycle_bbox_win)
    move_window_relative(
        rx,
        ry,
        window_left,
        window_top,
        duration=SELL_RECYCLE_MOVE_DURATION,
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    click_window_relative(
        rx,
        ry,
        window_left,
        window_top,
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    sleep_with_abort(MENU_APPEAR_DELAY)

    cx, cy = recycle_confirm_button_center(
        window_left, window_top, window_width, window_height
    )
    move_absolute(
        cx,
        cy,
        duration=SELL_RECYCLE_MOVE_DURATION,
        pause=SELL_RECYCLE_ACTION_DELAY,
    )
    click_absolute(cx, cy, pause=SELL_RECYCLE_ACTION_DELAY)
    sleep_with_abort(SELL_RECYCLE_POST_DELAY)
