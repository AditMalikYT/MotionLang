# motion_lang/cli.py

import sys
import os
import argparse

os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from motion_lang.parser import run_script, MotionSyntaxError
from motion_lang.fetcher import clear_cache, cache_stats


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Motion Language Compiler (.hmg -> MP4)",
        epilog="Examples: motion script.hmg --render | motion script.hmg --studio | "
               "motion script.hmg --preview | motion script.hmg --clean-cache",
    )
    parser.add_argument("script", nargs="?", help="Path to .hmg script file")
    parser.add_argument("--preview", action="store_true", help="Launch interactive video preview mode")
    parser.add_argument("--render", action="store_true", help="Force MP4 render mode (overrides config `mode`)")
    parser.add_argument("--output", default="output/rendered.mp4", help="Output path for rendered video")
    parser.add_argument("--clean-cache", action="store_true", help="Wipe stored asset cutouts (.cache/) and exit")
    parser.add_argument("--cache-stats", action="store_true", help="Show cache usage and exit")
    parser.add_argument("--no-cache", action="store_true", help="Bypass disk cache for this run")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent asset fetch workers (default: 4)")
    parser.add_argument("--emit-json", default=None,
                        help="Also export a composition.json timeline for the Remotion studio")
    parser.add_argument("--studio", action="store_true",
                        help="Export composition.json into studio/public/ and print launch instructions")
    args = parser.parse_args(argv)
    if args.clean_cache:
        clear_cache()
        return 0
    if args.cache_stats:
        stats = cache_stats()
        print(f"[Cache] dir={stats['dir']} files={stats['files']} bytes={stats['bytes']}")
        return 0
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
        emit_json = emit_json or os.path.join("studio", "public", "composition.json")
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
        print(f"[Error] Compilation failed: {exc}", file=sys.stderr)
        return 1
    if args.studio and emit_json:
        print("\n[Studio] Remotion editor is ready.")
        print("  cd studio && npm install && npm run dev")
        print("  then open http://localhost:5173")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
