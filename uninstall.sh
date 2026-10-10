#!/bin/bash

# Motion Language (.hmg) Full Uninstallation Script
# ==================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${BLUE}[Motion Language]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}[ERROR]${NC} Please do not run this script as root."
    exit 1
fi

print_status "Starting full system uninstallation of Motion Language..."

# 1. Remove global source directory & virtual environment (~/.motion_lang_src)
if [ -d "$HOME/.motion_lang_src" ]; then
    print_status "Removing ~/.motion_lang_src..."
    rm -rf "$HOME/.motion_lang_src"
    print_success "Source directory removed"
else
    print_warning "No global source directory found"
fi

# 2. Remove VS Code / VS Codium extensions
for EXT_DIR in "$HOME/.vscode/extensions/motion-language-support" "$HOME/.vscode-oss/extensions/motion-language-support"; do
    if [ -d "$EXT_DIR" ]; then
        print_status "Removing extension from $EXT_DIR..."
        rm -rf "$EXT_DIR"
        print_success "Extension removed"
    fi
done

# 3. Clean up global shell aliases from ~/.bashrc and ~/.zshrc
for PROFILE in "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [ -f "$PROFILE" ]; then
        if grep -q "Motion Language" "$PROFILE"; then
            print_status "Cleaning up aliases from $PROFILE..."
            sed -i '/# Motion Language CLI/d' "$PROFILE"
            sed -i '/\.motion_lang_src\/\.venv\/bin\/motion/d' "$PROFILE"
            print_success "Shell profile cleaned"
        fi
    fi
done

# 4. Clean local workspace artifacts (if run inside a project folder)
if [ -d ".venv" ]; then
    rm -rf .venv
fi
if [ -d "studio/node_modules" ]; then
    rm -rf studio/node_modules
fi
if [ -d "output" ]; then
    rm -rf output
fi

echo ""
print_success "Motion Language has been completely uninstalled from your system!"
print_status "Please run: source ~/.bashrc (or restart your terminal) to clear the 'motion' command."