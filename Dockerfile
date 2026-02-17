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

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY static/ ./static/

# Create logs directory
RUN mkdir -p /app/logs

# Non-root user for security
RUN adduser -D -u 1000 appuser && chown -R appuser:appuser /app

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
