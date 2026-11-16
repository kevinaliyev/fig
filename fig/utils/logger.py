"""Audit Logging Engine for Fig.
Writes structured timestamped logs to ~/.fig/logs/fig.log and system redundancy
logs for system-level operations.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fig.config.state import get_fig_home, get_system_fig_root


def get_user_log_file() -> Path:
    """Return path to user audit log file (~/.fig/logs/fig.log)."""
    logs_dir = get_fig_home() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / "fig.log"


def get_system_log_file() -> Optional[Path]:
    """Return path to system-level redundancy log file if writable."""
    try:
        sys_logs_dir = get_system_fig_root() / "logs"
        sys_logs_dir.mkdir(parents=True, exist_ok=True)
        return sys_logs_dir / "system_fig.log"
    except (PermissionError, OSError):
        return None


def log_event(message: str, is_system: bool = False, level: str = "INFO") -> None:
    """Write an entry to the audit log."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = "[SYSTEM]" if is_system else "[USER]"
    log_line = f"[{now_str}] [{level:<5}] {prefix} {message}\n"

    # 1. Always append to user log
    try:
        user_log = get_user_log_file()
        with open(user_log, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass

    # 2. If system operation, also append to system redundancy log
    if is_system:
        sys_log = get_system_log_file()
        if sys_log:
            try:
                with open(sys_log, "a", encoding="utf-8") as f:
                    f.write(log_line)
            except Exception:
                pass


def log_operation(
    action: str,
    status: str = "OK",
    details: Optional[str] = None,
    is_system: bool = False,
    level: str = "INFO",
) -> None:
    """Convenience helper to record standardized operational events."""
    msg = f"{action.upper()} [{status}]"
    if details:
        msg += f" — {details}"
    log_event(msg, is_system=is_system, level=level)
