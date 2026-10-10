#!/bin/bash

# Motion Language (.hmg) Uninstallation Script
# ==============================================
# This script removes the Motion Language installation

set -e

# Colors for output
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

print_status "Starting Motion Language uninstallation cleanup..."

# Step 1: Remove virtual environment
print_status "Removing Python virtual environment..."
if [ -d ".venv" ]; then
    rm -rf .venv
    print_success "Virtual environment removed"
else
    print_warning "No virtual environment found"
fi

# Step 2: Remove studio node_modules
print_status "Removing studio node_modules..."
if [ -d "studio/node_modules" ]; then
    rm -rf studio/node_modules
    print_success "Studio node_modules removed"
else
    print_warning "No studio/node_modules found"
fi

# Step 3: Remove studio package-lock.json
if [ -f "studio/package-lock.json" ]; then
    rm -f studio/package-lock.json
    print_success "Studio package-lock.json removed"
fi

# Step 4: Remove output directory
print_status "Removing output directory..."
if [ -d "output" ]; then
    rm -rf output
    print_success "Output directory removed"
else
    print_warning "No output directory found"
fi

# Step 5: Remove cache files
print_status "Removing cache files..."
if [ -d ".cache" ]; then
    rm -rf .cache
    print_success "Cache directory removed"
else
    print_warning "No cache directory found"
fi

# Step 6: Remove temp files
print_status "Removing temporary files..."
rm -f /tmp/test_*.mp4 /tmp/test_*.hmg /tmp/modern_demo*.mp4 2>/dev/null || true

# Final message
echo ""
print_success "Motion Language uninstallation complete!"
print_status "The local workspace has been cleaned up."