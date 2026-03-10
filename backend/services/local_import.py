"""
Scan a local folder and build a course structure from video files.

Handles varied directory layouts:
  - Flat: Course Folder/01 - Video.mp4
  - Sectioned: Course Folder/Section 1/01 - Video.mp4
  - Deeply nested: Course Folder/Section/Subsection/Video.mp4

Videos are ordered by their path (natural sort) so numbering is preserved.
"""
import os
import re
import subprocess
from typing import List, Dict, Optional

VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.webm', '.mov', '.m4v'}
SUBTITLE_EXTENSIONS = {'.srt', '.vtt', '.ass', '.ssa'}


def _natural_sort_key(s: str):
    """Sort strings with embedded numbers in natural order."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)]


def _get_video_duration(filepath: str) -> int:
    """Get video duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', filepath],
            capture_output=True, text=True, timeout=10
        )
        return int(float(result.stdout.strip()))
    except Exception:
        return 0


def _clean_title(filename: str) -> str:
    """Extract a clean title from a video filename."""
    name = os.path.splitext(filename)[0]
    # Remove leading number prefixes like "01 - ", "1. ", "01. "
    name = re.sub(r'^\d+[\.\)\-\s]+\s*', '', name)
    return name.strip() or filename


def scan_local_folder(folder_path: str) -> Optional[Dict]:
    """
    Scan a local folder and return a course structure.

    Returns: {
        'title': str,
        'source_path': str,
        'videos': [{'title': str, 'path': str, 'duration': int, 'order': int, 'subtitle': str|None}]
    }
    """
    folder_path = os.path.abspath(folder_path)
    if not os.path.isdir(folder_path):
        return None

    course_title = os.path.basename(folder_path)

    # Collect all video files with relative paths
    video_files = []
    for root, dirs, files in os.walk(folder_path):
        dirs.sort(key=_natural_sort_key)
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in VIDEO_EXTENSIONS:
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, folder_path)
                video_files.append((rel_path, full_path))

    # Sort by relative path (natural sort keeps numbering intact)
    video_files.sort(key=lambda x: _natural_sort_key(x[0]))

    videos = []
    for order, (rel_path, full_path) in enumerate(video_files):
        filename = os.path.basename(full_path)

        # Build title from section path + filename
        parts = rel_path.split(os.sep)
        if len(parts) > 1:
            # Include section name(s) in title
            section = " - ".join(_clean_title(p) for p in parts[:-1])
            clean_name = _clean_title(filename)
            title = f"{section}: {clean_name}" if section else clean_name
        else:
            title = _clean_title(filename)

        # Check for subtitle file alongside video
        subtitle = None
        base = os.path.splitext(full_path)[0]
        for srt_ext in SUBTITLE_EXTENSIONS:
            srt_path = base + srt_ext
            if os.path.exists(srt_path):
                subtitle = srt_path
                break

        duration = _get_video_duration(full_path)

        videos.append({
            'title': title,
            'path': full_path,
            'duration': duration,
            'order': order,
            'subtitle': subtitle,
        })

    if not videos:
        return None

    return {
        'title': course_title,
        'source_path': folder_path,
        'videos': videos,
    }
