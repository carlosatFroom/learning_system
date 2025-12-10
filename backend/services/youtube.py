import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from typing import List, Dict, Optional

def get_playlist_info(playlist_url: str) -> Dict:
    """
    Fetches playlist metadata and video list using yt-dlp.
    """
    ydl_opts = {
        'extract_flat': True, # Don't download videos
        'dump_single_json': True,
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(playlist_url, download=False)
        
        if 'entries' in result:
            videos = []
            for entry in result['entries']:
                videos.append({
                    'youtube_id': entry['id'],
                    'title': entry['title'],
                    'duration': entry.get('duration', 0),
                    'url': entry.get('url', f"https://www.youtube.com/watch?v={entry['id']}")
                })
            return {
                'id': result.get('id'),
                'title': result.get('title'),
                'videos': videos
            }
        return {}

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
