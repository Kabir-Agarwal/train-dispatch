# Hugging Face Spaces (Docker SDK) image for the West Bengal demo.
# The app is a single-process Python stdlib http.server — no runtime deps.
# HF Spaces serves the port declared as `app_port` in README.md (7860). We set
# PORT=7860 so the UNCHANGED run_ui.py (which reads $PORT and then binds
# 0.0.0.0:$PORT) listens where HF expects. See SPACES_DEPLOY.md.
FROM python:3.12-slim

WORKDIR /app

# requirements.txt is intentionally comment-only (stdlib-only app); installing it
# is a no-op but keeps the build identical to Render/Railway.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# HF Spaces (Docker) expects the container to listen on app_port (7860). run_ui.py
# binds 0.0.0.0:$PORT whenever $PORT is set, so provide it here.
ENV PORT=7860
EXPOSE 7860

CMD ["python", "run_ui.py", "--wb", "--no-browser"]
