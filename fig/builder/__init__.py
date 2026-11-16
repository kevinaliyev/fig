"""Fig Interactive Template Builder, Scanner, and Wizard."""

from fig.builder.scanner import RepoScanner, DiscoveredConfig, KNOWN_CONFIG_DIRS, parse_pathspec_file
from fig.builder.render import (
    ask_input,
    ask_bool,
    parse_indices,
    PathSuggestion,
    get_pathspec_suggestions,
    get_visible_items,
    set_expansion,
    set_exclusion_recursive,
    get_all_leaf_items,
    is_package_customized,
    mark_ancestors_unpacked,
    get_scope_path_str,
    collect_active_tree_items,
    format_tree_lines,
    format_excluded_table,
    render_help_modal,
    render_scoped_view,
    render_full_repo_tree,
    format_discovered_table,
)
from fig.builder.repl import run_builder_repl
from fig.builder.assembler import (
    build_template_from_items,
    merge_existing_template_into_discovered,
    run_builder,
    run_rebuilder,
)
from fig.builder.wizard import run_interactive_wizard
