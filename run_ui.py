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
    args = parser.parse_args()
    server = make_server(port=args.port)
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
