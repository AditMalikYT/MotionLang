#!/bin/bash

# Motion Language (.hmg) Installation Script
# ============================================
# This script sets up the Motion Language development environment
# including all dependencies for rendering and studio editing.

set -e  # Exit on error

REPO_URL="https://github.com/AditMalikYT/MotionLang.git"
INSTALL_DIR="$HOME/.motion_lang_src"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[Motion Language]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    print_error "Please do not run this script as root. Use a regular user account."
    exit 1
fi

# Detect OS
OS="$(uname -s)"
case "$OS" in
    Linux*)     OS_TYPE="linux" ;;
    Darwin*)    OS_TYPE="macos" ;;
    CYGWIN*)    OS_TYPE="windows" ;;
    MINGW*)     OS_TYPE="windows" ;;
    *)          OS_TYPE="unknown" ;;
esac

# Step 0: Handle Remote vs Local Execution (Clone/Update Repo)
print_status "Preparing source repository..."
if [ ! -f "setup.py" ]; then
    if [ -d "$INSTALL_DIR" ]; then
        print_status "Updating existing source code in $INSTALL_DIR..."
        cd "$INSTALL_DIR"
        git pull origin main || true
    else
        print_status "Cloning repository from $REPO_URL..."
        git clone "$REPO_URL" "$INSTALL_DIR"
        cd "$INSTALL_DIR"
    fi
else
    print_status "Running from local repository directory..."
fi

# Step 1: Check Python version
print_status "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+' || echo "0.0")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || [ "$PYTHON_MINOR" -lt 13 ]; then
    print_error "Motion Language requires Python 3.13 or higher. Found: Python $PYTHON_VERSION"
    print_status "Please install Python 3.13+ before continuing."
    exit 1
else
    print_success "Python $PYTHON_VERSION detected"
fi

# Step 2: Create and activate virtual environment
print_status "Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    print_success "Virtual environment created"
else
    print_warning "Virtual environment already exists, reusing it"
fi

# Activate the virtual environment
source .venv/bin/activate

# Step 3: Install Python dependencies & package in editable mode
print_status "Installing Python dependencies and CLI package..."
pip install --upgrade pip

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    print_warning "requirements.txt not found, relying on setup.py dependencies"
fi

if [ -f "setup.py" ]; then
    pip install -e .
    print_success "Motion Language CLI package installed successfully"
else
    print_error "setup.py not found in working directory: $(pwd)"
    exit 1
fi

# Step 4: Install Node.js for Studio (optional but recommended)
print_status "Checking for Node.js (required for studio)..."
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    print_success "Node.js $NODE_VERSION detected"
else
    print_warning "Node.js not found. Studio features will not be available."
fi

# Step 5: Install Studio dependencies (if Node.js is available)
if [ -d "studio" ] && command -v node &> /dev/null; then
    print_status "Installing Studio dependencies..."
    cd studio
    if [ -f "package.json" ]; then
        npm install
        print_success "Studio dependencies installed"
    fi
    cd ..
fi

# Step 6: Register VS Code / VS Codium Extension & Generate Asset Icon
print_status "Registering VS Code / VS Codium extension & icons..."
python3 -c "
import os
from PIL import Image, ImageDraw
os.makedirs('extension_assets', exist_ok=True)
img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)
draw.rounded_rectangle([16, 16, 240, 240], radius=48, fill='#0F172A')
draw.polygon([(40, 180), (88, 70), (128, 120), (168, 70), (216, 180), (180, 180), (168, 110), (128, 160), (88, 110), (72, 180)], fill='#00E5FF')
draw.polygon([(40, 180), (88, 70), (128, 120), (72, 180)], fill='#FF0055')
img.save('extension_assets/icon.png')
" 2>/dev/null || true

for EXT_DIR in "$HOME/.vscode/extensions/motion-language-support" "$HOME/.vscode-oss/extensions/motion-language-support"; do
    mkdir -p "$EXT_DIR"
    cp -r package.json language-configuration.json syntaxes snippets extension_assets "$EXT_DIR/" 2>/dev/null || true
done
print_success "VS Code/Codium extension registered"

# Step 7: Verify installation
print_status "Verifying installation..."
if motion --help &> /dev/null; then
    print_success "Motion Language CLI is working"
else
    print_warning "motion command is installed inside .venv. Activate it with: source .venv/bin/activate"
fi

# Step 8: Final instructions
print_status ""
print_status "============================================"
print_success "Motion Language installation complete!"
print_status "============================================"
print_status ""
print_status "To get started:"
print_status "  source .venv/bin/activate"
print_status "  motion examples/modern_demo.hmg"
print_status ""
print_status "============================================"