# Deploying the live demo on Hugging Face Spaces (free, no credit card)

This app is a single-process Python **stdlib** `http.server` (no third-party
runtime deps). On Spaces it runs as a **Docker** Space and serves the **West
Bengal real-railway demo** at the Space URL.

## How it adapts to Spaces
- The `Dockerfile` builds Python 3.12, copies the repo, sets `ENV PORT=7860`, and
  runs `python run_ui.py --wb --no-browser`.
- `run_ui.py` reads `$PORT` and binds **`0.0.0.0:$PORT`** (= `0.0.0.0:7860`).
- `README.md` declares `sdk: docker` and `app_port: 7860` in its top YAML block —
  HF routes the public URL to port 7860. These three must agree (they do).

## Exact steps

### Option A — push this Git repo to a new Space
1. Create the Space: https://huggingface.co/new-space
   - **Owner:** your username · **Space name:** e.g. `train-dispatch`
   - **License:** your choice (e.g. MIT)
   - **Select the SDK:** **Docker** → **Blank** template
   - **Hardware:** **CPU basic (free)** · **Public**
   - Click **Create Space**. (It starts empty with its own git remote:
     `https://huggingface.co/spaces/<user>/train-dispatch`.)
2. Add the Space as a remote and push the branch as the Space's `main`:
   ```bash
   # one-time auth: create a WRITE token at https://huggingface.co/settings/tokens
   git remote add space https://huggingface.co/spaces/<user>/train-dispatch
   # push our branch to the Space's main branch
   git push space real-railway:main
   # (if prompted: username = your HF username, password = the WRITE token)
   ```
   Large/binary files aren't an issue here (text only), so Git LFS is not needed.
3. HF detects the `Dockerfile`, builds the image, and starts the container. Watch
   the **Building**/**Running** status and the **Logs** tab; on success you'll see
   `Train dispatch UI running at 0.0.0.0:7860` in the logs.

### Option B — drag-and-drop in the browser
1. Create the Space as in A.1 (SDK = Docker, Blank).
2. In the Space's **Files** tab → **Add file** → **Upload files**, upload at least:
   `Dockerfile`, `README.md`, `requirements.txt`, `run_ui.py`, and the `app/`,
   `engine/`, and `data/` folders. Commit. HF rebuilds automatically.

## Where the URL appears
- The Space page itself is the app:
  `https://huggingface.co/spaces/<user>/train-dispatch`
- The raw embed/app URL (the iframe target) is:
  `https://<user>-train-dispatch.hf.space`
  (shown via the Space's **⋮ → Embed this Space**).

## Verify locally first (exactly how HF runs it)
```bash
PORT=7860 python run_ui.py --wb --no-browser
#  -> logs: "running at 0.0.0.0:7860"; open http://127.0.0.1:7860/

# or build/run the actual image:
docker build -t train-dispatch .
docker run --rm -p 7860:7860 train-dispatch
#  -> open http://127.0.0.1:7860/
```

## Notes
- Free CPU Spaces **sleep when idle** and reset on wake; state is in-memory per
  process — fine for a demo.
- To show a different network, change the Dockerfile `CMD` flag (`--real`, or drop
  the flag for the 6-city demo) or set a `DATASET` env var, then redeploy.
- This file is HF-specific; `DEPLOY.md` covers Render/Railway.
