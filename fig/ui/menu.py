"""Interactive Menu and Popup Selector Subsystem for Fig.
Provides zero-dependency ANSI-bordered popup menus with arrow navigation,
direct number shortcuts, and automatic fallback for non-interactive environments.
"""

from __future__ import annotations

import sys
import os
from typing import List, Tuple, Optional, Union

from fig.ui.ansi import (
    colors_enabled,
    visible_len,
    c_bold,
    c_cyan,
    c_green,
    c_dim,
    c_yellow,
)


def read_single_key() -> str:
    """Read a single keypress without waiting for Enter across Windows, Linux, and macOS.
    Returns: 'up', 'down', 'left', 'right', 'enter', 'escape', 'ctrl_c', or the character typed.
    """
    if sys.platform.startswith("win"):
        import msvcrt

        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            ch2 = msvcrt.getwch()
            if ch2 == "H":
                return "up"
            if ch2 == "P":
                return "down"
            if ch2 == "K":
                return "left"
            if ch2 == "M":
                return "right"
            return f"ext_{ch2}"
        if ch in ("\r", "\n"):
            return "enter"
        if ch == "\x1b":
            return "escape"
        if ch == "\x03":
            return "ctrl_c"
        return ch

    # POSIX (Linux / macOS)
    import termios
    import tty
    import select

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            # Check if an escape sequence follows
            r, _, _ = select.select([sys.stdin], [], [], 0.08)
            if r:
                seq = sys.stdin.read(2)
                if seq == "[A":
                    return "up"
                if seq == "[B":
                    return "down"
                if seq == "[C":
                    return "right"
                if seq == "[D":
                    return "left"
            return "escape"
        if ch in ("\r", "\n"):
            return "enter"
        if ch == "\x03":
            return "ctrl_c"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def format_popup_box(
    title: str,
    items: List[Tuple[str, str]],
    selected_idx: int,
    width: int = 68,
) -> List[str]:
    """Render a styled ANSI box for an interactive popup selector."""
    use_color = colors_enabled()
    lines: List[str] = []

    # Box title header
    clean_title = f" {title} "
    dash_len = max(2, width - len(clean_title) - 4)
    top_line = f"┌──{c_cyan(clean_title, bold=True) if use_color else clean_title}{'─' * dash_len}┐"
    lines.append(top_line)

    # Menu items
    for idx, (label, desc) in enumerate(items):
        is_sel = (idx == selected_idx)
        cursor = ">" if is_sel else " "
        num_str = f"{idx + 1:>2}."
        
        # Build visible text
        core_label = f"{cursor} {num_str} {label}"
        desc_str = f" ({desc})" if desc else ""
        content = f"{core_label}{desc_str}"
        
        # Truncate if exceeding box width
        vis_w = visible_len(content)
        max_content_w = width - 4
        if vis_w > max_content_w:
            content = content[: max_content_w - 3] + "..."
            vis_w = max_content_w

        padding = " " * (width - 4 - vis_w)

        if is_sel and use_color:
            formatted_item = f"│ {c_green(content + padding, bold=True)} │"
        elif is_sel:
            formatted_item = f"│ {content}{padding} │"
        elif desc and use_color:
            # Dim the description when unselected
            label_part = f"  {num_str} {label}"
            desc_part = f" {c_dim(f'({desc})')}"
            pad = " " * (width - 4 - visible_len(label_part + desc_part))
            formatted_item = f"│ {label_part}{desc_part}{pad} │"
        else:
            formatted_item = f"│ {content}{padding} │"

        lines.append(formatted_item)

    # Footer separator & navigation key
    lines.append(f"│{' ' * (width - 2)}│")
    hint = "[↑/↓] Move  [Enter] Select  [Esc] Cancel  [1-9] Shortcut"
    hint_pad = " " * max(0, width - 4 - len(hint))
    hint_line = f"│ {c_dim(hint) if use_color else hint}{hint_pad} │"
    lines.append(hint_line)
    lines.append(f"└{'─' * (width - 2)}┘")

    return lines


