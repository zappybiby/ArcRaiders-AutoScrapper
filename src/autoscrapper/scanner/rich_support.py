from __future__ import annotations

try:
    from rich import box
    from rich.align import Align
    from rich.console import Console, Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        Progress,
        ProgressColumn,
        SpinnerColumn,
        Task,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )
    from rich.table import Table
    from rich.text import Text
except ImportError:  # pragma: no cover - optional dependency
    Align = None
    Console = None
    Group = None
    Live = None
    Panel = None
    BarColumn = None
    Progress = None
    ProgressColumn = None
    SpinnerColumn = None
    Task = None
    TaskProgressColumn = None
    TextColumn = None
    TimeElapsedColumn = None
    TimeRemainingColumn = None
    Table = None
    Text = None
    box = None
