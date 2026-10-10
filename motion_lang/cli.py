# motion_lang/cli.py

import sys
import os
import argparse
import subprocess

os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from motion_lang.parser import run_script, MotionSyntaxError
from motion_lang.fetcher import clear_cache, cache_stats
from motion_lang import __version__

STUDIO_URL = "http://localhost:5173"
UPSTREAM_REPO = "https://github.com/AditMalikYT/MotionLang.git"


def _repo_root():
    """Locate the Motion Language checkout to operate on.

    Prefers the git work tree containing the running CLI (so ``motion update``
    refreshes the copy you invoked); falls back to the global install at
    ``~/.motion_lang_src`` created by ``install.sh``.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
            cwd=os.path.dirname(os.path.abspath(__file__)))
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    home_src = os.path.expanduser("~/.motion_lang_src")
    if os.path.isdir(os.path.join(home_src, ".git")):
        return home_src
    return os.getcwd()


def do_update():
    """Pull the latest Motion Language sources and reinstall the CLI."""
    root = _repo_root()
    if not os.path.isdir(os.path.join(root, ".git")):
        print("[ERROR] Source directory not found. Please re-run install.sh", file=sys.stderr)
        return 1
    print(f"[Motion Language] Updating source repository at {root}...")
    pull = subprocess.run(["git", "-C", root, "pull", "--ff-only", "origin", "main"])
    if pull.returncode != 0:
        # Fall back to the branch's configured upstream (dev checkouts).
        pull = subprocess.run(["git", "-C", root, "pull", "--ff-only"])
        if pull.returncode != 0:
            print("[ERROR] `git pull` failed. Resolve conflicts and retry.", file=sys.stderr)
            return 1
    venv_pip = os.path.join(root, ".venv", "bin", "pip")
    pip_cmd = [venv_pip, "install", "-e", root] if os.path.isfile(venv_pip) \
        else [sys.executable, "-m", "pip", "install", "-e", root]
    print(f"[Motion Language] Reinstalling ({' '.join(pip_cmd)})...")
    if subprocess.run(pip_cmd).returncode != 0:
        print("[ERROR] `pip install -e .` failed.", file=sys.stderr)
        return 1
    print("[SUCCESS] Motion Language updated successfully!")
    return 0


def _studio_dir():
    root = _repo_root()
    local = os.path.join(root, "studio")
    if os.path.isdir(local):
        return local
    home = os.path.join(os.path.expanduser("~/.motion_lang_src"), "studio")
    return home if os.path.isdir(home) else local


def launch_studio(studio_dir= None):
    """Start the Remotion dev server and open it in the browser (blocking)."""
    studio_dir = studio_dir or _studio_dir()
    if not os.path.isfile(os.path.join(studio_dir, "package.json")):
        print(f"[Studio] Studio project not found at {studio_dir}.", file=sys.stderr)
        return 1
    npm = "npm.cmd" if os.name == "nt" else "npm"
    try:
        subprocess.run([npm, "--version"], capture_output=True, check=True)
    except Exception:
        print("[Studio] Node.js/npm not found. Install Node 18+ and retry.", file=sys.stderr)
        return 1
    if not os.path.isdir(os.path.join(studio_dir, "node_modules")):
        print("[Studio] Installing studio dependencies (first run only)...")
        if subprocess.run([npm, "install"], cwd=studio_dir).returncode != 0:
            print("[Studio] `npm install` failed.", file=sys.stderr)
            return 1
    print(f"[Studio] Launching Remotion editor at {STUDIO_URL}...")
    try:
        import webbrowser
        webbrowser.open(STUDIO_URL)
    except Exception as exc:
        print(f"[Studio] Could not open a browser ({exc}); visit {STUDIO_URL} manually.")
    try:
        return subprocess.run([npm, "run", "dev"], cwd=studio_dir).returncode
    except KeyboardInterrupt:
        print("\n[Studio] Stopped.")
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Motion Language Compiler (.hmg -> MP4)",
        epilog="Examples: motion script.hmg --render | motion script.hmg --studio | "
               "motion script.hmg --preview | motion update | motion --update | motion -v",
    )
    parser.add_argument("script", nargs="?", help="Path to .hmg script file")
    parser.add_argument("--preview", action="store_true", help="Launch interactive video preview mode")
    parser.add_argument("--render", action="store_true", help="Force MP4 render mode (overrides config `mode`)")
    parser.add_argument("--output", default="output/rendered.mp4", help="Output path for rendered video")
    parser.add_argument("--clean-cache", action="store_true", help="Wipe stored asset cutouts (.cache/) and exit")
    parser.add_argument("--cache-stats", action="store_true", help="Show cache usage and exit")
    parser.add_argument("--no-cache", action="store_true", help="Bypass disk cache for this run")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent asset fetch workers (default: 4)")
    parser.add_argument("-v", "--version", action="version",
                        version=f"%(prog)s {__version__}")
    parser.add_argument("--update", action="store_true",
                        help="Pull the latest sources and reinstall (same as `motion update`)")
    parser.add_argument("--emit-json", default=None,
                        help="Also export a composition.json timeline for the Remotion studio")
    parser.add_argument("--debug", action="store_true",
                        help="Print full tracebacks on compilation failure")
    parser.add_argument("--studio", action="store_true",
                        help="Export composition.json into studio/public/ and launch the editor")
    parser.add_argument("--no-launch", action="store_true",
                        help="With --studio, only export the JSON (do not start the dev server)")
    args = parser.parse_args(argv)
    if args.clean_cache:
        clear_cache()
        return 0
    if args.cache_stats:
        stats = cache_stats()
        print(f"[Cache] dir={stats['dir']} files={stats['files']} bytes={stats['bytes']}")
        return 0
    if args.update or (args.script == "update" and not os.path.exists("update")):
        # `motion --update` / `motion update`: refresh + reinstall (no script run).
        return do_update()
    if not args.script:
        parser.print_usage(sys.stderr)
        print("motion: error: the following arguments are required: script (unless --clean-cache/--cache-stats)", file=sys.stderr)
        return 2
    if not os.path.exists(args.script):
        print(f"Error: Script file '{args.script}' not found.")
        return 1
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    mode = "preview" if args.preview else ("render" if args.render else None)
    emit_json = args.emit_json
    skip_build = False
    if args.studio:
        emit_json = emit_json or os.path.join(_studio_dir(), "public", "composition.json")
        skip_build = not (args.preview or args.render)
    try:
        run_script(args.script, output_path=args.output, mode_override=mode,
                   use_cache=not args.no_cache, max_workers=args.workers,
                   emit_json=emit_json, skip_build=skip_build)
    except MotionSyntaxError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"[Error] {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        if args.debug:
            import traceback as _tb
            _tb.print_exc()
        print(f"[Error] Compilation failed: {exc}", file=sys.stderr)
        return 1
    if args.studio and emit_json:
        print("\n[Studio] Remotion editor is ready.")
        if args.no_launch:
            print("  cd studio && npm install && npm run dev")
            print(f"  then open {STUDIO_URL}")
            return 0
        return launch_studio()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
