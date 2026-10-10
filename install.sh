#!/bin/bash

# Motion Language (.hmg) Installation Script
# ============================================
# This script sets up the Motion Language development environment
# including all dependencies for rendering and studio editing.

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored messages
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

# Step 1: Check Python version
print_status "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+' || echo "0.0")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || [ "$PYTHON_MINOR" -lt 13 ]; then
    print_error "Motion Language requires Python 3.13 or higher. Found: Python $PYTHON_VERSION"
    print_status "Please install Python 3.13+ before continuing."
    print_status "On Ubuntu: sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.13"
    print_status "On macOS: brew install python@3.13"
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

# Determine the correct activate script based on OS
if [ "$OS_TYPE" = "windows" ]; then
    ACTIVATE_CMD=". .venv/Scripts/activate"
else
    ACTIVATE_CMD=". .venv/bin/activate"
fi

# Activate the virtual environment
source .venv/bin/activate

# Step 3: Install Python dependencies
print_status "Installing Python dependencies..."
if [ -f "requirements.txt" ]; then
    pip install --upgrade pip
    pip install -r requirements.txt
    print_success "Python dependencies installed"
else
    print_error "requirements.txt not found!"
    exit 1
fi

# Step 4: Install Motion Language package
print_status "Installing Motion Language package..."
pip install -e .
print_success "Motion Language package installed"

# Step 5: Install Node.js for Studio (optional but recommended)
print_status "Checking for Node.js (required for studio)..."
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    print_success "Node.js $NODE_VERSION detected"
else
    print_warning "Node.js not found. Studio features will not be available."
    print_status "To install Node.js:"
    print_status "  On Ubuntu: sudo apt install nodejs npm"
    print_status "  On macOS: brew install node"
    print_status "  Or download from: https://nodejs.org/"
    NODE_INSTALLED=false
fi

# Step 6: Install Studio dependencies (if Node.js is available)
if [ -d "studio" ] && command -v node &> /dev/null; then
    print_status "Installing Studio dependencies..."
    cd studio
    if [ -f "package.json" ]; then
        npm install
        print_success "Studio dependencies installed"
    else
        print_warning "studio/package.json not found"
    fi
    cd ..
else
    print_warning "Skipping Studio installation (Node.js not available)"
fi

# Step 7: Verify installation
print_status "Verifying installation..."

# Test motion command
if command -v motion &> /dev/null; then
    print_success "motion command is available"
else
    print_error "motion command not found. Installation may have failed."
    exit 1
fi

# Test basic functionality
if motion --help &> /dev/null; then
    print_success "Motion Language CLI is working"
else
    print_error "Motion Language CLI is not responding correctly"
    exit 1
fi

# Step 8: Final instructions
print_status ""
print_status "============================================"
print_success "Motion Language installation complete!"
print_status "============================================"
print_status ""
print_status "To get started:"
print_status ""
print_status "1. Run the modern demo:"
print_status "   motion examples/modern_demo.hmg --render --output output/demo.mp4"
print_status ""
print_status "2. Open the studio (web editor):"
print_status "   motion examples/modern_demo.hmg --studio"
print_status "   cd studio && npm run dev      # http://localhost:5173"
print_status ""
print_status "3. For real-time preview:"
print_status "   motion examples/modern_demo.hmg --preview"
print_status ""
print_status "4. To use VS Code extension (if available):"
print_status "   mkdir -p ~/.vscode/extensions/motion-language-support"
print_status "   cp -r ./* ~/.vscode/extensions/motion-language-support/"
print_status ""
print_status "Documentation:"
print_status "   - AGENT.md - Developer guide"
print_status "   - docs/DSL_SPEC.md - Language specification"
print_status "   - docs/REPO_STRUCTURE.md - Repository structure"
print_status ""
print_status "============================================"
