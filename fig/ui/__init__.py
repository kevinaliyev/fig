"""Fig Terminal UI, Interactive Menus, and Template Viewer."""

from fig.ui.ansi import (
    colors_enabled,
    visible_len,
    strip_ansi,
    color,
    clear_screen,
    render_banner,
    render_warning_banner,
    format_table,
    format_box,
)
from fig.ui.menu import interactive_select, format_popup_box
from fig.ui.viewer import view_template, edit_template, list_templates, format_template_view, resolve_template_target
