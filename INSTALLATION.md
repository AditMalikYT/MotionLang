# Motion Language Installation Guide

## Quick Start

The easiest way to install Motion Language is using the provided installation script:

```bash
# Make the script executable and run it
chmod +x install.sh
./install.sh
```

This script will:
1. Check Python version (requires 3.13+)
2. Create a Python virtual environment
3. Install all Python dependencies
4. Install the Motion Language package
5. Install Node.js dependencies for the studio (if Node.js is available)
6. Verify the installation

## Manual Installation

### 1. Install Python 3.13+

Motion Language requires Python 3.13 or higher.

**Ubuntu:**
```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.13 python3.13-venv python3.13-dev
```

**macOS:**
```bash
brew install python@3.13
```

**Windows:**
Download from [Python 3.13 releases](https://www.python.org/downloads/)

### 2. Create Virtual Environment

```bash
python3 -m venv .venv
```

### 3. Activate Virtual Environment

**Linux/macOS:**
```bash
source .venv/bin/activate
```

**Windows:**
```bash
.\.venv\Scripts\activate
```

### 4. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

### 5. Install Studio Dependencies (Optional)

The studio requires Node.js 18+ and npm:

```bash
# Install Node.js
# Ubuntu: sudo apt install nodejs npm
# macOS: brew install node
# Windows: Download from https://nodejs.org/

# Install studio dependencies
cd studio
npm install
cd ..
```

## Verify Installation

```bash
# Check motion command
motion --help

# Run the modern demo
motion examples/modern_demo.hmg --render --output output/demo.mp4
```

## Usage Examples

### Render to MP4

```bash
motion examples/modern_demo.hmg --render --output output/demo.mp4
```

### Preview

```bash
motion examples/modern_demo.hmg --preview
```

### Studio (Web Editor)

```bash
# Export timeline for Remotion
motion examples/modern_demo.hmg --studio

# Run the studio development server
cd studio
npm run dev      # http://localhost:5173
```

### Render from Studio

```bash
cd studio
npm run render  # -> studio/out/studio.mp4
```

## VS Code Extension (Optional)

To use Motion Language syntax highlighting in VS Code:

```bash
# Create extension directory
mkdir -p ~/.vscode/extensions/motion-language-support

# Copy files
cp -r ./* ~/.vscode/extensions/motion-language-support/

# Restart VS Code
```

Note: A proper VS Code extension package will be available in the future.

## Troubleshooting

### Python Version Issues

If you get errors about Python version:
```
Error: requires Python 3.13+
```

Install Python 3.13+ as shown above, then ensure you're using the correct version:
```bash
python3 --version  # Should show 3.13.x
```

### Missing Dependencies

If you get import errors:
```bash
# Reinstall dependencies
pip install -r requirements.txt
pip install -e .
```

### Node.js Not Found

If studio features don't work:
```bash
# Install Node.js (see above)
# Then reinstall studio dependencies
cd studio
npm install
cd ..
```

### Permission Errors

If you get permission errors on Linux/macOS:
```bash
chmod +x install.sh
chmod +x uninstall.sh
```

## Uninstall

To completely remove Motion Language:

```bash
./uninstall.sh
```

This will remove:
- Python virtual environment (`.venv/`)
- Studio node_modules (`studio/node_modules/`)
- Output files (`output/`)
- Cache files (`.cache/`)

Note: Source code and examples remain intact.

## System Requirements

| Component | Minimum Version | Recommended Version |
|-----------|----------------|-------------------|
| Python | 3.13.0 | 3.13.x |
| pip | 23.0 | Latest |
| Node.js | 18.0 (optional) | 20.x |
| npm | 9.0 (optional) | Latest |
| OS | Linux/macOS/Windows | Any |
| Memory | 4 GB | 8 GB+ for large projects |
| Disk Space | 500 MB | 1 GB+ for studio |

## Development Setup

For contributing to Motion Language:

1. Fork the repository
2. Clone your fork
3. Run `./install.sh`
4. Make your changes
5. Run tests:
   ```bash
   python tests/test_language.py
   python tests/test_ae_features.py
   ```

## Next Steps

After installation:

1. ✅ Read the [AGENT.md](AGENT.md) for development guidelines
2. ✅ Try the [modern_demo.hmg](examples/modern_demo.hmg) example
3. ✅ Explore the [DSL Specification](docs/DSL_SPEC.md)
4. ✅ Check the [Repository Structure](docs/REPO_STRUCTURE.md)

## Support

- **Documentation:** [AGENT.md](AGENT.md), [docs/](docs/)
- **Examples:** [examples/](examples/)
- **Tests:** [tests/](tests/)
- **Issues:** (Repository issue tracker)
- **Discussions:** (Repository discussions)

---

For more information, see:
- [README.md](README.md) - Project overview
- [AGENT.md](AGENT.md) - Developer guide
- [docs/DSL_SPEC.md](docs/DSL_SPEC.md) - Language specification
- [docs/REPO_STRUCTURE.md](docs/REPO_STRUCTURE.md) - Architecture details
