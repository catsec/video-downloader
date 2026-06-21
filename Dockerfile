FROM python:3.11-alpine3.19

# Install system dependencies
RUN apk add --no-cache \
    ffmpeg \
    gcc \
    musl-dev \
    libffi-dev \
    su-exec \
    && rm -rf /var/cache/apk/*

# Create app directory
WORKDIR /app

# Non-root user, plus a virtualenv it OWNS. Deps (incl. yt-dlp) live in the venv, so the
# app can `pip install --upgrade yt-dlp` at request time WITHOUT root — which is what the
# fail→update→retry path needs (the app runs as appuser via su-exec).
RUN adduser -D -u 1000 appuser
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python dependencies into the venv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY static/ ./static/

# Logs dir + hand the app and the venv to appuser (so runtime upgrades can write to it)
RUN mkdir -p /app/logs && chown -R appuser:appuser /app /opt/venv

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8000/health || exit 1

# Start as root, entrypoint drops to appuser after updates
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
