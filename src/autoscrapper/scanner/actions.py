from __future__ import annotations

from typing import Tuple

from ..interaction.ui_windows import (
    ACTION_DELAY,
    MOVE_DURATION,
    SELL_RECYCLE_POST_DELAY,
    SELL_RECYCLE_SPEED_MULT,
    click_absolute,
    click_window_relative,
    move_absolute,
    move_window_relative,
    sleep_with_abort,
)
from ..interaction.keybinds import DEFAULT_STOP_KEY
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
    *,
    stop_key: str = DEFAULT_STOP_KEY,
    action_delay: float = ACTION_DELAY,
    menu_appear_delay: float = MENU_APPEAR_DELAY,
    post_action_delay: float = SELL_RECYCLE_POST_DELAY,
) -> None:
    move_duration = MOVE_DURATION * SELL_RECYCLE_SPEED_MULT
    action_pause = action_delay * SELL_RECYCLE_SPEED_MULT
    bx, by, bw, bh = action_bbox_rel
    sell_bbox_win = (infobox_rect[0] + bx, infobox_rect[1] + by, bw, bh)
    sx, sy = rect_center(sell_bbox_win)
    move_window_relative(
        sx,
        sy,
        window_left,
        window_top,
        duration=move_duration,
        pause=action_pause,
        stop_key=stop_key,
    )
    click_window_relative(
        sx,
        sy,
        window_left,
        window_top,
        pause=action_pause,
        stop_key=stop_key,
    )
    sleep_with_abort(menu_appear_delay, stop_key=stop_key)

    cx, cy = sell_confirm_button_center(
        window_left, window_top, window_width, window_height
    )
    move_absolute(
        cx,
        cy,
        duration=move_duration,
        pause=action_pause,
        stop_key=stop_key,
    )
    click_absolute(cx, cy, pause=action_pause, stop_key=stop_key)
    sleep_with_abort(post_action_delay, stop_key=stop_key)


def _perform_recycle(
    infobox_rect: Tuple[int, int, int, int],
    action_bbox_rel: Tuple[int, int, int, int],
    window_left: int,
    window_top: int,
    window_width: int,
    window_height: int,
    *,
    stop_key: str = DEFAULT_STOP_KEY,
    action_delay: float = ACTION_DELAY,
    menu_appear_delay: float = MENU_APPEAR_DELAY,
    post_action_delay: float = SELL_RECYCLE_POST_DELAY,
) -> None:
    move_duration = MOVE_DURATION * SELL_RECYCLE_SPEED_MULT
    action_pause = action_delay * SELL_RECYCLE_SPEED_MULT
    bx, by, bw, bh = action_bbox_rel
    recycle_bbox_win = (infobox_rect[0] + bx, infobox_rect[1] + by, bw, bh)
    rx, ry = rect_center(recycle_bbox_win)
    move_window_relative(
        rx,
        ry,
        window_left,
        window_top,
        duration=move_duration,
        pause=action_pause,
        stop_key=stop_key,
    )
    click_window_relative(
        rx,
        ry,
        window_left,
        window_top,
        pause=action_pause,
        stop_key=stop_key,
    )
    sleep_with_abort(menu_appear_delay, stop_key=stop_key)

    cx, cy = recycle_confirm_button_center(
        window_left, window_top, window_width, window_height
    )
    move_absolute(
        cx,
        cy,
        duration=move_duration,
        pause=action_pause,
        stop_key=stop_key,
    )
    click_absolute(cx, cy, pause=action_pause, stop_key=stop_key)
    sleep_with_abort(post_action_delay, stop_key=stop_key)
