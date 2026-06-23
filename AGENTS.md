# AGENTS.md

AI agent instructions for the **video-downloader** project.
Full architecture, security model, and troubleshooting guide: [CLAUDE.md](CLAUDE.md)

## Project Summary

Docker-based video downloader (FastAPI + yt-dlp + ffmpeg) for YouTube, Facebook, Instagram, X/Twitter, and Vimeo. Runs as a containerized service on a shared `edge` Docker network, fronted by a separate cloudflared tunnel and optional Authentik auth stack.

## Build & Run

```bash
# Prerequisite (once): shared Docker network
docker network create edge

# After any code change
docker-compose down && docker-compose up -d --build

# Logs
docker logs -f video-downloader

# Local dev (no Docker)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Component Map

| File | Responsibility |
|------|---------------|
| `app/main.py` | FastAPI app, lifespan hooks, SSE routes, yt-dlp update scheduling |
| `app/downloader.py` | yt-dlp subprocess wrapper, title fetching, filename sanitization |
| `app/url_cleaner.py` | Platform-specific URL normalization and video ID extraction |
| `app/file_manager.py` | Background periodic cleanup + post-serve deletion |
| `app/config.py` | `pydantic-settings` env config — `ALLOWED_DOMAINS` is the security gate |
| `app/models.py` | Pydantic request/response validation |
| `app/activity_logger.py` | Cloudflare-header-aware audit log (keeps last 1000 lines) |
| `entrypoint.sh` | Updates ffmpeg as root, then drops to `appuser` via `su-exec` |
| `Dockerfile` | Alpine 3.19 + Python 3.11, non-root `appuser`, venv at `/opt/venv` |

## Key Conventions

### Logger
All modules use the uvicorn logger for consistent container log output:
```python
logger = logging.getLogger("uvicorn")
```

### Download file pairs
Every download produces **two files** in `/app/downloads/`:
- `{uuid}.mp4` — the video
- `{uuid}.json` — metadata `{"filename": "sanitized-title.mp4"}`

The UUID from the metadata filename is what `/api/download/{uuid}` resolves.

### Filename sanitization
`VideoDownloader._sanitize_filename()` keeps English letters, Hebrew (U+0590–U+05FF), digits, spaces, hyphens, underscores. Max 100 chars. Falls back to `"video"` if empty after stripping.

### yt-dlp self-upgrade model
yt-dlp lives in the `appuser`-owned venv at `/opt/venv`. The app upgrades it via `pip install --upgrade` at runtime (startup + throttled background checks). **Never install yt-dlp as root** — root-owned files in the venv break the runtime self-upgrade path. ffmpeg is upgraded by `entrypoint.sh` as root before dropping privileges.

### SSE progress streaming
Download requests return a `text/event-stream` response via `sse-starlette`. Events carry a JSON payload with a `status` field. See `app/main.py` for the pattern before adding any new streaming endpoint.

### Activity logger reads Cloudflare headers
`app/activity_logger.py` extracts `cf-access-authenticated-user-email`, `cf-connecting-ip`, and `cf-ipcountry` from request headers. Do not replace these with generic headers.

## Adding a New Platform

Follow the 4-step pattern documented in [CLAUDE.md § Adding a New Platform](CLAUDE.md#adding-a-new-platform):

1. Add domain string(s) to `ALLOWED_DOMAINS` in `app/config.py`
2. Add `clean_{platform}_url() -> Optional[str]` in `app/url_cleaner.py`
3. Route to it from `URLCleaner.clean_url()` by detecting the domain
4. (Optional) Add platform-specific yt-dlp extractor args in `VideoDownloader._get_platform_options()`

## Security Rules

- **Domain whitelist** (`ALLOWED_DOMAINS` in `app/config.py`) is the primary input gate — always add new domains there before any other work.
- **Path traversal guard** — file access validates `os.path.abspath(path).startswith(download_dir)`; never bypass.
- **UUID-only download IDs** — never expose filesystem paths to the API caller.
- **Non-root runtime** — container runs as UID 1000 (`appuser`) via `su-exec`; keep it that way.

## Deployment Notes

The app joins the external `edge` network. Cloudflared and Authentik run as separate stacks on the same network and reach this service as `http://video-downloader:8000`. The `ports: 8000:8000` mapping in `docker-compose.yml` exposes the port directly **bypassing auth** — remove it for production. See [CLAUDE.md § Deployment](CLAUDE.md#deployment) for the full topology.

## Configuration Reference

All settings are in `app/config.py` (env vars or `.env` file):

| Variable | Default | Purpose |
|----------|---------|---------|
| `MAX_FILE_SIZE_MB` | 500 | Hard cap on download size |
| `MAX_FILE_AGE_SECONDS` | 3600 | Background cleanup threshold |
| `POST_SERVE_DELETE_DELAY` | 60 | Seconds before post-serve deletion |
| `YTDLP_UPDATE_CHECK_INTERVAL` | 600 | Throttle for background yt-dlp updates |
| `DOWNLOAD_TIMEOUT_SECONDS` | 300 | yt-dlp subprocess timeout |
