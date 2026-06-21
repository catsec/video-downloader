#!/bin/sh
# Refresh ffmpeg (needs root) on startup, then drop to appuser.
# yt-dlp is NOT upgraded here: it lives in an appuser-owned venv and the app upgrades it
# itself (on startup and on a failed download). Upgrading it here as root would leave
# root-owned files in the venv and break those runtime upgrades.
echo "Updating ffmpeg..."
apk update --quiet && apk upgrade --quiet ffmpeg
echo "Starting application..."
exec su-exec appuser "$@"
