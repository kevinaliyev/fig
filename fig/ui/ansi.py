"""Terminal UI, Color, and Styling Engine for Fig.
Provides zero-dependency ANSI color formatting, status badges, banners,
and table rendering with automatic terminal capability detection.
"""

from __future__ import annotations

import os
import sys
import re
from typing import List, Optional, Tuple, Sequence

# Windows virtual terminal initialization flag
_VT_INITIALIZED = False


def _init_windows_console() -> bool:
    """Enable ANSI virtual terminal processing on Windows 10/11 console."""
    global _VT_INITIALIZED
    if _VT_INITIALIZED:
        return True
    if not sys.platform.startswith("win"):
        _VT_INITIALIZED = True
        return True

    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # STD_OUTPUT_HANDLE = -11
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        _VT_INITIALIZED = True
        return True
    except Exception:
        _VT_INITIALIZED = True
        return False


def colors_enabled() -> bool:
    """Check if color output is enabled and supported by the current terminal."""
    if "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb":
        return False
    if not sys.stdout.isatty():
        # Allow FORCE_COLOR override if specified in CI/testing
        return "FORCE_COLOR" in os.environ
    _init_windows_console()
    return True


# ANSI Escape Codes
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_UNDERLINE = "\033[4m"

_FG_RED = "\033[31m"
_FG_GREEN = "\033[32m"
_FG_YELLOW = "\033[33m"
_FG_BLUE = "\033[34m"
_FG_MAGENTA = "\033[35m"
_FG_CYAN = "\033[36m"
_FG_WHITE = "\033[37m"
_FG_GRAY = "\033[90m"

_BG_RED = "\033[41m"
_BG_GREEN = "\033[42m"
_BG_YELLOW = "\033[43m"
_BG_BLUE = "\033[44m"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def visible_len(text: str) -> int:
    """Return the visible character width of a string ignoring ANSI escape codes."""
    return len(_ANSI_RE.sub("", text))


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return _ANSI_RE.sub("", text)


def color(
    text: str,
    fg: Optional[str] = None,
    bold: bool = False,
    dim: bool = False,
    underline: bool = False,
) -> str:
    """Apply ANSI styling to text if color is enabled."""
    if not colors_enabled() or not text:
        return text

    codes = []
    if bold:
        codes.append(_BOLD)
    if dim:
        codes.append(_DIM)
    if underline:
        codes.append(_UNDERLINE)

    if fg == "red":
        codes.append(_FG_RED)
    elif fg == "green":
        codes.append(_FG_GREEN)
    elif fg == "yellow":
        codes.append(_FG_YELLOW)
    elif fg == "blue":
        codes.append(_FG_BLUE)
    elif fg == "magenta":
        codes.append(_FG_MAGENTA)
    elif fg == "cyan":
        codes.append(_FG_CYAN)
    elif fg == "white":
        codes.append(_FG_WHITE)
    elif fg == "gray":
        codes.append(_FG_GRAY)

    if not codes:
        return text

    return f"{''.join(codes)}{text}{_RESET}"


# Semantic helpers
def c_green(text: str, bold: bool = False) -> str:
    return color(text, "green", bold=bold)


def c_red(text: str, bold: bool = False) -> str:
    return color(text, "red", bold=bold)


def c_yellow(text: str, bold: bool = False) -> str:
    return color(text, "yellow", bold=bold)


def c_cyan(text: str, bold: bool = False) -> str:
    return color(text, "cyan", bold=bold)


def c_magenta(text: str, bold: bool = False) -> str:
    return color(text, "magenta", bold=bold)


def c_blue(text: str, bold: bool = False) -> str:
    return color(text, "blue", bold=bold)


def c_dim(text: str) -> str:
    return color(text, "gray", dim=True)


def c_bold(text: str) -> str:
    return color(text, bold=True)


# Status Badges
def badge_ok(label: str = "OK") -> str:
    return color(f"[{label}]", "green", bold=True)


def badge_created(label: str = "+") -> str:
    return color(f"[{label}]", "cyan", bold=True)


def badge_backed_up(label: str = "BACKUP") -> str:
    return color(f"[{label}]", "yellow", bold=True)


def badge_skipped(label: str = "EXCLUDED") -> str:
    return color(f"[{label}]", "gray", dim=True)


