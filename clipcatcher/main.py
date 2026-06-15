"""
ClipCatcher - Twitch Stream Clipper & AI Content Engine
Run GUI:              python main.py
Run ContentEngine:    python main.py --content-engine [--batch N] [--schedule] [--test]
"""
import sys
import os

# Ensure we're running with the right Python
if sys.version_info < (3, 8):
    print("Python 3.8+ required")
    sys.exit(1)

if __name__ == "__main__":
    if "--gui" in sys.argv:
        try:
            from app.gui import ClipCatcherApp
            app = ClipCatcherApp()
            app.run()
        except Exception as e:
            import traceback
            print(f"GUI Error: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            sys.exit(1)
    elif "--content-engine" in sys.argv:
        # Remove the flag so argparse in engine.py doesn't see it
        sys.argv.remove("--content-engine")
        from content_engine.engine import main as ce_main
        ce_main()
    else:
        from app.gui import ClipCatcherApp
        app = ClipCatcherApp()
        app.run()
