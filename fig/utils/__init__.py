"""Fig Shared Utilities: Logging, Elevation, Git Cloning, and Cleanup."""

from fig.utils.logger import log_event, log_operation
from fig.utils.elevation import is_elevated, display_breaking_changes_warning, request_elevation
from fig.utils.git_clone import is_git_url, normalize_git_url, clone_remote_repo
from fig.utils.cleanup import CleanupManager