def badge_conflict(label: str = "CONFLICT") -> str:
    return color(f"[{label}]", "red", bold=True)


def badge_missing(label: str = "MISSING") -> str:
    return color(f"[{label}]", "yellow", bold=True)


def badge_active(is_active: bool) -> str:
    if is_active:
        return color("[x]", "green", bold=True)
    return color("[ ]", "gray", dim=True)


def badge_kind(is_dir: bool) -> str:
    if is_dir:
        return color("[dir] ", "blue", bold=False)
    return color("[file]", "magenta", bold=False)


def render_banner(title: str, subtitle: Optional[str] = None, width: int = 86) -> str:
    """Render a clean, modern header banner."""
    sep = "=" * width
    lines = [
        c_cyan(sep, bold=True),
        f" {c_bold(title)}",
    ]
    if subtitle:
        lines.append(f" {c_dim(subtitle)}")
    lines.append(c_cyan(sep, bold=True))
    return "\n".join(lines)


def render_warning_banner(title: str, subtitle: Optional[str] = None, width: int = 86) -> str:
    """Render a prominent alert/warning banner."""
    sep = "!" * width
    lines = [
        c_yellow(sep, bold=True),
        f" {c_yellow(c_bold(title))}",
    ]
    if subtitle:
        lines.append(f" {subtitle}")
    lines.append(c_yellow(sep, bold=True))
    return "\n".join(lines)


def format_table(
    headers: List[str],
    rows: Sequence[Sequence[str]],
    alignments: Optional[List[str]] = None,
    padding: int = 2,
) -> str:
    """Format tabular data cleanly, calculating widths based on visible text (ignoring ANSI)."""
    if not headers and not rows:
        return ""

    num_cols = len(headers) if headers else max(len(r) for r in rows)
    col_widths = [0] * num_cols

    for i, h in enumerate(headers):
        col_widths[i] = max(col_widths[i], visible_len(h))

    for row in rows:
        for i, cell in enumerate(row):
            if i < num_cols:
                col_widths[i] = max(col_widths[i], visible_len(cell))

    pad_str = " " * padding

    # Header line
    hdr_cells = []
    for i, h in enumerate(headers):
        w = col_widths[i]
        align = alignments[i] if alignments and i < len(alignments) else "left"
        cur_vlen = visible_len(h)
        spaces = max(0, w - cur_vlen)
        if align == "right":
            hdr_cells.append(" " * spaces + c_bold(h))
        else:
            hdr_cells.append(c_bold(h) + " " * spaces)
    
    header_line = pad_str.join(hdr_cells)
    divider_line = pad_str.join("-" * w for w in col_widths)

    out_lines = [header_line, c_dim(divider_line)]

    for row in rows:
        row_cells = []
        for i, cell in enumerate(row):
            if i >= num_cols:
                break
            w = col_widths[i]
            align = alignments[i] if alignments and i < len(alignments) else "left"
            cur_vlen = visible_len(cell)
            spaces = max(0, w - cur_vlen)
            if align == "right":
                row_cells.append(" " * spaces + cell)
            else:
                row_cells.append(cell + " " * spaces)
        out_lines.append(pad_str.join(row_cells))

    return "\n".join(out_lines)


def clear_screen() -> None:
    """Clear terminal screen and place cursor at home position if stdout is a TTY."""
    if sys.stdout.isatty():
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


def format_box(
    title: str,
    lines: Sequence[str],
    width: int = 90,
    color_name: str = "cyan",
) -> str:
    """Render text lines inside a modern framed box with a title."""
    title_vlen = visible_len(title)
    inner_width = max(width - 4, title_vlen + 6)

    top_border = f"┌── {title} " + "─" * max(0, inner_width - title_vlen - 5) + "┐"
    bottom_border = "└" + "─" * inner_width + "┘"

    out = [color(top_border, color_name, bold=True)]
    for line in lines:
        vlen = visible_len(line)
        pad = max(0, inner_width - vlen - 2)
        out.append(f"{color('│', color_name, bold=True)}  {line}{' ' * pad}{color('│', color_name, bold=True)}")
    out.append(color(bottom_border, color_name, bold=True))
    return "\n".join(out)

