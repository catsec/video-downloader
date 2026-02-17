"""Main FastAPI application."""

import json
import os
import uuid
import asyncio
import logging
import sys
import time
from urllib.parse import quote
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse, HTMLResponse
from sse_starlette.sse import EventSourceResponse
from fastapi.staticfiles import StaticFiles

from .models import VideoRequest, VideoResponse
from .url_cleaner import URLCleaner
from .downloader import VideoDownloader
from .file_manager import FileManager
from .config import settings
from .activity_logger import log_activity

# Configure logging to use uvicorn's logger
logger = logging.getLogger("uvicorn")

# Global state for update tracking
_last_update_check = 0
_update_in_progress = False


async def update_ytdlp(force: bool = False):
    """
    Check for and install yt-dlp updates.

    Args:
        force: If True, bypass the time-based throttling
    """
    global _last_update_check, _update_in_progress

    # Check if we should skip this update check
    current_time = time.time()
    time_since_last_check = current_time - _last_update_check

    if not force and time_since_last_check < settings.YTDLP_UPDATE_CHECK_INTERVAL:
        logger.debug(f"Skipping yt-dlp update check (last checked {int(time_since_last_check)}s ago)")
        return

    # Prevent concurrent updates
    if _update_in_progress:
        logger.debug("yt-dlp update already in progress, skipping")
        return

    _update_in_progress = True
    logger.info("Checking for yt-dlp updates...")

    try:
        # Run pip upgrade command
        process = await asyncio.create_subprocess_exec(
            "pip", "install", "--upgrade", "--no-cache-dir", "yt-dlp",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            output = stdout.decode('utf-8')
            if "Successfully installed" in output:
                # Extract version if possible
                import re
                version_match = re.search(r'yt-dlp-([\d.]+)', output)
                if version_match:
                    logger.info(f"✓ yt-dlp updated to version {version_match.group(1)}")
                else:
                    logger.info("✓ yt-dlp updated successfully")
            elif "Requirement already satisfied" in output:
                logger.info("✓ yt-dlp is already up to date")
            else:
                logger.info("✓ yt-dlp check completed")
        else:
            error_msg = stderr.decode('utf-8')
            logger.warning(f"Failed to update yt-dlp: {error_msg}")

        # Update last check time
        _last_update_check = current_time

    except Exception as e:
        logger.warning(f"Error checking for yt-dlp updates: {e}")
    finally:
        _update_in_progress = False


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Video Downloader application...")

    # Clean downloads folder on startup
    downloads_dir = Path(__file__).parent.parent / "downloads"
    if downloads_dir.exists():
        for file in downloads_dir.iterdir():
            if file.is_file():
                try:
                    file.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete {file}: {e}")
        logger.info("Cleaned downloads folder on startup")

    # Update yt-dlp to latest version (force on startup)
    await update_ytdlp(force=True)

    # Start file cleanup manager
    file_manager = FileManager()
    await file_manager.start_cleanup_task()
    app.state.file_manager = file_manager

    logger.info("Application startup complete!")

    yield

    # Shutdown
    logger.info("Shutting down application...")
    await file_manager.stop_cleanup_task()
    logger.info("Application shutdown complete")


app = FastAPI(
    title="Video Downloader",
    description="Download videos from YouTube, Facebook, Instagram, and X/Twitter",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files
static_dir = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Initialize services
url_cleaner = URLCleaner()
downloader = VideoDownloader()


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main HTML form."""
    html_file = static_dir / "index.html"
    with open(html_file, "r") as f:
        return HTMLResponse(content=f.read())


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/log")
async def get_activity_log():
    """Download the activity log file."""
    log_path = Path("/app/logs/activity.log")
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="No activity log found")
    return FileResponse(
        path=log_path,
        media_type="text/plain",
        filename="activity.log",
    )


@app.post("/api/download", response_model=VideoResponse)
async def download_video(video_request: VideoRequest, background_tasks: BackgroundTasks, request: Request):
    """
    Download video from provided URL (non-streaming version).
    """
    # Check for yt-dlp updates (non-blocking, throttled)
    background_tasks.add_task(update_ytdlp)

    # Clean URL
    clean_result = url_cleaner.clean_url(video_request.url)
    if not clean_result['success']:
        raise HTTPException(status_code=400, detail=clean_result['error'])

    clean_url = clean_result['clean_url']
    platform = clean_result['platform']

    # Download video
    download_result = await downloader.download_video(clean_url, platform)

    if not download_result['success']:
        raise HTTPException(status_code=500, detail=download_result['error'])

    # Log activity
    log_activity(request, video_request.url, platform, download_result)

    return VideoResponse(
        success=True,
        download_id=download_result['download_id'],
        filename=download_result.get('filename', 'video.mp4'),
        platform=platform
    )


@app.get("/api/download/stream")
async def download_video_stream(url: str, request: Request):
    """
    Download video with real-time status updates via Server-Sent Events.
    """
    async def event_generator():
        status_queue = asyncio.Queue()

        try:
            # Send initial status
            yield {"event": "status", "data": json.dumps({"status": "Validating URL..."})}

            # Clean URL
            clean_result = url_cleaner.clean_url(url)
            if not clean_result['success']:
                yield {"event": "error", "data": json.dumps({"error": clean_result['error']})}
                return

            clean_url = clean_result['clean_url']
            platform = clean_result['platform']

            yield {"event": "status", "data": json.dumps({"status": f"Connecting to {platform}..."})}

            # Start download task
            download_task = asyncio.create_task(
                downloader.download_video(clean_url, platform, status_queue)
            )

            # Yield status updates while download is running
            while not download_task.done():
                try:
                    # Wait for status update with timeout
                    status = await asyncio.wait_for(status_queue.get(), timeout=0.5)
                    yield {"event": "status", "data": json.dumps(status)}
                except asyncio.TimeoutError:
                    continue  # Check if task is done

            # Get download result
            download_result = download_task.result()

            # Drain any remaining status messages
            while not status_queue.empty():
                status = await status_queue.get()
                yield {"event": "status", "data": json.dumps(status)}

            if not download_result['success']:
                yield {"event": "error", "data": json.dumps({"error": download_result['error']})}
                return

            # Log activity
            log_activity(request, url, platform, download_result)

            # Send completion
            yield {"event": "complete", "data": json.dumps({
                "download_id": download_result['download_id'],
                "filename": download_result.get('filename', 'video.mp4'),
                "platform": platform
            })}

        except Exception as e:
            logger.error(f"SSE error: {e}")
            yield {"event": "error", "data": json.dumps({"error": str(e)})}

    return EventSourceResponse(event_generator())


@app.get("/api/download/{download_id}")
async def get_video(download_id: str, background_tasks: BackgroundTasks):
    """
    Retrieve downloaded video by ID.

    Security:
    - Validates download_id format (UUID)
    - Prevents path traversal
    - Schedules file deletion after serving
    """

    # Validate download_id format (UUID)
    try:
        uuid.UUID(download_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid download ID")

    # Construct file paths
    download_dir = Path("/app/downloads")
    file_path = download_dir / f"{download_id}.mp4"
    metadata_path = download_dir / f"{download_id}.json"

    logger.info(f"Serving request for download_id: {download_id}")
    logger.info(f"File path: {file_path}")
    logger.info(f"File exists: {file_path.exists()}")

    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        raise HTTPException(status_code=404, detail="File not found or expired")

    # Log file size
    file_size = file_path.stat().st_size
    logger.info(f"File size: {file_size} bytes")

    if file_size == 0:
        logger.error(f"File is empty! {file_path}")
        raise HTTPException(status_code=500, detail="Downloaded file is empty")

    # Read metadata to get display filename
    filename = "video.mp4"  # Default fallback
    if metadata_path.exists():
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
                filename = metadata.get('filename', 'video.mp4')
                logger.info(f"Display filename: {filename}")
        except Exception as e:
            logger.warning(f"Failed to read metadata: {e}")
            pass  # Use default if metadata read fails

    # Prevent path traversal
    if not os.path.abspath(str(file_path)).startswith("/app/downloads"):
        raise HTTPException(status_code=400, detail="Invalid download ID")

    # Schedule cleanup after serving (use configured delay)
    background_tasks.add_task(
        app.state.file_manager.delete_file_after_delay,
        file_path,
        settings.POST_SERVE_DELETE_DELAY
    )

    logger.info(f"✓ Serving file: {filename} ({file_size} bytes)")

    # Encode filename for HTTP header (RFC 2231)
    # Use ASCII fallback and UTF-8 encoded filename for non-ASCII characters
    try:
        # Try to encode as ASCII
        filename.encode('ascii')
        content_disposition = f'attachment; filename="{filename}"'
    except UnicodeEncodeError:
        # Use RFC 2231 encoding for non-ASCII filenames
        encoded_filename = quote(filename.encode('utf-8'))
        content_disposition = f"attachment; filename=\"video.mp4\"; filename*=UTF-8''{encoded_filename}"

    # Serve file with actual filename
    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        headers={
            "Content-Disposition": content_disposition
        }
    )
