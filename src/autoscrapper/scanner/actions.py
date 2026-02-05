from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

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
    InfoboxOcrResult,
    recycle_confirm_button_center,
    rect_center,
    sell_confirm_button_center,
)
from ..core.item_actions import ActionMap, Decision

MENU_APPEAR_DELAY = 0.15


@dataclass(frozen=True)
class ActionExecutionContext:
    apply_actions: bool
    win_left: int
    win_top: int
    win_width: int
    win_height: int
    stop_key: str
    action_delay: float
    menu_appear_delay: float
    post_action_delay: float


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


def _apply_destructive_decision(
    *,
    decision: Decision,
    infobox_rect: Optional[Tuple[int, int, int, int]],
    infobox_ocr: Optional[InfoboxOcrResult],
    action_bbox_rel: Optional[Tuple[int, int, int, int]],
    context: ActionExecutionContext,
) -> str:
    if infobox_rect is None or infobox_ocr is None:
        return "SKIP_NO_INFOBOX"
    if action_bbox_rel is None:
        return "SKIP_NO_ACTION_BBOX"
    if not context.apply_actions:
        return f"DRY_RUN_{decision}"

    if decision == "SELL":
        _perform_sell(
            infobox_rect,
            action_bbox_rel,
            context.win_left,
            context.win_top,
            context.win_width,
            context.win_height,
            stop_key=context.stop_key,
            action_delay=context.action_delay,
            menu_appear_delay=context.menu_appear_delay,
            post_action_delay=context.post_action_delay,
        )
        return "SELL"

    _perform_recycle(
        infobox_rect,
        action_bbox_rel,
        context.win_left,
        context.win_top,
        context.win_width,
        context.win_height,
        stop_key=context.stop_key,
        action_delay=context.action_delay,
        menu_appear_delay=context.menu_appear_delay,
        post_action_delay=context.post_action_delay,
    )
    return "RECYCLE"


def resolve_action_taken(
    *,
    decision: Optional[Decision],
    item_name: str,
    actions: ActionMap,
    infobox_rect: Optional[Tuple[int, int, int, int]],
    infobox_ocr: Optional[InfoboxOcrResult],
    sell_bbox_rel: Optional[Tuple[int, int, int, int]],
    recycle_bbox_rel: Optional[Tuple[int, int, int, int]],
    context: ActionExecutionContext,
) -> str:
    if decision is None:
        if not item_name:
            if infobox_rect is None:
                return "UNREADABLE_NO_INFOBOX"
            if infobox_ocr is None:
                return "UNREADABLE_NO_OCR"
            if infobox_ocr.ocr_failed:
                return "UNREADABLE_OCR_FAILED"
            return "UNREADABLE_TITLE"
        if not actions:
            return "SKIP_NO_ACTION_MAP"
        return "SKIP_UNLISTED"

    if decision == "KEEP":
        return "KEEP"
    if decision == "SELL":
        return _apply_destructive_decision(
            decision=decision,
            infobox_rect=infobox_rect,
            infobox_ocr=infobox_ocr,
            action_bbox_rel=sell_bbox_rel,
            context=context,
        )
    if decision == "RECYCLE":
        return _apply_destructive_decision(
            decision=decision,
            infobox_rect=infobox_rect,
            infobox_ocr=infobox_ocr,
            action_bbox_rel=recycle_bbox_rel,
            context=context,
        )
    return "SCAN_ONLY"


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
