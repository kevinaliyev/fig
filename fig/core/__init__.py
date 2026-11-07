"""Fig Core Primitives & Low-Level Engines.
Contains config, platform, linker, backup, elevation, logger, template, and engine.
Higher-level feature modules reside in fig.modules.
"""

from fig.core.config import FigState, get_fig_home, get_system_fig_root
from fig.core.platform import CURRENT_OS, OperatingSystem
from fig.core.elevation import is_elevated, display_breaking_changes_warning, request_elevation
from fig.core.logger import log_event
from fig.core.linker import deploy_link, LinkMode, LinkStatus
from fig.core.backup import BackupSession, list_all_backups
from fig.core.template import Template
from fig.core.engine import FigEngine, EngineResult

# Backward-compatible re-exports from modules
from fig.modules.builder import run_builder
from fig.modules.scanner import RepoScanner, DiscoveredConfig
from fig.modules.viewer import view_template, edit_template, list_templates
from fig.modules.profiles import ProfileManager, BorrowSessionManager
from fig.modules.system import SystemConfigManager
from fig.modules.wizard import run_interactive_wizard