def interactive_select(
    title: str,
    options: Sequence[Union[str, Tuple[str, str]]],
    default_idx: int = 0,
    width: Optional[int] = None,
) -> Optional[int]:
    """Display an interactive scrollable menu or popup and return selected index (0-based).
    Returns None if user cancels (Esc, 'q', or Ctrl+C).
    Automatically falls back to numbered prompt input if stdin is not a TTY (tests, pipes).
    """
    if not options:
        return None

    # Normalize options to List[Tuple[label, desc]]
    norm_items: List[Tuple[str, str]] = []
    for opt in options:
        if isinstance(opt, tuple):
            norm_items.append((str(opt[0]), str(opt[1])))
        else:
            norm_items.append((str(opt), ""))

    total_items = len(norm_items)
    selected_idx = max(0, min(default_idx, total_items - 1))

    # Calculate optimal box width
    max_label_w = max(visible_len(lbl) + (visible_len(dsc) + 3 if dsc else 0) for lbl, dsc in norm_items)
    title_w = visible_len(title)
    box_width = width or max(60, min(90, max(max_label_w + 12, title_w + 10)))

    # Non-interactive / piped / testing fallback
    if not sys.stdin.isatty():
        print(f"\n--- {title} ---")
        for idx, (label, desc) in enumerate(norm_items):
            desc_part = f" ({desc})" if desc else ""
            default_marker = " [DEFAULT]" if idx == selected_idx else ""
            print(f"  {idx + 1}. {label}{desc_part}{default_marker}")
        try:
            val = input(f"Choose option [1-{total_items}] (default: {selected_idx + 1}): ").strip()
            if not val:
                return selected_idx
            choice_num = int(val) - 1
            if 0 <= choice_num < total_items:
                return choice_num
            return None
        except (ValueError, EOFError, KeyboardInterrupt):
            return selected_idx

    # Interactive TTY Loop
    rendered_lines = format_popup_box(title, norm_items, selected_idx, width=box_width)
    sys.stdout.write("\n".join(rendered_lines) + "\n")
    sys.stdout.flush()
    box_height = len(rendered_lines)

    while True:
        try:
            key = read_single_key()
        except (EOFError, KeyboardInterrupt):
            key = "escape"

        if key in ("up", "k"):
            selected_idx = (selected_idx - 1) % total_items
        elif key in ("down", "j"):
            selected_idx = (selected_idx + 1) % total_items
        elif key == "enter":
            # Clear popup from screen cleanly
            sys.stdout.write(f"\x1b[{box_height}A")
            for _ in range(box_height):
                sys.stdout.write("\x1b[2K\n")
            sys.stdout.write(f"\x1b[{box_height}A")
            sys.stdout.flush()
            return selected_idx
        elif key in ("escape", "q", "ctrl_c"):
            # Clear popup on cancellation
            sys.stdout.write(f"\x1b[{box_height}A")
            for _ in range(box_height):
                sys.stdout.write("\x1b[2K\n")
            sys.stdout.write(f"\x1b[{box_height}A")
            sys.stdout.flush()
            return None
        elif key.isdigit():
            digit_val = int(key) - 1
            if 0 <= digit_val < total_items:
                selected_idx = digit_val
                # Instant selection on number key
                sys.stdout.write(f"\x1b[{box_height}A")
                for _ in range(box_height):
                    sys.stdout.write("\x1b[2K\n")
                sys.stdout.write(f"\x1b[{box_height}A")
                sys.stdout.flush()
                return selected_idx

        # Redraw in place
        sys.stdout.write(f"\x1b[{box_height}A")
        updated_lines = format_popup_box(title, norm_items, selected_idx, width=box_width)
        for line in updated_lines:
            sys.stdout.write(f"\r\x1b[2K{line}\n")
        sys.stdout.flush()
