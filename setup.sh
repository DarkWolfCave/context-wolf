#!/bin/bash
# ContextWolf - Setup Script
#
# Usage:
#   bash setup.sh                  # Full interactive setup (install + configure)
#   bash setup.sh --install-only   # Only install uv + dependencies
#   bash setup.sh --doctor         # Run diagnostics
#   bash setup.sh --init           # Configure database
#   bash setup.sh --setup-mcp      # Configure Claude Code MCP integration

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ============================================================
# Helper functions
# ============================================================

ensure_uv() {
    export PATH="$HOME/.local/bin:$PATH"

    if command -v uv &> /dev/null; then
        return 0
    fi

    echo "📦 uv not found. Installing..."
    echo ""
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"

    if command -v uv &> /dev/null; then
        echo ""
        echo "✅ uv installed: $(uv --version)"
    else
        echo "❌ uv installation failed."
        echo "   Manual install: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
}

install_deps() {
    echo "📦 Installing dependencies..."
    cd "$SCRIPT_DIR"
    uv sync --extra all 2>&1 | tail -5
    echo ""

    echo "📦 Installing cm globally..."
    # --reinstall (not --force): --force only replaces the tool installation
    # from uv's wheel cache. With a dynamic-version package (Hatch reads
    # src/version.py) the cached wheel can be stale, so --force will quietly
    # reinstall the previous version. --reinstall forces a fresh build.
    uv tool install --reinstall --from "$SCRIPT_DIR" context-wolf 2>&1 | tail -3
    echo ""

    # Verify against the global cm in PATH (uv tool's), not the local .venv
    # copy — the .venv copy is editable and would report the new version
    # even if the global install silently kept the old one.
    GLOBAL_CM="$HOME/.local/bin/cm"
    if [ ! -x "$GLOBAL_CM" ]; then
        GLOBAL_CM="$(command -v cm 2>/dev/null || true)"
    fi
    if [ -n "$GLOBAL_CM" ] && "$GLOBAL_CM" --version > /dev/null 2>&1; then
        VERSION=$("$GLOBAL_CM" --version 2>&1)
        echo "✅ $VERSION (installed at: $GLOBAL_CM)"
    else
        echo "❌ Installation failed - 'cm' not found on PATH."
        echo "   If ~/.local/bin is not on your PATH, add it:"
        echo "     export PATH=\"\$HOME/.local/bin:\$PATH\""
        exit 1
    fi
}

run_cm() {
    # Use local venv cm (always works, even if PATH not yet updated)
    "$SCRIPT_DIR/.venv/bin/cm" "$@"
}

# ============================================================
# Parameter handling
# ============================================================

case "${1:-}" in
    --doctor)
        ensure_uv
        run_cm doctor
        exit 0
        ;;
    --init)
        ensure_uv
        run_cm init
        exit 0
        ;;
    --setup-mcp)
        ensure_uv
        run_cm setup-mcp
        exit 0
        ;;
    --install-only)
        echo "🚀 ContextWolf - Install Only"
        echo ""
        ensure_uv
        install_deps
        echo ""
        echo "🎉 Done! Run 'bash setup.sh' (without flags) for full setup."
        exit 0
        ;;
    --help|-h)
        echo "ContextWolf - Setup Script"
        echo ""
        echo "Usage:"
        echo "  bash setup.sh                  Full interactive setup"
        echo "  bash setup.sh --install-only   Only install dependencies"
        echo "  bash setup.sh --doctor         Run diagnostics"
        echo "  bash setup.sh --init           Configure database"
        echo "  bash setup.sh --setup-mcp      Configure Claude Code MCP"
        echo "  bash setup.sh --help           Show this help"
        exit 0
        ;;
    "")
        # Full interactive setup - continue below
        ;;
    *)
        echo "❌ Unknown option: $1"
        echo "   Run: bash setup.sh --help"
        exit 1
        ;;
esac

# ============================================================
# Full interactive setup
# ============================================================

echo "🚀 ContextWolf - Setup"
echo ""

# Step 1: Install uv + dependencies
ensure_uv
echo ""
install_deps
echo ""

# Step 2: Database configuration
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
CONFIG_PATH="$HOME/.context/config.yaml"

if [ -f "$CONFIG_PATH" ]; then
    echo "✅ Database config found: $CONFIG_PATH"
    echo ""
    read -p "   Reconfigure database? (y/N) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        run_cm init
    fi
else
    echo "📋 No database config found. Let's set one up."
    echo ""
    run_cm init
fi
echo ""

# Step 3: Claude Code MCP integration
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
read -p "🔌 Configure Claude Code MCP integration? (Y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    run_cm setup-mcp
fi
echo ""

# Step 4: Semantic search (optional, ~90 MB download)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
read -p "🧠 Enable semantic search? Downloads ~90 MB ONNX model + installs timer (y/N) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    "$SCRIPT_DIR/.venv/bin/cm-embed" setup
fi
echo ""

# Step 5: Final check
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🩺 Running diagnostics..."
echo ""
run_cm doctor
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 Setup complete!"
echo ""
echo "Quick start:"
echo "  cm stats                 # Check connection"
echo "  cm save 'first entry'   # Save something"
echo "  cm search 'entry'       # Search for it"
echo ""
echo "Documentation: README.md"
