#!/bin/sh
# Update ffmpeg and yt-dlp on startup, then drop to appuser
echo "Updating system packages..."
apk update --quiet && apk upgrade --quiet ffmpeg
echo "Updating yt-dlp..."
pip install --quiet --upgrade yt-dlp
echo "Starting application..."
exec su-exec appuser "$@"
