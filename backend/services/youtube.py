import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from typing import List, Dict, Optional
import os
import re
import subprocess

VIDEOS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "videos")

# Find yt-dlp binary: prefer venv, fall back to system
_VENV_YTDLP = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "venv", "bin", "yt-dlp")
YTDLP_BIN = _VENV_YTDLP if os.path.exists(_VENV_YTDLP) else "yt-dlp"

def get_playlist_info(playlist_url: str) -> Dict:
    """
    Fetches playlist metadata and video list using yt-dlp.
    """
    ydl_opts = {
        'extract_flat': True, # Don't download videos
        'dump_single_json': True,
        'quiet': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(playlist_url, download=False)
            
            if 'entries' in result:
                videos = []
                for entry in result['entries']:
                    if not entry or 'id' not in entry:
                        continue

                    vid_id = entry['id']
                    # Extra safety: if ID contains '&', strip it. 
                    # (yt-dlp usually handles this, but some raw entries might not)
                    if '&' in vid_id:
                        vid_id = vid_id.split('&')[0]
                    if '?' in vid_id:
                         vid_id = vid_id.split('?')[0]

                    videos.append({
                        'youtube_id': vid_id,
                        'title': entry.get('title', 'Untitled Video'),
                        'duration': entry.get('duration', 0),
                        'url': entry.get('url', f"https://www.youtube.com/watch?v={vid_id}")
                    })
                return {
                    'id': result.get('id'),
                    'title': result.get('title'),
                    'videos': videos
                }
            return {}
    except Exception as e:
        print(f"Error fetching playlist info for {playlist_url}: {e}")
        return {}

def _sanitize_filename(name: str) -> str:
    """Remove characters that are problematic in filenames."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.strip('. ')
    return name


def download_video(youtube_id: str, course_title: str = "", video_title: str = "", video_order: int = 0) -> Optional[str]:
    """
    Downloads a YouTube video to a course subfolder within the videos directory.
    Files are named: {order:02d} - {video_title}.mp4
    Returns the relative path (course_folder/filename) on success, None on failure.
    """
    # Build course subfolder
    if course_title:
        course_folder = _sanitize_filename(course_title)
    else:
        course_folder = "_unsorted"

    course_dir = os.path.join(VIDEOS_DIR, course_folder)
    os.makedirs(course_dir, exist_ok=True)

    # Build filename from video title
    if video_title:
        safe_title = _sanitize_filename(video_title)
    else:
        safe_title = youtube_id
    filename = f"{video_order + 1:02d} - {safe_title}.mp4"
    rel_path = os.path.join(course_folder, filename)
    full_path = os.path.join(VIDEOS_DIR, rel_path)

    # Check if already downloaded (by final name or old youtube_id name)
    if os.path.exists(full_path):
        return rel_path
    # Also check legacy flat files from before this change
    for f in os.listdir(VIDEOS_DIR):
        if f == youtube_id + ".mp4":
            # Migrate old file into course folder
            old_path = os.path.join(VIDEOS_DIR, f)
            os.rename(old_path, full_path)
            return rel_path

    output_template = os.path.join(course_dir, f"{video_order + 1:02d} - {safe_title}.%(ext)s")

    # Use subprocess so yt-dlp definitively blocks until done
    cmd = [
        YTDLP_BIN,
        '--format', 'best[height<=720][ext=mp4]/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]',
        '--output', output_template,
        '--merge-output-format', 'mp4',
        '--no-playlist',
        f'https://www.youtube.com/watch?v={youtube_id}',
    ]
    try:
        print(f"[DOWNLOAD START] {filename}", flush=True)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,  # 30 min max per video
        )
        # Log yt-dlp output for debugging
        if result.stdout:
            for line in result.stdout.strip().splitlines():
                print(f"  [yt-dlp] {line}", flush=True)
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                print(f"  [yt-dlp ERR] {line}", flush=True)

        if result.returncode != 0:
            print(f"[DOWNLOAD FAILED] {filename} (exit code {result.returncode})", flush=True)
            return None

        if os.path.exists(full_path):
            print(f"[DOWNLOAD OK] {filename}", flush=True)
            return rel_path
        print(f"[DOWNLOAD MISSING] {filename} - process exited 0 but file not found", flush=True)
        return None
    except subprocess.TimeoutExpired:
        print(f"[DOWNLOAD TIMEOUT] {filename} - exceeded 30 min", flush=True)
        return None
    except Exception as e:
        print(f"[DOWNLOAD ERROR] {filename}: {e}", flush=True)
        return None


def get_video_transcript(video_id: str) -> List[Dict]:
    """
    Fetches transcript for a video using youtube-transcript-api.
    """
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        # Format: [{'text': '...', 'start': 0.0, 'duration': 1.0}, ...]
        return transcript_list
    except Exception as e:
        print(f"Error fetching transcript for {video_id}: {e}")
        return []

if __name__ == "__main__":
    # Test with a sample playlist (CS50 2019)
    url = "https://www.youtube.com/playlist?list=PLhQjrBD2T383f9scHRNYJkior2grvZBxp"
    info = get_playlist_info(url)
    print(f"Found playlist: {info.get('title')}")
    print(f"Videos: {len(info.get('videos', []))}")
    if info.get('videos'):
        vid_id = info['videos'][0]['youtube_id']
        print(f"Fetching transcript for {vid_id}...")
        transcript = get_video_transcript(vid_id)
        print(f"Transcript length: {len(transcript)} segments")
