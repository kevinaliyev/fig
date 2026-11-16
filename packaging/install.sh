#!/usr/bin/env sh
# ============================================================================
# Fig Binary Installation Script (POSIX)
# Copies fig from this release package to ~/.local/bin
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$SCRIPT_DIR/fig"

if [ ! -f "$SOURCE" ]; then
    echo "[ERROR] Could not find executable at $SOURCE"
    exit 1
fi

LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"

echo "[*] Installing fig to $LOCAL_BIN..."
cp "$SOURCE" "$LOCAL_BIN/fig"
chmod +x "$LOCAL_BIN/fig"
echo "[OK] Successfully installed to $LOCAL_BIN/fig"

# PATH check
case ":$PATH:" in
    *":$LOCAL_BIN:"*) ;;
    *)
        echo "[!] Notice: $LOCAL_BIN is not currently in your PATH."
        echo "    Add this to your ~/.bashrc or ~/.zshrc:"
        echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
        ;;
esac

echo ""
echo "============================================================================"
echo " Fig installation complete!"
echo "============================================================================"
echo "Test with: fig --version"
echo "============================================================================"
