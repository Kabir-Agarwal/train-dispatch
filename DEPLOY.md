# Deploying the live demo (Render)

The app is a single-process Python stdlib HTTP server — **no third-party runtime
dependencies**. The deployed site loads the **West Bengal real-railway demo** at
the root URL (the strongest demo). Locally nothing changes: `python run_ui.py`
still runs the 6-city demo on 127.0.0.1.

## How it adapts to the platform
- `run_ui.py` reads **`$PORT`** from the environment (Render/Railway set it) and,
  when present, binds **`0.0.0.0:$PORT`** for public traffic. With no `$PORT` it
  stays on `--port` (default 8000) at loopback for local use.
- The default network is chosen by the `--wb` flag in the start command (you can
  also set `DATASET=baseline|real|wb`).

## Render — exact steps (manual)
1. Push this branch: `git push origin real-railway`.
2. Render dashboard → **New +** → **Web Service**.
3. **Connect** your Git repo; pick branch **`real-railway`**.
4. Settings:
   - **Runtime:** Python 3
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `python run_ui.py --wb --no-browser`
   - **Instance type:** Free is fine.
5. **Create Web Service.** Render builds, then runs the start command with its
   own `$PORT`; the service goes live at `https://<name>.onrender.com/`.

That URL serves the West Bengal demo. To show a different network instead, change
the start command's flag (`--real` or drop the flag for 6-city) or set a
`DATASET` env var, then redeploy.

## Render — one-click (Blueprint)
`render.yaml` is included. Render dashboard → **New +** → **Blueprint** → point at
this repo/branch; it reads `render.yaml` (build + start commands above) and
provisions the service.

## Railway (alternative)
Railway auto-detects the `Procfile` (`web: python run_ui.py --wb --no-browser`)
and provides `$PORT`. New Project → Deploy from repo → branch `real-railway`.

## Verify locally before deploying
```bash
# Local dev (6-city, opens a browser):       python run_ui.py
# Simulate the deployed WB site (headless):  PORT=8146 python run_ui.py --wb --no-browser
#   -> binds 0.0.0.0:8146; open http://127.0.0.1:8146/
# Tests:                                      python -m pytest -q   # 230 passed
```

## Notes
- `requirements.txt` is intentionally comment-only (no runtime deps); it exists so
  the platform detects a Python project. `pytest` is dev-only.
- State is in-memory per process; the free tier sleeps when idle and resets on
  wake — fine for a demo.
