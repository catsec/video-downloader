# Video Downloader

A simple Docker-based video downloader application that supports downloading videos from YouTube, Facebook, Instagram, and X/Twitter.

## Features

- Download videos from multiple platforms:
  - YouTube (youtube.com, youtu.be)
  - Facebook (facebook.com, fb.watch)
  - Instagram (instagram.com)
  - X/Twitter (x.com, twitter.com)
- **Automatic yt-dlp updates** - Checks for and installs the latest version on every startup
- Automatic URL cleaning (removes playlist parameters, tracking data)
- Best quality video + audio merged into MP4 format
- Clean, responsive web interface
- Automatic file cleanup (files deleted after 1 hour or 60 seconds after download)
- Docker-based for easy deployment

## Tech Stack

- **Backend**: FastAPI (Python 3.11)
- **Downloader**: yt-dlp with ffmpeg
- **Container**: Alpine Linux (minimal footprint)
- **Frontend**: Vanilla HTML/CSS/JavaScript

## Quick Start

### Using Docker Compose (Recommended)

```bash
cd video-downloader
docker-compose up -d
```

### Using Docker CLI

```bash
cd video-downloader
docker build -t video-downloader .
docker run -d -p 8000:8000 --name video-downloader video-downloader
```

## Usage

1. Open your browser and navigate to: http://localhost:8000

2. Paste a video URL from any supported platform

3. Click "Download"

4. Once the video is ready, click the download button to save it

## Supported URL Formats

### YouTube
- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- Playlist URLs (automatically extracts single video)

### Facebook
- `https://www.facebook.com/watch?v=VIDEO_ID`
- `https://www.facebook.com/username/videos/VIDEO_ID`
- `https://www.facebook.com/share/v/VIDEO_ID`
- `https://fb.watch/VIDEO_ID`

### Instagram
- `https://www.instagram.com/p/POST_ID`
- `https://www.instagram.com/reel/REEL_ID`
- `https://www.instagram.com/tv/TV_ID`

### X/Twitter
- `https://twitter.com/username/status/STATUS_ID`
- `https://x.com/username/status/STATUS_ID`

## API Endpoints

### Health Check
```bash
curl http://localhost:8000/health
```

### Download Video
```bash
curl -X POST http://localhost:8000/api/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=VIDEO_ID"}'
```

### Retrieve Downloaded Video
```bash
curl http://localhost:8000/api/download/{download_id} -o video.mp4
```

## Configuration

Environment variables can be set in `docker-compose.yml`:

- `MAX_FILE_AGE_SECONDS`: Time before files are deleted (default: 3600 = 1 hour)
- `MAX_FILE_SIZE_MB`: Maximum allowed file size (default: 500 MB)

## Project Structure

```
video-downloader/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── models.py            # Pydantic models
│   ├── url_cleaner.py       # URL sanitization
│   ├── downloader.py        # yt-dlp wrapper
│   ├── file_manager.py      # Cleanup tasks
│   └── config.py            # Settings
├── static/
│   ├── index.html           # Web interface
│   ├── style.css            # Styling
│   └── app.js               # Client-side logic
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Security Features

- URL validation and sanitization
- Path traversal prevention
- UUID-based file access (prevents guessing)
- Non-root container user
- Restricted filenames (ASCII only)
- Domain whitelist

## File Cleanup

The application automatically cleans up downloaded files:

1. **Immediate cleanup**: Files are deleted 60 seconds after being downloaded
2. **Background cleanup**: A background task runs every 5 minutes to delete files older than 1 hour

This prevents disk space exhaustion and maintains privacy.

## Automatic yt-dlp Updates

The application automatically checks for and installs the latest version of yt-dlp:

- **On startup**: Always checks and updates to latest version
- **On every download request**: Checks for updates (throttled to once every 10 minutes)

This ensures you always have:

- Latest video extractor updates
- Bug fixes and security patches
- Support for new platforms and features
- Compatibility with platform changes

### Update Behavior

The update check is **throttled** to prevent excessive checks:
- After an update check, subsequent checks are skipped for 10 minutes
- This prevents slowdowns while still keeping yt-dlp current
- Update checks run in the background and don't block downloads

### Configuration

You can customize the update interval in `docker-compose.yml`:

```yaml
environment:
  - YTDLP_UPDATE_CHECK_INTERVAL=600  # seconds (default: 10 minutes)
```

### Monitoring Updates

View update status in the container logs:

```bash
docker logs video-downloader
```

Look for messages like:
- `INFO: Checking for yt-dlp updates...`
- `INFO: yt-dlp is already up to date`
- `INFO: yt-dlp updated to version X.X.X`

## Troubleshooting

### Check container logs
```bash
docker logs video-downloader
```

### Check container status
```bash
docker ps
```

### Restart container
```bash
docker restart video-downloader
```

### Rebuild after code changes
```bash
docker-compose down
docker-compose up -d --build
```

### Access container shell
```bash
docker exec -it video-downloader sh
```

## Limitations

- Videos must be publicly accessible (no authentication support)
- Maximum file size: 500 MB (configurable)
- Some platforms may block downloads from server IPs
- Private Instagram content requires cookies (not implemented by default)

## License

This project is for educational purposes. Ensure you comply with the terms of service of the platforms you download from.

## Credits

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- Powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- Video processing with [ffmpeg](https://ffmpeg.org/)
