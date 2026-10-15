# ChangeWatch — one container: the built React app + the Python engine that serves it.
#
# Stage 1 compiles the frontend into static files (HTML/CSS/JS).
# Stage 2 starts from Microsoft's official Playwright image, which already contains Chromium and every
# system library it needs, installs our Python packages, and copies in the built frontend.

# ---------- Stage 1: build the frontend ----------
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci
COPY frontend/ .
# Optional build-time setting for the footer link (Render and Railway pass env vars as build args).
ARG VITE_GITHUB_URL=""
ENV VITE_GITHUB_URL=$VITE_GITHUB_URL
RUN npm run build

# ---------- Stage 2: backend runtime with Chromium ----------
# The tag must match the playwright version pinned in backend/requirements.txt exactly (1.63.0).
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=web /web/dist ./frontend_dist
ENV DATA_DIR=/data \
    FRONTEND_DIST=/app/frontend_dist \
    PYTHONUNBUFFERED=1
EXPOSE 8000
# Exactly ONE Uvicorn worker: the scheduler, job queue and live-event bus live inside this process.
# A second worker would run a second scheduler and double every check.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
