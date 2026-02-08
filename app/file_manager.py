"""Manage temporary file lifecycle and cleanup."""

import time
import asyncio
from pathlib import Path
from typing import Optional


class FileManager:
    """Manage temporary file lifecycle and cleanup."""

    def __init__(self, download_dir: str = "/app/downloads", max_age_seconds: int = 3600):
        self.download_dir = Path(download_dir)
        self.max_age_seconds = max_age_seconds  # 1 hour default
        self.cleanup_task: Optional[asyncio.Task] = None

    async def start_cleanup_task(self):
        """Start background cleanup task."""
        self.cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def stop_cleanup_task(self):
        """Stop background cleanup task."""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass

    async def _periodic_cleanup(self):
        """Run cleanup every 5 minutes."""
        while True:
            try:
                await asyncio.sleep(300)  # 5 minutes
                await self.cleanup_old_files()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Cleanup error: {e}")

    async def cleanup_old_files(self):
        """Delete files older than max_age_seconds."""
        now = time.time()
        deleted_count = 0

        for file_path in self.download_dir.glob("*.mp4"):
            try:
                file_age = now - file_path.stat().st_mtime

                if file_age > self.max_age_seconds:
                    file_path.unlink()
                    deleted_count += 1
                    print(f"Deleted old file: {file_path.name}")

                    # Also delete corresponding metadata file
                    metadata_path = file_path.with_suffix('.json')
                    if metadata_path.exists():
                        metadata_path.unlink()

            except Exception as e:
                print(f"Error deleting {file_path}: {e}")

        if deleted_count > 0:
            print(f"Cleaned up {deleted_count} old files")

    async def delete_file_after_delay(self, file_path: str, delay_seconds: int = 60):
        """Delete a file after specified delay (for post-download cleanup)."""
        await asyncio.sleep(delay_seconds)

        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                print(f"Deleted file after serving: {file_path}")

                # Also delete corresponding metadata file
                metadata_path = path.with_suffix('.json')
                if metadata_path.exists():
                    metadata_path.unlink()
        except Exception as e:
            print(f"Error deleting file {file_path}: {e}")
