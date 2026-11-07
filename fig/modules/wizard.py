"""Interactive Setup Wizard (REPL) for Fig.
Guides the user through simple questions to generate a starter fig.toml template.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

from fig.core.platform import CURRENT_OS, OperatingSystem
from fig.core.template import Template


def ask_choice(prompt: str, choices: List[str], default: str) -> str:
    """Prompt user for a choice among allowed options."""
    choices_str = "/".join(choices)
    while True:
        try:
            val = input(f"{prompt} [{choices_str}] (default: {default}): ").strip().lower()
            if not val:
                return default
            for c in choices:
                if c.lower() == val or c.lower().startswith(val):
                    return c
            print(f"Invalid choice '{val}'. Please choose from {choices_str}.")
        except (EOFError, KeyboardInterrupt):
            print("\nSetup cancelled.")
            return default


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    """Prompt user for yes/no question."""
    hint = "Y/n" if default else "y/N"
    while True:
        try:
            val = input(f"{prompt} [{hint}]: ").strip().lower()
            if not val:
                return default
            if val in ("y", "yes"):
                return True
            elif val in ("n", "no"):
                return False
            print("Please answer 'y' or 'n'.")
        except (EOFError, KeyboardInterrupt):
            print("\nSetup cancelled.")
            return default


def run_interactive_wizard(
    output_dir: Optional[Path] = None,
    interactive: bool = True,
    answers: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """Run interactive REPL setup to generate a starter fig.toml.
    The generated template is NOT registered as active yet.
    """
    target_dir = (output_dir or Path.cwd()).resolve()
    target_file = target_dir / "fig.toml"

    print("=" * 60)
    print("Welcome to Fig — Configuration & Dotfile Manager Setup")
    print(f"Detected Platform: {CURRENT_OS.value.capitalize()}")
    print("=" * 60)
    print("No active configuration found.")
    print("Let's generate a clean starter template for your dotfiles.\n")

    if target_file.exists():
        print(f"Note: '{target_file.name}' already exists in {target_dir}.")
        if interactive and not ask_yes_no("Overwrite existing template?", default=False):
            print("Setup aborted.")
            return target_file

    presets: List[str] = []
    mappings: Dict[str, str] = {}
    os_mappings: Dict[str, Dict[str, str]] = {}

    ans = answers or {}

    # 1. Shell selection
    if CURRENT_OS == OperatingSystem.WINDOWS:
        shell_default = "powershell"
        shell_choices = ["powershell", "bash", "zsh", "none"]
    else:
        shell_default = "zsh"
        shell_choices = ["zsh", "bash", "fish", "powershell", "none"]

    if interactive and "shell" not in ans:
        chosen_shell = ask_choice("Which primary shell do you use?", shell_choices, default=shell_default)
    else:
        chosen_shell = ans.get("shell", shell_default)

    if chosen_shell != "none":
        presets.append(chosen_shell)
        if chosen_shell == "zsh":
            mappings[".zshrc"] = "~/.zshrc"
        elif chosen_shell == "bash":
            mappings[".bashrc"] = "~/.bashrc"
        elif chosen_shell == "powershell":
            if CURRENT_OS == OperatingSystem.WINDOWS:
                os_mappings.setdefault("windows", {})["profile.ps1"] = "~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1"
            else:
                mappings["profile.ps1"] = "~/.config/powershell/Microsoft.PowerShell_profile.ps1"

    # 2. Git
    if interactive and "git" not in ans:
        use_git = ask_yes_no("Do you want to manage Git configuration (.gitconfig)?", default=True)
    else:
        use_git = ans.get("git", True)

    if use_git:
        presets.append("git")
        mappings[".gitconfig"] = "~/.gitconfig"

    # 3. SSH
    if interactive and "ssh" not in ans:
        use_ssh = ask_yes_no("Do you want to manage SSH client configuration (~/.ssh/config)?", default=True)
    else:
        use_ssh = ans.get("ssh", True)

    if use_ssh:
        presets.append("ssh")
        mappings["ssh_config"] = "~/.ssh/config"

    # 4. Text Editor
    editor_choices = ["neovim", "vim", "helix", "none"]
    if interactive and "editor" not in ans:
        chosen_editor = ask_choice("Which text editor do you use?", editor_choices, default="neovim")
    else:
        chosen_editor = ans.get("editor", "neovim")

    if chosen_editor != "none":
        presets.append(chosen_editor)
        if chosen_editor == "neovim":
            if CURRENT_OS == OperatingSystem.WINDOWS:
                os_mappings.setdefault("windows", {})["nvim"] = "%LOCALAPPDATA%/nvim"
            else:
                mappings["nvim"] = "~/.config/nvim"
        elif chosen_editor == "vim":
            mappings[".vimrc"] = "~/.vimrc"
        elif chosen_editor == "helix":
            mappings["helix"] = "~/.config/helix"

    # 5. Terminal Emulator
    terminal_choices = ["alacritty", "kitty", "wezterm", "none"]
    if CURRENT_OS == OperatingSystem.WINDOWS:
        terminal_choices.append("windows-terminal")

    if interactive and "terminal" not in ans:
        chosen_term = ask_choice("Which terminal emulator do you use?", terminal_choices, default="none")
    else:
        chosen_term = ans.get("terminal", "none")

    if chosen_term != "none":
        presets.append(chosen_term)
        if chosen_term == "alacritty":
            if CURRENT_OS == OperatingSystem.WINDOWS:
                os_mappings.setdefault("windows", {})["alacritty.toml"] = "%APPDATA%/alacritty/alacritty.toml"
            else:
                mappings["alacritty.toml"] = "~/.config/alacritty/alacritty.toml"
        elif chosen_term == "wezterm":
            mappings["wezterm.lua"] = "~/.config/wezterm/wezterm.lua"
        elif chosen_term == "windows-terminal":
            os_mappings.setdefault("windows", {})["wt_settings.json"] = "%LOCALAPPDATA%/Packages/Microsoft.WindowsTerminal_8wekyb3d8bbwe/LocalState/settings.json"

    tpl = Template(
        name="starter-dotfiles",
        description=f"Starter configuration generated for {CURRENT_OS.value}",
        link_mode="auto",
        backup_on_collision=True,
        mappings=mappings,
        presets=presets,
        os_mappings=os_mappings,
    )
    tpl.save(target_file)

    print("\n" + "=" * 60)
    print(f"[SUCCESS] Starter template created at: {target_file}")
    print("=" * 60)
    print("Next steps:")
    print("  1. Place your configuration files in this directory matching the template.")
    print("  2. Open fig.toml to tweak or add custom paths if desired.")
    print("  3. Run 'fig -bootstrap' (or 'fig bootstrap') to deploy your dotfiles!\n")

    return target_file
