"""Fig Configuration, State, Platform Detection, and Presets."""

from fig.config.state import FigState, get_fig_home, get_system_fig_root
from fig.config.platform import CURRENT_OS, OperatingSystem, expand_pathspec_shorthand
from fig.config.template import Template, ResolvedLink, discover_template, generate_default_template
