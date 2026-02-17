"""Activity logger for tracking download activity."""

import logging
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Request

logger = logging.getLogger("uvicorn")

LOG_DIR = Path("/app/logs")
LOG_FILE = LOG_DIR / "activity.log"
MAX_LINES = 1000

_write_lock = threading.Lock()


def _format_size(size_bytes: int) -> str:
    """Format bytes to human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f}MB"


def log_activity(request: Request, url: str, platform: str, download_result: dict) -> None:
    """
    Log a download activity entry, keeping only the last 1000 lines.

    Args:
        request: FastAPI request object (for Cloudflare headers)
        url: Original video URL
        platform: Platform identifier
        download_result: Download result dict with download_id and file_size
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    user = request.headers.get("cf-access-authenticated-user-email", "unknown")
    ip = request.headers.get("cf-connecting-ip", request.client.host if request.client else "unknown")
    country = request.headers.get("cf-ipcountry", "unknown")
    file_size = _format_size(download_result.get("file_size", 0))

    line = f"{timestamp}, {user}, {ip}, {country}, {url}, {file_size}\n"

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with _write_lock:
            # Read existing lines, append new one, keep last 1000
            existing = []
            if LOG_FILE.exists():
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    existing = f.readlines()
            lines = deque(existing, maxlen=MAX_LINES)
            lines.append(line)
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.writelines(lines)
        logger.info(f"Activity logged: {user} downloaded {url} ({file_size})")
    except Exception as e:
        logger.warning(f"Failed to write activity log: {e}")
