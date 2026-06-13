#!/usr/bin/env python3
"""ONE command to run the demo UI:  python3 run_ui.py  (then a browser opens).

Optional: --port 8000 (default), --no-browser, --real, --wb.

Deployment (Render/Railway): the platform sets $PORT and expects the server to
bind 0.0.0.0. We read PORT from the environment (overriding --port) and bind
0.0.0.0 there; locally, with no $PORT, it stays on --port. See DEPLOY.md.
Pick the default network with $DATASET (baseline|real|wb) or the --real/--wb flags.
"""

import argparse
import os
import webbrowser

from app.server import make_server


def main():
    parser = argparse.ArgumentParser(description="Train dispatch demo UI")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--real", action="store_true",
                        help="use the real Indian Railways corridor dataset")
    parser.add_argument("--wb", action="store_true",
                        help="use the 50-station West Bengal state network")
    args = parser.parse_args()
    from app.state import AppState

    # Dataset: flags win, else $DATASET, else 6-city baseline.
    env_ds = os.environ.get("DATASET", "").strip().lower()
    dataset = ("wb" if args.wb else "real" if args.real
               else env_ds if env_ds in ("baseline", "real", "wb")
               else "baseline")

    # Port/host: $PORT (set by Render/Railway) wins and implies a public bind;
    # otherwise stay on --port at loopback for local use.
    env_port = os.environ.get("PORT")
    deployed = env_port is not None
    port = int(env_port) if deployed else args.port
    host = "0.0.0.0" if deployed else "127.0.0.1"

    state = AppState(dataset=dataset)
    server = make_server(state=state, port=port, host=host)
    bound_port = server.server_address[1]
    which = {
        "wb": "West Bengal 50-station network (geographic)",
        "real": "REAL 27-station Indian Railways corridor",
        "baseline": "6-city demo network",
    }[dataset]
    where = f"0.0.0.0:{bound_port}" if deployed else f"http://127.0.0.1:{bound_port}/"
    print(f"Train dispatch UI running at {where}  ({which}; Ctrl+C to stop)",
          flush=True)  # flush so the platform's log captures it immediately

    if not args.no_browser and not deployed:
        webbrowser.open(f"http://127.0.0.1:{bound_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
