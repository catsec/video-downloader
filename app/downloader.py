"""Video downloader using yt-dlp."""

import json
import re
import uuid
import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional, Callable, Awaitable

logger = logging.getLogger("uvicorn")

# Type for status callback
StatusCallback = Optional[Callable[[str], Awaitable[None]]]


class VideoDownloader:
    """Handle video downloads using yt-dlp."""

    def __init__(self, download_dir: str = "/app/downloads"):
        self.download_dir = Path(download_dir)

    def _save_metadata(self, download_id: str, filename: str) -> None:
        """Save metadata file for later retrieval."""
        metadata_file = self.download_dir / f"{download_id}.json"
        metadata = {"filename": filename}
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False)

    @staticmethod
    def _sanitize_filename(title: str) -> str:
        """
        Sanitize filename to keep only English, Hebrew, numbers, and basic punctuation.

        Args:
            title: The original video title

        Returns:
            Sanitized filename safe for filesystem
        """
        # Keep only: English letters, Hebrew letters, numbers, spaces, hyphens, underscores
        # Unicode ranges: a-zA-Z (English), \u0590-\u05FF (Hebrew), 0-9 (numbers)
        sanitized = re.sub(r'[^a-zA-Z\u0590-\u05FF0-9\s\-_]', '', title)

        # Replace multiple spaces with single space
        sanitized = re.sub(r'\s+', ' ', sanitized)

        # Trim and limit length to 100 characters
        sanitized = sanitized.strip()[:100]

        # If empty after sanitization, use a default
        if not sanitized:
            sanitized = "video"

        return sanitized

    async def _get_video_title(self, url: str, platform: str) -> str:
        """
        Fetch video title using yt-dlp.

        Args:
            url: Video URL
            platform: Platform identifier

        Returns:
            Video title or 'video' if fetch fails
        """
        try:
            cmd = [
                "yt-dlp",
                "--print", "%(title)s",
                "--no-playlist",
                *self._get_platform_options(platform),
                url
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, _ = await process.communicate()

            if process.returncode == 0 and stdout:
                title = stdout.decode('utf-8').strip()
                return self._sanitize_filename(title)

        except Exception as e:
            logger.warning(f"Failed to fetch video title: {e}")

        return "video"

    async def _check_audio_stream(self, file_path: Path) -> bool:
        """
        Check if video file has a valid audio stream.

        Returns:
            True if audio stream exists and is not silent, False otherwise
        """
        try:
            # Check for audio stream existence
            process = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()

            if process.returncode != 0 or not stdout.decode().strip():
                logger.warning(f"No audio stream found in {file_path.name}")
                return False

            # Check if audio is silent (all samples near zero)
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", str(file_path),
                "-af", "volumedetect",
                "-f", "null", "-",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()
            stderr_text = stderr.decode()

            # Look for mean_volume or max_volume indicators
            if "mean_volume: -91.0 dB" in stderr_text or "max_volume: -91.0 dB" in stderr_text:
                logger.warning(f"Audio stream in {file_path.name} appears to be silent")
                return False

            return True

        except Exception as e:
            logger.error(f"Error checking audio stream: {e}")
            return False

    async def _get_codecs(self, file_path: Path) -> tuple:
        """
        Get video and audio codec names from file.

        Returns:
            Tuple of (video_codec, audio_codec) or (None, None) on error
        """
        try:
            # Get video codec
            process = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_name",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            video_codec = stdout.decode().strip() if process.returncode == 0 else None

            # Get audio codec
            process = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_name",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            audio_codec = stdout.decode().strip() if process.returncode == 0 else None

            return (video_codec, audio_codec)

        except Exception as e:
            logger.error(f"Error getting codecs: {e}")
            return (None, None)

    async def _ensure_mobile_compatible(self, file_path: Path, send_status: Optional[Callable] = None) -> Path:
        """
        Ensure video is universally compatible (H.264 + AAC in MP4).
        Works on iOS, Android, and all browsers.
        Re-encodes if necessary.

        Returns:
            Path to the compatible file (same or new)
        """
        video_codec, audio_codec = await self._get_codecs(file_path)
        logger.info(f"Detected codecs - video: {video_codec}, audio: {audio_codec}")

        # Universally compatible video codecs (H.264 only - H.265 has limited Android/browser support)
        compatible_video = ['h264', 'avc1', 'avc']
        # Universally compatible audio codecs
        compatible_audio = ['aac', 'mp4a']

        video_ok = video_codec and any(vc in video_codec.lower() for vc in compatible_video)
        audio_ok = not audio_codec or any(ac in audio_codec.lower() for ac in compatible_audio)

        if video_ok and audio_ok:
            logger.info("Video is already mobile-compatible (H.264/AAC)")
            return file_path

        logger.info(f"Re-encoding for mobile compatibility (video: {video_codec} → H.264, audio: {audio_codec} → AAC)")
        if send_status:
            await send_status("Converting to mobile format...")

        # Create temp output file
        temp_file = file_path.with_suffix('.temp.mp4')

        # Build ffmpeg command
        cmd = [
            "ffmpeg", "-y",
            "-i", str(file_path),
        ]

        # Video encoding
        if not video_ok:
            cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "23"])
        else:
            cmd.extend(["-c:v", "copy"])

        # Audio encoding
        if audio_codec and not audio_ok:
            cmd.extend(["-c:a", "aac", "-b:a", "128k"])
        elif audio_codec:
            cmd.extend(["-c:a", "copy"])

        # Output settings
        cmd.extend(["-movflags", "+faststart", str(temp_file)])

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()

        if process.returncode == 0 and temp_file.exists():
            # Replace original with re-encoded version
            file_path.unlink()
            temp_file.rename(file_path)
            logger.info(f"✓ Re-encoded to mobile-compatible format (H.264/AAC)")
            return file_path
        else:
            logger.error(f"Re-encoding failed: {stderr.decode()}")
            temp_file.unlink(missing_ok=True)
            return file_path  # Return original, better than nothing

    async def _add_url_subtitle(self, file_path: Path, url: str, send_status: Optional[Callable] = None) -> Path:
        """
        Add a subtitle track with the original URL.
        Creates a soft subtitle (not burned in) that can be toggled.
        """
        if send_status:
            await send_status("Adding source info...")

        # Get video duration using ffprobe
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path)
        ]
        process = await asyncio.create_subprocess_exec(
            *probe_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()

        try:
            duration = float(stdout.decode().strip())
        except:
            duration = 10.0  # Default fallback

        # Create SRT subtitle file with the URL displayed for full duration
        srt_file = file_path.with_suffix('.srt')
        srt_content = f"""1
00:00:00,000 --> {int(duration//3600):02d}:{int((duration%3600)//60):02d}:{int(duration%60):02d},{int((duration%1)*1000):03d}
{url}
"""
        srt_file.write_text(srt_content, encoding='utf-8')

        # Add subtitle to video
        temp_file = file_path.with_suffix('.temp.mp4')
        cmd = [
            "ffmpeg", "-y",
            "-i", str(file_path),
            "-i", str(srt_file),
            "-c:v", "copy",
            "-c:a", "copy",
            "-c:s", "mov_text",
            "-metadata:s:s:0", "language=eng",
            "-metadata:s:s:0", "title=Source URL",
            str(temp_file)
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()

        # Cleanup SRT file
        srt_file.unlink(missing_ok=True)

        if process.returncode == 0 and temp_file.exists():
            file_path.unlink()
            temp_file.rename(file_path)
            logger.info(f"✓ Added URL subtitle track")
            return file_path
        else:
            logger.warning(f"Failed to add subtitle: {stderr.decode()}")
            temp_file.unlink(missing_ok=True)
            return file_path  # Return original without subtitle

    async def _download_and_merge_separately(self, url: str, platform: str, download_id: str, title: str, send_status: Optional[Callable] = None) -> Dict:
        """
        Download video and audio separately, then merge with ffmpeg.
        Fallback method when combined download has audio issues.
        """
        logger.info(f"Attempting separate video+audio download for {download_id}")
        if send_status:
            await send_status("Downloading video track...")

        video_file = self.download_dir / f"{download_id}_video.mp4"
        audio_file = self.download_dir / f"{download_id}_audio.m4a"
        output_file = self.download_dir / f"{download_id}.mp4"

        try:
            # Download video only (best quality)
            video_cmd = [
                "yt-dlp",
                "-f", "bestvideo",
                "-o", str(video_file),
                "--no-playlist",
                *self._get_platform_options(platform),
                url
            ]

            process = await asyncio.create_subprocess_exec(
                *video_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            if process.returncode != 0 or not video_file.exists():
                return {'success': False, 'error': 'Failed to download video stream'}

            if send_status:
                await send_status("Downloading audio track...")

            # Download audio only
            audio_cmd = [
                "yt-dlp",
                "-f", "bestaudio[ext=m4a]/bestaudio",
                "-o", str(audio_file),
                "--no-playlist",
                *self._get_platform_options(platform),
                url
            ]

            process = await asyncio.create_subprocess_exec(
                *audio_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            if process.returncode != 0 or not audio_file.exists():
                # Try without audio if it fails
                logger.warning("Audio download failed, using video only")
                video_file.rename(output_file)
                display_filename = f"{title}.mp4"
                self._save_metadata(download_id, display_filename)
                return {
                    'success': True,
                    'file_path': str(output_file),
                    'download_id': download_id,
                    'filename': display_filename,
                    'file_size': output_file.stat().st_size,
                    'audio_warning': 'Video downloaded without audio'
                }

            if send_status:
                await send_status("Merging video and audio...")

            # Merge video and audio with ffmpeg (re-encode to H.264 for iOS compatibility)
            merge_cmd = [
                "ffmpeg",
                "-i", str(video_file),
                "-i", str(audio_file),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-movflags", "+faststart",
                str(output_file)
            ]

            process = await asyncio.create_subprocess_exec(
                *merge_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            # Cleanup temp files
            video_file.unlink(missing_ok=True)
            audio_file.unlink(missing_ok=True)

            if process.returncode == 0 and output_file.exists():
                logger.info(f"Successfully merged video and audio for {download_id}")
                # Add subtitle track with source URL
                output_file = await self._add_url_subtitle(output_file, url, send_status)
                display_filename = f"{title}.mp4"
                self._save_metadata(download_id, display_filename)
                return {
                    'success': True,
                    'file_path': str(output_file),
                    'download_id': download_id,
                    'filename': display_filename,
                    'file_size': output_file.stat().st_size
                }
            else:
                return {'success': False, 'error': 'Failed to merge video and audio'}

        except Exception as e:
            # Cleanup on error
            video_file.unlink(missing_ok=True)
            audio_file.unlink(missing_ok=True)
            return {'success': False, 'error': f'Merge error: {str(e)}'}

    async def download_video(self, url: str, platform: str, status_queue: Optional[asyncio.Queue] = None) -> Dict:
        """
        Download video using yt-dlp with optimal settings.

        Args:
            url: Video URL
            platform: Platform identifier
            status_queue: Optional queue to receive status updates
        """
        async def send_status(msg: str):
            if status_queue:
                await status_queue.put({"status": msg})
            logger.info(msg)

        await send_status("Fetching video info...")
        # Fetch video title first
        title = await self._get_video_title(url, platform)

        # Generate unique download ID (UUID for internal use only)
        download_id = str(uuid.uuid4())
        output_template = str(self.download_dir / f"{download_id}.%(ext)s")

        # yt-dlp command with optimal settings
        cmd = [
            "yt-dlp",

            # Format selection: best quality (handles both horizontal and vertical videos)
            "-f", "bestvideo+bestaudio/best",
            # Prioritize resolution and quality
            "--format-sort", "res,vcodec,acodec",
            "--merge-output-format", "mp4",

            # Output settings
            "-o", output_template,

            # Restrict filenames to ASCII (security)
            "--restrict-filenames",

            # No playlists (single video only)
            "--no-playlist",

            # Metadata
            "--add-metadata",

            # Progress reporting (for future progress bar implementation)
            "--newline",
            "--progress",

            # Retries and timeout
            "--retries", "3",
            "--socket-timeout", "30",

            # Platform-specific optimizations
            *self._get_platform_options(platform),

            # The URL to download
            url
        ]

        try:
            await send_status("Downloading video...")

            # Run asynchronously to not block FastAPI event loop
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode('utf-8')
                logger.error(f"yt-dlp failed for {url}: {error_msg}")
                return {
                    'success': False,
                    'error': f'Download failed: {error_msg}'
                }

            # Find the downloaded file
            output_file = self.download_dir / f"{download_id}.mp4"

            if not output_file.exists():
                return {
                    'success': False,
                    'error': 'Downloaded file not found'
                }

            await send_status("Checking video format...")

            # Ensure mobile compatibility (re-encode to H.264/AAC if needed)
            output_file = await self._ensure_mobile_compatible(output_file, send_status)

            await send_status("Validating audio...")

            # Check if audio stream is valid
            has_audio = await self._check_audio_stream(output_file)

            if not has_audio:
                logger.warning(f"Audio issue detected in {download_id}, trying separate download")
                await send_status("Fixing audio...")
                # Delete the problematic file
                output_file.unlink()
                # Try downloading video and audio separately
                return await self._download_and_merge_separately(url, platform, download_id, title, send_status)

            # Add subtitle track with source URL
            output_file = await self._add_url_subtitle(output_file, url, send_status)

            # Save metadata for later retrieval
            display_filename = f"{title}.mp4"
            self._save_metadata(download_id, display_filename)

            file_size = output_file.stat().st_size
            await send_status("Complete!")
            logger.info(f"✓ Download complete: {download_id} ({title}) - {file_size} bytes")

            return {
                'success': True,
                'file_path': str(output_file),
                'download_id': download_id,
                'filename': display_filename,
                'file_size': file_size
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}'
            }

    @staticmethod
    def _get_platform_options(platform: str) -> list:
        """Platform-specific yt-dlp options."""
        options = {
            'youtube': [
                # Let yt-dlp use default client selection for best quality
            ],
            'facebook': [
                '--extractor-args', 'facebook:api_version=v12.0',
            ],
            'instagram': [
                # Instagram may require cookies for private content
                # '--cookies-from-browser', 'chrome',  # Uncomment if needed
            ],
            'twitter': [
                # Twitter/X specific options
            ],
            'vimeo': [
                # Vimeo specific options
            ]
        }
        return options.get(platform, [])
