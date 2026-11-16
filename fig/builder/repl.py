"""Interactive Builder REPL Loop.
Handles command parsing, directory takeover navigation, toggling,
packaging (pack/unpack), remapping, link modes, and OS scope assignment.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Tuple

from fig.config.platform import expand_pathspec_shorthand
from fig.builder.scanner import DiscoveredConfig
from fig.ui.menu import interactive_select
from fig.ui.ansi import (
    render_banner,
    clear_screen,
    badge_ok,
    c_cyan,
    c_green,
    c_yellow,
    c_dim,
)
from fig.builder.render import (
    ask_input,
    parse_indices,
    get_pathspec_suggestions,
    set_exclusion_recursive,
    mark_ancestors_unpacked,
    get_scope_path_str,
    collect_active_tree_items,
    format_tree_lines,
    render_help_modal,
    render_scoped_view,
    render_full_repo_tree,
)


def run_builder_repl(
    root_items: List[DiscoveredConfig],
    interactive: bool = True,
    is_system: bool = False,
) -> List[DiscoveredConfig]:
    """Interactive REPL allowing user to review, navigate directories via 'cd' or 'ex',
    batch-toggle exclusions, view directory trees, and edit mappings.
    """
    if not interactive or not sys.stdin.isatty():
        return root_items

    nav_stack: List[DiscoveredConfig] = []
    status_msg: Optional[str] = None

    def redraw(msg: Optional[str] = None) -> Tuple[str, List[DiscoveredConfig]]:
        nonlocal view_text, item_lookup, status_msg
        status_msg = msg
        if sys.stdout.isatty():
            clear_screen()
        view_text, item_lookup = render_scoped_view(
            root_items, nav_stack, is_system=is_system, status_msg=status_msg
        )
        print(view_text)
        return view_text, item_lookup

    if sys.stdout.isatty():
        clear_screen()
    view_text, item_lookup = render_scoped_view(root_items, nav_stack, is_system=is_system)
    print(view_text)

    while True:
        path_str = get_scope_path_str(nav_stack)
        try:
            prompt_name = f"{c_cyan('fig builder', bold=True)} {c_dim('(' + path_str + ')')} {c_cyan('>')}"
            cmd_line = input(f"{prompt_name} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBuilder cancelled.")
            break

        if not cmd_line:
            continue

        parts = cmd_line.split()
        verb = parts[0].lower()

        # 1. DIRECT NUMBER INPUT (e.g. "1" or "1 3 5" to toggle)
        if verb.lstrip("#").isdigit():
            indices = parse_indices(parts, len(item_lookup))
            changed = []
            for idx in indices:
                target_item = item_lookup[idx]
                target_item.is_excluded = not target_item.is_excluded
                set_exclusion_recursive(target_item, target_item.is_excluded)
                target_item.customized = True
                if nav_stack:
                    mark_ancestors_unpacked(nav_stack, unexclude=not target_item.is_excluded)
                st = c_dim("EXCLUDED [ ]") if target_item.is_excluded else c_green("INCLUDED [x]", bold=True)
                changed.append(f"#{idx+1} ({target_item.app_name}): {st}")
            redraw(f"{badge_ok('TOGGLED')} " + " · ".join(changed) if changed else None)
            continue

        # 2. TOGGLE COMMAND
        if verb in ("toggle", "t"):
            indices = parse_indices(parts[1:], len(item_lookup))
            changed = []
            for idx in indices:
                target_item = item_lookup[idx]
                target_item.is_excluded = not target_item.is_excluded
                set_exclusion_recursive(target_item, target_item.is_excluded)
                target_item.customized = True
                if nav_stack:
                    mark_ancestors_unpacked(nav_stack, unexclude=not target_item.is_excluded)
                st = c_dim("EXCLUDED [ ]") if target_item.is_excluded else c_green("INCLUDED [x]", bold=True)
                changed.append(f"#{idx+1} ({target_item.app_name}): {st}")
            redraw(f"{badge_ok('TOGGLED')} " + " · ".join(changed) if changed else None)

        # 2b. ONLY COMMAND (keep specified items active, exclude all others in scope)
        elif verb == "only":
            indices = parse_indices(parts[1:], len(item_lookup))
            if not indices:
                redraw(c_yellow("Usage: only <# ...> (e.g. 'only 1 2 3' to keep specified items active)"))
                continue
            kept_ids = {id(item_lookup[idx]) for idx in indices}
            for item in item_lookup:
                if id(item) in kept_ids:
                    item.is_excluded = False
                    item.customized = True
                else:
                    set_exclusion_recursive(item, True)
                    item.customized = True
            if nav_stack:
                mark_ancestors_unpacked(nav_stack, unexclude=True)
            redraw(f"{badge_ok('KEPT')} Only #{', #'.join(str(i+1) for i in sorted(indices))}. Excluded all other items in current scope.")

        # 2c. UNPACK / FILES / SPLIT COMMAND
        elif verb in ("unpack", "files", "split", "ungroup"):
            if len(parts) > 1:
                target_arg = parts[1]
                matched = None
                if target_arg.lstrip("#").isdigit():
                    idx_val = int(target_arg.lstrip("#")) - 1
                    if 0 <= idx_val < len(item_lookup):
                        matched = item_lookup[idx_val]
                else:
                    t_name = target_arg.strip("/").lower()
                    scope_list = nav_stack[-1].children if nav_stack else root_items
                    for cand in scope_list:
                        if cand.is_directory and (cand.app_name.lower() == t_name or Path(cand.source_rel).name.lower() == t_name):
                            matched = cand
                            break
                if matched:
                    if matched.is_directory:
                        matched.link_as_dir = False
                        matched.force_pack = False
                        matched.customized = True
                        redraw(f"{badge_ok('UNPACKED')} '{matched.app_name}'. It will now link individual files instead of the directory.")
                    else:
                        redraw(c_yellow(f"'{matched.app_name}' is a file, cannot unpack."))
                else:
                    redraw(c_yellow(f"Directory '{target_arg}' not found."))
            else:
                if nav_stack:
                    curr = nav_stack[-1]
                    curr.link_as_dir = False
                    curr.force_pack = False
                    curr.customized = True
                    redraw(f"{badge_ok('UNPACKED')} Current directory '{curr.app_name}'. It will now link individual files instead of the directory.")
                else:
                    redraw(c_yellow("Usage: unpack <# | name> (e.g. 'unpack 1' or 'unpack pwsh')"))

        # 2d. PACK / DIR / GROUP COMMAND
        elif verb in ("pack", "dir", "group"):
            if len(parts) > 1:
                target_arg = parts[1]
                matched = None
                if target_arg.lstrip("#").isdigit():
                    idx_val = int(target_arg.lstrip("#")) - 1
                    if 0 <= idx_val < len(item_lookup):
                        matched = item_lookup[idx_val]
                else:
                    t_name = target_arg.strip("/").lower()
                    scope_list = nav_stack[-1].children if nav_stack else root_items
                    for cand in scope_list:
                        if cand.is_directory and (cand.app_name.lower() == t_name or Path(cand.source_rel).name.lower() == t_name):
                            matched = cand
                            break
                if matched:
                    if matched.is_directory:
                        matched.link_as_dir = True
                        matched.force_pack = True
                        matched.customized = True
                        redraw(f"{badge_ok('PACKED')} '{matched.app_name}'. It will now link as a whole directory root.")
                    else:
                        redraw(c_yellow(f"'{matched.app_name}' is a file, cannot pack."))
                else:
                    redraw(c_yellow(f"Directory '{target_arg}' not found."))
            else:
                if nav_stack:
                    curr = nav_stack[-1]
                    curr.link_as_dir = True
                    curr.force_pack = True
                    curr.customized = True
                    redraw(f"{badge_ok('PACKED')} Current directory '{curr.app_name}'. It will now link as a whole directory root.")
                else:
                    redraw(c_yellow("Usage: pack <# | name> (e.g. 'pack 1' or 'pack pwsh')"))

        # 3. DIRECTORY NAVIGATION (cd / ex / expand / open)
        elif verb in ("cd", "ex", "expand", "open"):
            if len(parts) < 2:
                redraw(c_dim(f"Current location: {path_str}. Usage: 'cd <# | name>' (e.g. 'cd 1', 'cd pwsh') or 'cd ..'"))
                continue

            target_arg = parts[1]

            # Go up one level
            if target_arg in ("..", "back", "up"):
                if nav_stack:
                    popped = nav_stack.pop()
                    msg = f"{badge_ok('NAVIGATED')} Returned to {'/' if not nav_stack else nav_stack[-1].app_name + '/'}"
                else:
                    msg = c_dim("Already at repository root (/).")
                redraw(msg)
                continue

            # Go to root
            if target_arg in ("/", "root", "~", "home"):
                nav_stack.clear()
                redraw(f"{badge_ok('NAVIGATED')} Returned to repository root (/).")
                continue

            # Navigate by index
            if target_arg.lstrip("#").isdigit():
                idx_val = int(target_arg.lstrip("#")) - 1
                if 0 <= idx_val < len(item_lookup):
                    candidate = item_lookup[idx_val]
                    if candidate.is_directory:
                        nav_stack.append(candidate)
                        candidate.is_expanded = True
                        redraw(f"{badge_ok('NAVIGATED')} Into {candidate.app_name}/")
                    else:
                        redraw(c_yellow(f"Item #{idx_val+1} ({candidate.app_name}) is a file. Use 'edit {idx_val+1}' to remap."))
                else:
                    redraw(c_yellow(f"Index #{target_arg} out of range (1..{len(item_lookup)})."))
                continue

            # Navigate by folder name
            target_name = target_arg.strip("/").lower()
            scope_items = nav_stack[-1].children if nav_stack else root_items
            match = None
            for item in scope_items:
                if item.is_directory and (item.app_name.lower() == target_name or Path(item.source_rel).name.lower() == target_name):
                    match = item
                    break

            if match:
                nav_stack.append(match)
                match.is_expanded = True
                redraw(f"{badge_ok('NAVIGATED')} Into {match.app_name}/")
            else:
                redraw(c_yellow(f"Directory '{target_arg}' not found in current folder."))

        # 4. GO BACK / UP ALIASES
        elif verb in ("back", "up"):
            if nav_stack:
                popped = nav_stack.pop()
                msg = f"{badge_ok('NAVIGATED')} Returned to {'/' if not nav_stack else nav_stack[-1].app_name + '/'}"
            else:
                msg = c_dim("Already at repository root (/).")
            redraw(msg)

        # 5. TREE VIEW COMMAND
        elif verb == "tree":
            if sys.stdout.isatty():
                clear_screen()
                if nav_stack:
                    print(render_banner(f"Tree View — {path_str}", width=95))
                    active_items_tr: List[DiscoveredConfig] = []
                    ex_items_tr: List[DiscoveredConfig] = []
                    collect_active_tree_items(nav_stack[-1], active_items_tr, ex_items_tr, is_root_call=True)
                    active_indices = {id(it): idx for idx, it in enumerate(active_items_tr, 1)}
                    tree_lines = format_tree_lines(nav_stack[-1], active_indices, prefix="", is_last=True, is_top=True)
                    print("\n".join(tree_lines))
                else:
                    print(render_full_repo_tree(root_items))
                try:
                    input(f"\n  {c_dim('Press [Enter] to return to template builder...')}")
                except (EOFError, KeyboardInterrupt):
                    pass
                redraw(None)
            else:
                if nav_stack:
                    print(render_banner(f"Tree View — {path_str}", width=90))
                    active_items_tr = []
                    ex_items_tr = []
                    collect_active_tree_items(nav_stack[-1], active_items_tr, ex_items_tr, is_root_call=True)
                    active_indices = {id(it): idx for idx, it in enumerate(active_items_tr, 1)}
                    tree_lines = format_tree_lines(nav_stack[-1], active_indices, prefix="", is_last=True, is_top=True)
                    print("\n".join(tree_lines))
                else:
                    print(render_full_repo_tree(root_items))

        # 6. EXCLUDE COMMANDS
        elif verb in ("exclude", "exc", "skip", "rm"):
            changed = []
            warnings = []
            for tok in parts[1:]:
                if tok.lstrip("#").isdigit():
                    idx_val = int(tok.lstrip("#")) - 1
                    if 0 <= idx_val < len(item_lookup):
                        target_item = item_lookup[idx_val]
                        set_exclusion_recursive(target_item, True)
                        target_item.customized = True
                        if nav_stack:
                            mark_ancestors_unpacked(nav_stack, unexclude=False)
                        changed.append(f"#{idx_val+1} ({target_item.app_name})")
                    else:
                        warnings.append(f"Index #{tok} out of range (1..{len(item_lookup)})")
                else:
                    t_name = tok.strip("/").lower()
                    scope_list = nav_stack[-1].children if nav_stack else root_items
                    matched = False
                    for cand in scope_list:
                        if cand.app_name.lower() == t_name or Path(cand.source_rel).name.lower() == t_name:
                            set_exclusion_recursive(cand, True)
                            cand.customized = True
                            if nav_stack:
                                mark_ancestors_unpacked(nav_stack, unexclude=False)
                            matched = True
                            changed.append(f"'{cand.app_name}'")
                    if not matched:
                        warnings.append(f"'{tok}' not found")
            msg_parts = []
            if changed:
                msg_parts.append(f"{badge_ok('EXCLUDED')} " + ", ".join(changed))
            if warnings:
                msg_parts.append(c_yellow(f"Warning: {', '.join(warnings)}."))
            redraw(" · ".join(msg_parts) if msg_parts else None)

        # 7. INCLUDE COMMANDS
        elif verb in ("include", "inc"):
            changed = []
            warnings = []
            for tok in parts[1:]:
                if tok.lstrip("#").isdigit():
                    idx_val = int(tok.lstrip("#")) - 1
                    if 0 <= idx_val < len(item_lookup):
                        target_item = item_lookup[idx_val]
                        set_exclusion_recursive(target_item, False)
                        target_item.customized = True
                        if nav_stack:
                            mark_ancestors_unpacked(nav_stack, unexclude=True)
                        changed.append(f"#{idx_val+1} ({target_item.app_name})")
                    else:
                        warnings.append(f"Index #{tok} out of range (1..{len(item_lookup)})")
                else:
                    t_name = tok.strip("/").lower()
                    scope_list = nav_stack[-1].children if nav_stack else root_items
                    matched = False
                    for cand in scope_list:
                        if cand.app_name.lower() == t_name or Path(cand.source_rel).name.lower() == t_name:
                            set_exclusion_recursive(cand, False)
                            cand.customized = True
                            if nav_stack:
                                mark_ancestors_unpacked(nav_stack, unexclude=True)
                            matched = True
                            changed.append(f"'{cand.app_name}'")
                    if not matched:
                        warnings.append(f"'{tok}' not found")
            msg_parts = []
            if changed:
                msg_parts.append(f"{badge_ok('INCLUDED')} " + ", ".join(changed))
            if warnings:
                msg_parts.append(c_yellow(f"Warning: {', '.join(warnings)}."))
            redraw(" · ".join(msg_parts) if msg_parts else None)

        # 8. INCLUDE-ALL / EXCLUDE-ALL
        elif verb in ("all", "include-all"):
            scope_items = nav_stack[-1].children if nav_stack else root_items
            for it in scope_items:
                set_exclusion_recursive(it, False)
                it.customized = True
            if nav_stack:
                mark_ancestors_unpacked(nav_stack, unexclude=True)
            redraw(f"{badge_ok('INCLUDED ALL')} Items in {path_str}.")

        elif verb in ("none", "exclude-all"):
            scope_items = nav_stack[-1].children if nav_stack else root_items
            for it in scope_items:
                set_exclusion_recursive(it, True)
                it.customized = True
            redraw(f"{badge_ok('EXCLUDED ALL')} Items in {path_str}.")

        # 9. EDIT / REMAP DESTINATION
        elif verb in ("edit", "e", "remap"):
            if len(parts) > 2 and parts[1].lstrip("#").isdigit():
                idx_val = int(parts[1].lstrip("#")) - 1
                if 0 <= idx_val < len(item_lookup):
                    item = item_lookup[idx_val]
                    chosen = expand_pathspec_shorthand(parts[2])
                    item.dest_expr = chosen
                    item.customized = True
                    item.is_excluded = False
                    redraw(f"{badge_ok('UPDATED')} {item.source_rel} -> {chosen}")
                else:
                    redraw(c_yellow(f"Index #{parts[1]} out of range (1..{len(item_lookup)})."))
                continue

            indices = parse_indices(parts[1:], len(item_lookup))
            if not indices:
                redraw(c_yellow("Usage: edit <#> [dest] (e.g. 'edit 2' or 'edit 2 ~/.config/nvim')"))
                continue
            last_msg = None
            for idx in indices:
                item = item_lookup[idx]
                suggestions = get_pathspec_suggestions(item)
                if suggestions:
                    options = [(str(s), getattr(s, "desc", "")) for s in suggestions]
                    options.append(("Custom...", "Type custom destination manually"))
                    sel = interactive_select(f"Select Destination: [{item.app_name}]", options)
                    if sel is not None:
                        if sel == len(options) - 1:
                            new_dest = ask_input(f"Enter custom destination for {item.app_name}")
                            if new_dest:
                                chosen = expand_pathspec_shorthand(new_dest)
                                item.dest_expr = chosen
                                item.customized = True
                                item.is_excluded = False
                                last_msg = f"{badge_ok('UPDATED')} {item.source_rel} -> {chosen}"
                        else:
                            chosen = options[sel][0]
                            item.dest_expr = chosen
                            item.customized = True
                            item.is_excluded = False
                            last_msg = f"{badge_ok('UPDATED')} {item.source_rel} -> {chosen}"
                else:
                    new_dest = ask_input(f"Enter destination for {item.app_name} [{item.dest_expr}]", default=item.dest_expr)
                    if new_dest:
                        chosen = expand_pathspec_shorthand(new_dest)
                        item.dest_expr = chosen
                        item.customized = True
                        item.is_excluded = False
                        last_msg = f"{badge_ok('UPDATED')} {item.source_rel} -> {chosen}"
            redraw(last_msg)

        # 9b. LINK MODE COMMAND
        elif verb in ("mode", "linkmode"):
            if len(parts) > 1:
                target_arg = parts[1]
                idx_val = int(target_arg.lstrip("#")) - 1 if target_arg.lstrip("#").isdigit() else None
                matched_item = item_lookup[idx_val] if (idx_val is not None and 0 <= idx_val < len(item_lookup)) else None
                if not matched_item:
                    redraw(c_yellow(f"Item '{target_arg}' not found."))
                    continue

                if len(parts) > 2:
                    new_mode = parts[2].lower()
                    if new_mode in ("auto", "symlink", "junction", "hardlink", "copy"):
                        matched_item.link_mode = new_mode if new_mode != "auto" else None
                        matched_item.customized = True
                        redraw(f"{badge_ok('MODE')} Set for '{matched_item.app_name}' to [{new_mode}].")
                    else:
                        redraw(c_yellow(f"Invalid mode '{new_mode}'. Valid: auto, symlink, junction, hardlink, copy."))
                else:
                    mode_options = [
                        ("auto", "Decided automatically based on OS & permissions"),
                        ("symlink", "Symbolic link (cross-platform standard)"),
                        ("junction", "NTFS Directory Junction (Windows directory link)"),
                        ("hardlink", "Hard link (single file mirror)"),
                        ("copy", "Physical byte-copy duplicate"),
                    ]
                    sel = interactive_select(f"Select Link Mode: [{matched_item.app_name}]", mode_options)
                    if sel is not None:
                        chosen_mode = mode_options[sel][0]
                        matched_item.link_mode = chosen_mode if chosen_mode != "auto" else None
                        matched_item.customized = True
                        redraw(f"{badge_ok('MODE')} Set for '{matched_item.app_name}' to [{chosen_mode}].")
            else:
                redraw(c_yellow("Usage: mode <# | name> [auto|symlink|junction|hardlink|copy]"))

        # 9c. OS TARGET SCOPE COMMAND
        elif verb in ("os", "platform"):
            if len(parts) > 1:
                target_arg = parts[1]
                idx_val = int(target_arg.lstrip("#")) - 1 if target_arg.lstrip("#").isdigit() else None
                matched_item = item_lookup[idx_val] if (idx_val is not None and 0 <= idx_val < len(item_lookup)) else None
                if not matched_item:
                    redraw(c_yellow(f"Item '{target_arg}' not found."))
                    continue

                if len(parts) > 2:
                    raw_os = parts[2].lower()
                    if raw_os in ("universal", "all", "univ", "none", "*"):
                        matched_item.os_target = None
                    elif raw_os in ("windows", "win", "win32"):
                        matched_item.os_target = "windows"
                    elif raw_os in ("linux", "gnu/linux"):
                        matched_item.os_target = "linux"
                    elif raw_os in ("macos", "darwin", "osx", "mac"):
                        matched_item.os_target = "macos"
                    elif raw_os in ("posix", "unix"):
                        matched_item.os_target = "posix"
                    else:
                        redraw(c_yellow(f"Invalid OS '{raw_os}'. Valid: universal, windows, linux, macos, posix."))
                        continue
                    matched_item.customized = True
                    redraw(f"{badge_ok('OS SCOPE')} Assigned '{matched_item.app_name}' to: {matched_item.os_target or 'Universal'}.")
                else:
                    os_options = [
                        ("Universal", "Active on all operating systems [mappings]"),
                        ("Windows", "os.windows.mappings - Windows only"),
                        ("Linux", "os.linux.mappings - Linux only"),
                        ("macOS", "os.macos.mappings - macOS only"),
                        ("POSIX", "os.posix.mappings - Linux & macOS"),
                    ]
                    sel = interactive_select(f"Assign OS Target Scope: [{matched_item.app_name}]", os_options)
                    if sel is not None:
                        os_map = [None, "windows", "linux", "macos", "posix"]
                        matched_item.os_target = os_map[sel]
                        matched_item.customized = True
                        redraw(f"{badge_ok('OS SCOPE')} Assigned '{matched_item.app_name}' to: {matched_item.os_target or 'Universal'}.")
            else:
                redraw(c_yellow("Usage: os <# | name> [universal|windows|linux|macos|posix]"))

        # 9d. COMMAND PALETTE POPUP (: or menu)
        elif verb in (":", "menu", "palette"):
            palette_options = [
                ("cd <folder>", "Navigate into directory package"),
                ("edit <#>", "Edit target destination / pick preset"),
                ("os <#>", "Assign operating system scope (Universal, Windows, POSIX)"),
                ("mode <#>", "Set link mode (symlink, junction, copy)"),
                ("pack <#>", "Pack folder to link as a whole directory"),
                ("unpack <#>", "Unpack folder to link individual files"),
                ("only <#>", "Keep only selected items active"),
                ("tree", "Display complete repository tree"),
                ("add", "Add a manual custom mapping"),
                ("help", "Open full command reference guide"),
                ("done", "Finalize, save template, and activate"),
                ("quit", "Exit builder without saving"),
            ]
            sel = interactive_select("Fig Builder — Command Palette", palette_options)
            if sel is not None:
                action_token = palette_options[sel][0].split()[0]
                if action_token == "help":
                    help_screen = render_help_modal()
                    if sys.stdout.isatty():
                        clear_screen()
                        print(help_screen)
                        try:
                            input(f"\n  {c_dim('Press [Enter] to return to template builder...')}")
                        except (EOFError, KeyboardInterrupt):
                            pass
                        redraw(None)
                    else:
                        print(help_screen)
                elif action_token == "tree":
                    if sys.stdout.isatty():
                        clear_screen()
                        if nav_stack:
                            active_items_tr = []
                            ex_items_tr = []
                            collect_active_tree_items(nav_stack[-1], active_items_tr, ex_items_tr, is_root_call=True)
                            active_indices = {id(it): idx for idx, it in enumerate(active_items_tr, 1)}
                            tree_lines = format_tree_lines(nav_stack[-1], active_indices, prefix="", is_last=True, is_top=True)
                            print("\n".join(tree_lines))
                        else:
                            print(render_full_repo_tree(root_items))
                        try:
                            input(f"\n  {c_dim('Press [Enter] to return to template builder...')}")
                        except (EOFError, KeyboardInterrupt):
                            pass
                        redraw(None)
                    else:
                        if nav_stack:
                            active_items_tr = []
                            ex_items_tr = []
                            collect_active_tree_items(nav_stack[-1], active_items_tr, ex_items_tr, is_root_call=True)
                            active_indices = {id(it): idx for idx, it in enumerate(active_items_tr, 1)}
                            tree_lines = format_tree_lines(nav_stack[-1], active_indices, prefix="", is_last=True, is_top=True)
                            print("\n".join(tree_lines))
                        else:
                            print(render_full_repo_tree(root_items))
                elif action_token == "done":
                    print("[OK] Finalizing configuration template...")
                    break
                elif action_token == "quit":
                    print("Aborted builder without saving.")
                    return []
                elif action_token == "add":
                    src = ask_input("Relative source path in repo")
                    dest = ask_input("Target destination expression")
                    if src and dest:
                        new_entry = DiscoveredConfig(
                            app_name=Path(src).stem,
                            source_rel=src,
                            dest_expr=expand_pathspec_shorthand(dest),
                            is_directory=False,
                            customized=True,
                        )
                        root_items.append(new_entry)
                        redraw(f"{badge_ok('ADDED')} Mapping: {src} -> {new_entry.dest_expr}")
                else:
                    target_arg = ask_input(f"Enter item number or name for '{action_token}'")
                    if target_arg:
                        sub_verb = action_token.lower()
                        if sub_verb == "cd":
                            if target_arg.lstrip("#").isdigit():
                                iv = int(target_arg.lstrip("#")) - 1
                                if 0 <= iv < len(item_lookup) and item_lookup[iv].is_directory:
                                    nav_stack.append(item_lookup[iv])
                                    redraw(f"{badge_ok('NAVIGATED')} Into {item_lookup[iv].app_name}/")
                        elif sub_verb == "edit":
                            iv = int(target_arg.lstrip("#")) - 1 if target_arg.lstrip("#").isdigit() else None
                            if iv is not None and 0 <= iv < len(item_lookup):
                                it = item_lookup[iv]
                                sugs = get_pathspec_suggestions(it)
                                opts = [(str(s), getattr(s, "desc", "")) for s in sugs]
                                opts.append(("Custom...", "Type custom destination manually"))
                                s_sel = interactive_select(f"Select Destination: [{it.app_name}]", opts)
                                if s_sel is not None:
                                    if s_sel == len(opts) - 1:
                                        nd = ask_input(f"Enter destination for {it.app_name}")
                                        if nd:
                                            it.dest_expr = expand_pathspec_shorthand(nd)
                                            it.customized = True
                                            redraw(f"{badge_ok('UPDATED')} {it.source_rel} -> {it.dest_expr}")
                                    else:
                                        it.dest_expr = opts[s_sel][0]
                                        it.customized = True
                                        redraw(f"{badge_ok('UPDATED')} {it.source_rel} -> {it.dest_expr}")
                        elif sub_verb == "os":
                            iv = int(target_arg.lstrip("#")) - 1 if target_arg.lstrip("#").isdigit() else None
                            if iv is not None and 0 <= iv < len(item_lookup):
                                it = item_lookup[iv]
                                os_opts = [
                                    ("Universal", "Active on all operating systems [mappings]"),
                                    ("Windows", "os.windows.mappings - Windows only"),
                                    ("Linux", "os.linux.mappings - Linux only"),
                                    ("macOS", "os.macos.mappings - macOS only"),
                                    ("POSIX", "os.posix.mappings - Linux & macOS"),
                                ]
                                o_sel = interactive_select(f"Assign OS: [{it.app_name}]", os_opts)
                                if o_sel is not None:
                                    it.os_target = [None, "windows", "linux", "macos", "posix"][o_sel]
                                    it.customized = True
                                    redraw(f"{badge_ok('OS SCOPE')} Assigned '{it.app_name}' to: {it.os_target or 'Universal'}.")
                        elif sub_verb == "mode":
                            iv = int(target_arg.lstrip("#")) - 1 if target_arg.lstrip("#").isdigit() else None
                            if iv is not None and 0 <= iv < len(item_lookup):
                                it = item_lookup[iv]
                                m_opts = [
                                    ("auto", "Decided automatically"),
                                    ("symlink", "Symbolic link"),
                                    ("junction", "NTFS Junction"),
                                    ("hardlink", "Hard link"),
                                    ("copy", "Physical copy"),
                                ]
                                m_sel = interactive_select(f"Select Link Mode: [{it.app_name}]", m_opts)
                                if m_sel is not None:
                                    cm = m_opts[m_sel][0]
                                    it.link_mode = cm if cm != "auto" else None
                                    it.customized = True
                                    redraw(f"{badge_ok('MODE')} Set for '{it.app_name}' to [{cm}].")
                        elif sub_verb == "pack":
                            iv = int(target_arg.lstrip("#")) - 1 if target_arg.lstrip("#").isdigit() else None
                            if iv is not None and 0 <= iv < len(item_lookup) and item_lookup[iv].is_directory:
                                item_lookup[iv].link_as_dir = True
                                item_lookup[iv].force_pack = True
                                redraw(f"{badge_ok('PACKED')} '{item_lookup[iv].app_name}'.")
                        elif sub_verb == "unpack":
                            iv = int(target_arg.lstrip("#")) - 1 if target_arg.lstrip("#").isdigit() else None
                            if iv is not None and 0 <= iv < len(item_lookup) and item_lookup[iv].is_directory:
                                item_lookup[iv].link_as_dir = False
                                item_lookup[iv].force_pack = False
                                redraw(f"{badge_ok('UNPACKED')} '{item_lookup[iv].app_name}'.")
            else:
                redraw(None)

        # 10. LIST / STATUS REPRINT
        elif verb in ("list", "ls", "status"):
            redraw(None)

        # 11. FINALIZE & SAVE
        elif verb in ("done", "save", "write", "finish"):
            print(f"\n[OK] Finalizing configuration template...")
            break

        # 12. QUIT / ABORT
        elif verb in ("quit", "q", "exit"):
            print("\nBuilder cancelled without saving.")
            return []

        # 13. ADD CUSTOM MAPPING
        elif verb == "add":
            src = ask_input("Relative source path in repo")
            dest = ask_input("Target destination expression (e.g. ~/.config/myapp or /etc/hosts)")
            if src and dest:
                expanded_dest = expand_pathspec_shorthand(dest)
                new_entry = DiscoveredConfig(
                    app_name=Path(src).stem,
                    source_rel=src,
                    dest_expr=expanded_dest,
                    is_directory=False,
                    is_system=is_system,
                    detection_source="manual pathspec",
                    customized=True,
                )
                if nav_stack:
                    nav_stack[-1].children.append(new_entry)
                    nav_stack[-1].child_count += 1
                else:
                    root_items.append(new_entry)
                redraw(f"{badge_ok('ADDED')} Mapping: {src} -> {expanded_dest}")

        # 14. HELP / COMMAND GUIDE
        elif verb in ("help", "?"):
            help_screen = render_help_modal()
            if sys.stdout.isatty():
                clear_screen()
                print(help_screen)
                try:
                    input(f"\n  {c_dim('Press [Enter] to return to template builder...')}")
                except (EOFError, KeyboardInterrupt):
                    pass
                redraw(None)
            else:
                print(help_screen)

        else:
            redraw(c_yellow(f"Unknown command '{parts[0]}'. Type '?' or 'help' for guide, ':' for menu."))

    return root_items


# ==============================================================================
# Template Assembler & Orchestration
