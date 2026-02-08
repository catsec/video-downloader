"""URL cleaning and validation for supported platforms."""

import re
from urllib.parse import urlparse, parse_qs, unquote
from typing import Optional, Dict


class URLCleaner:
    """Clean and validate video URLs from various platforms."""

    @staticmethod
    def clean_youtube_url(url: str) -> Optional[str]:
        """
        Extract YouTube video ID from various URL formats.

        Supported patterns:
        - youtube.com/watch?v=VIDEO_ID
        - youtu.be/VIDEO_ID
        - m.youtube.com/watch?v=VIDEO_ID
        - youtube.com/embed/VIDEO_ID
        - youtube.com/v/VIDEO_ID
        - youtube.com/e/VIDEO_ID
        - youtube-nocookie.com/embed/VIDEO_ID
        - youtube.com/shorts/VIDEO_ID
        - youtube.com/live/VIDEO_ID
        """
        parsed = urlparse(url)
        video_id = None

        # Handle youtu.be short links
        if 'youtu.be' in parsed.netloc:
            video_id = parsed.path.strip('/')
            # Remove any trailing path segments
            if '/' in video_id:
                video_id = video_id.split('/')[0]

        # Handle youtube.com and youtube-nocookie.com
        elif 'youtube.com' in parsed.netloc or 'youtube-nocookie.com' in parsed.netloc:
            # Check query parameter first (watch?v=)
            query_params = parse_qs(parsed.query)
            video_id = query_params.get('v', [None])[0]

            if not video_id:
                # Check path-based patterns: /embed/, /v/, /e/, /shorts/, /live/
                path_match = re.search(
                    r'/(?:embed|v|e|shorts|live)/([A-Za-z0-9_-]{11})',
                    parsed.path
                )
                if path_match:
                    video_id = path_match.group(1)

        if video_id and len(video_id) >= 11:
            # YouTube video IDs are 11 characters
            return f"https://www.youtube.com/watch?v={video_id[:11]}"

        return None

    @staticmethod
    def clean_facebook_url(url: str) -> Optional[str]:
        """
        Extract video ID from Facebook URLs.

        Supported patterns:
        - facebook.com/watch?v=VIDEO_ID
        - facebook.com/watch/live/?v=VIDEO_ID
        - facebook.com/username/videos/VIDEO_ID
        - facebook.com/username/posts/POST_ID
        - facebook.com/share/v/VIDEO_ID
        - facebook.com/share/r/VIDEO_ID
        - facebook.com/reel/VIDEO_ID
        - facebook.com/video.php?v=VIDEO_ID
        - facebook.com/photo.php?v=VIDEO_ID
        - facebook.com/story.php?story_fbid=VIDEO_ID
        - facebook.com/permalink.php?story_fbid=VIDEO_ID
        - facebook.com/groups/GROUP/posts/POST_ID
        - facebook.com/groups/GROUP/permalink/POST_ID
        - facebook.com/events/EVENT_ID
        - m.facebook.com/... (mobile URLs)
        - fb.watch/VIDEO_ID
        """
        parsed = urlparse(url)

        # fb.watch short links - pass through to yt-dlp
        if 'fb.watch' in parsed.netloc:
            return url.split('?')[0]

        # Handle facebook.com URLs (including m.facebook.com)
        if 'facebook.com' in parsed.netloc:
            # Pattern: /reel/VIDEO_ID (Facebook Reels)
            reel_match = re.search(r'/reel/(\d+)', parsed.path)
            if reel_match:
                return f"https://www.facebook.com/reel/{reel_match.group(1)}"

            # Pattern: /share/v/ID or /share/r/ID (sharing formats)
            share_match = re.search(r'/share/([vr])/([A-Za-z0-9]+)', parsed.path)
            if share_match:
                share_type = share_match.group(1)
                video_id = share_match.group(2)
                return f"https://www.facebook.com/share/{share_type}/{video_id}/"

            # Query parameter patterns
            query_params = parse_qs(parsed.query)

            # Pattern: watch?v=, video.php?v=, photo.php?v=
            video_id = query_params.get('v', [None])[0] or query_params.get('video_id', [None])[0]
            if video_id:
                return f"https://www.facebook.com/watch?v={video_id}"

            # Pattern: story.php?story_fbid= or permalink.php?story_fbid=
            story_id = query_params.get('story_fbid', [None])[0]
            if story_id:
                return f"https://www.facebook.com/watch?v={story_id}"

            # Pattern: /videos/VIDEO_ID or /videos/title/VIDEO_ID
            video_match = re.search(r'/videos/(?:[^/]+/)?(\d+)', parsed.path)
            if video_match:
                return f"https://www.facebook.com/watch?v={video_match.group(1)}"

            # Pattern: /posts/POST_ID (user posts with videos)
            posts_match = re.search(r'/posts/(pfbid[A-Za-z0-9]+|\d+)', parsed.path)
            if posts_match:
                return f"https://www.facebook.com/watch?v={posts_match.group(1)}"

            # Pattern: /groups/GROUP/posts/POST_ID or /groups/GROUP/permalink/POST_ID
            group_match = re.search(r'/groups/[^/]+/(?:posts|permalink)/(\d+)', parsed.path)
            if group_match:
                return f"https://www.facebook.com/watch?v={group_match.group(1)}"

            # Pattern: /events/EVENT_ID
            event_match = re.search(r'/events/(\d+)', parsed.path)
            if event_match:
                return f"https://www.facebook.com/events/{event_match.group(1)}"

        return None

    @staticmethod
    def clean_instagram_url(url: str) -> Optional[str]:
        """
        Extract Instagram content ID from various URL formats.

        Supported patterns:
        - instagram.com/p/POST_ID
        - instagram.com/reel/REEL_ID
        - instagram.com/reels/REEL_ID
        - instagram.com/tv/TV_ID
        - instagram.com/stories/USERNAME/STORY_ID
        - instagram.com/stories/highlights/HIGHLIGHT_ID
        - instagram.com/USERNAME/reel/REEL_ID
        """
        parsed = urlparse(url)

        if 'instagram.com' in parsed.netloc:
            # Pattern: /stories/highlights/ID or /stories/username/ID
            stories_match = re.search(
                r'/stories/(?:highlights/)?([A-Za-z0-9_.-]+)(?:/(\d+))?',
                parsed.path
            )
            if stories_match:
                user_or_highlight = stories_match.group(1)
                story_id = stories_match.group(2)
                if story_id:
                    return f"https://www.instagram.com/stories/{user_or_highlight}/{story_id}/"
                elif user_or_highlight == 'highlights' or user_or_highlight.isdigit():
                    return f"https://www.instagram.com/stories/highlights/{user_or_highlight}/"

            # Pattern: /p/, /reel/, /reels/, /tv/ (with optional username prefix)
            content_match = re.search(
                r'/(?:[^/]+/)?(p|reels?|tv)/([A-Za-z0-9_-]+)',
                parsed.path
            )
            if content_match:
                content_type = content_match.group(1)
                content_id = content_match.group(2)
                # Normalize 'reels' to 'reel'
                if content_type == 'reels':
                    content_type = 'reel'
                return f"https://www.instagram.com/{content_type}/{content_id}/"

        return None

    @staticmethod
    def clean_twitter_url(url: str) -> Optional[str]:
        """
        Extract Twitter/X content from various URL formats.

        Supported patterns:
        - twitter.com/username/status/STATUS_ID
        - x.com/username/status/STATUS_ID
        - twitter.com/i/web/status/STATUS_ID
        - twitter.com/statuses/STATUS_ID
        - twitter.com/i/broadcasts/BROADCAST_ID
        - twitter.com/i/spaces/SPACE_ID
        - twitter.com/username/status/STATUS_ID/video/1
        - twitter.com/username/status/STATUS_ID/photo/1
        - m.twitter.com/... (mobile URLs)
        - mobile.twitter.com/...
        - t.co/SHORTCODE (URL shortener)
        """
        parsed = urlparse(url)

        # Handle t.co shortener - pass through to yt-dlp
        if 't.co' in parsed.netloc:
            return url

        # Handle twitter.com and x.com (including mobile variants)
        if any(domain in parsed.netloc for domain in ['twitter.com', 'x.com']):
            # Pattern: /status/ID or /statuses/ID (with optional /video/N or /photo/N)
            status_match = re.search(r'/(?:status|statuses)/(\d+)', parsed.path)
            if status_match:
                status_id = status_match.group(1)
                return f"https://x.com/i/status/{status_id}"

            # Pattern: /i/broadcasts/ID
            broadcast_match = re.search(r'/i/broadcasts/(\w+)', parsed.path)
            if broadcast_match:
                return f"https://x.com/i/broadcasts/{broadcast_match.group(1)}"

            # Pattern: /i/spaces/ID
            spaces_match = re.search(r'/i/spaces/([0-9a-zA-Z]+)', parsed.path)
            if spaces_match:
                return f"https://x.com/i/spaces/{spaces_match.group(1)}"

        return None

    @staticmethod
    def clean_vimeo_url(url: str) -> Optional[str]:
        """
        Extract Vimeo video ID from various URL formats.

        Supported patterns:
        - vimeo.com/VIDEO_ID
        - vimeo.com/VIDEO_ID/UNLISTED_HASH
        - player.vimeo.com/video/VIDEO_ID
        - vimeo.com/channels/CHANNEL/VIDEO_ID
        - vimeo.com/groups/GROUP/videos/VIDEO_ID
        - vimeo.com/album/ALBUM_ID
        - vimeo.com/showcase/SHOWCASE_ID
        - vimeo.com/ondemand/TITLE/VIDEO_ID
        - vimeo.com/user/review/VIDEO_ID/HASH
        - vimeopro.com/user/project/video/VIDEO_ID
        - vimeo.com/event/EVENT_ID
        """
        parsed = urlparse(url)

        # Handle vimeo.com, player.vimeo.com, vimeopro.com
        if 'vimeo.com' in parsed.netloc:
            # Pattern: /ondemand/title/VIDEO_ID
            ondemand_match = re.search(r'/ondemand/[^/]+/(\d+)', parsed.path)
            if ondemand_match:
                return f"https://vimeo.com/{ondemand_match.group(1)}"

            # Pattern: /review/VIDEO_ID/HASH
            review_match = re.search(r'/review/(\d+)/([a-f0-9]+)', parsed.path)
            if review_match:
                video_id = review_match.group(1)
                review_hash = review_match.group(2)
                return f"https://vimeo.com/{video_id}/{review_hash}"

            # Pattern: /event/EVENT_ID
            event_match = re.search(r'/event/(\d+)', parsed.path)
            if event_match:
                return f"https://vimeo.com/event/{event_match.group(1)}"

            # Pattern: /album/ID or /showcase/ID (collections)
            collection_match = re.search(r'/(album|showcase)/(\d+)', parsed.path)
            if collection_match:
                coll_type = collection_match.group(1)
                coll_id = collection_match.group(2)
                return f"https://vimeo.com/{coll_type}/{coll_id}"

            # Pattern: VIDEO_ID with optional unlisted hash
            # Handles: /VIDEO_ID, /VIDEO_ID/HASH, /channels/x/VIDEO_ID, /groups/x/videos/VIDEO_ID
            video_match = re.search(r'/(\d+)(?:/([a-f0-9]+))?(?:\?|$|/)', parsed.path + '/')
            if video_match:
                video_id = video_match.group(1)
                unlisted_hash = video_match.group(2)
                if unlisted_hash:
                    return f"https://vimeo.com/{video_id}/{unlisted_hash}"
                return f"https://vimeo.com/{video_id}"

        # Handle vimeopro.com
        if 'vimeopro.com' in parsed.netloc:
            video_match = re.search(r'/video/(\d+)', parsed.path)
            if video_match:
                return f"https://vimeo.com/{video_match.group(1)}"

        return None

    @classmethod
    def clean_url(cls, url: str) -> Dict[str, any]:
        """
        Main entry point: detect platform and clean URL.

        Returns:
            dict with 'success', 'clean_url', 'platform', 'error'
        """
        url = url.strip()

        # Detect platform and route to appropriate cleaner
        if any(domain in url for domain in ['youtube.com', 'youtu.be', 'youtube-nocookie.com']):
            clean = cls.clean_youtube_url(url)
            platform = 'youtube'
        elif any(domain in url for domain in ['facebook.com', 'fb.watch']):
            clean = cls.clean_facebook_url(url)
            platform = 'facebook'
        elif 'instagram.com' in url:
            clean = cls.clean_instagram_url(url)
            platform = 'instagram'
        elif any(domain in url for domain in ['twitter.com', 'x.com', 't.co']):
            clean = cls.clean_twitter_url(url)
            platform = 'twitter'
        elif any(domain in url for domain in ['vimeo.com', 'vimeopro.com']):
            clean = cls.clean_vimeo_url(url)
            platform = 'vimeo'
        else:
            return {
                'success': False,
                'error': 'Unsupported platform. Supported: YouTube, Facebook, Instagram, X/Twitter, Vimeo'
            }

        if clean:
            return {
                'success': True,
                'clean_url': clean,
                'platform': platform
            }
        else:
            return {
                'success': False,
                'error': f'Could not extract valid video ID from {platform} URL'
            }
