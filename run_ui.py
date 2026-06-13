#!/usr/bin/env python3
"""ONE command to run the demo UI:  python3 run_ui.py  (then a browser opens).

Optional: --port 8000 (default), --no-browser.
"""

import argparse
import webbrowser

from app.server import make_server


def main():
    parser = argparse.ArgumentParser(description="Train dispatch demo UI")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--real", action="store_true",
                        help="use the real Indian Railways corridor dataset")
    args = parser.parse_args()
    from app.state import AppState

    state = AppState(dataset="real" if args.real else "baseline")
    server = make_server(state=state, port=args.port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Train dispatch UI running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
