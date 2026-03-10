from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, UploadFile, File
from datetime import datetime
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List, Optional
from ..database import get_db
from ..models import Course, Video, VideoProgress, Question, Answer, Transcript
from ..services.youtube import get_playlist_info, get_video_transcript, download_video
from ..services.local_import import scan_local_folder
from ..services.ai_tutor import generate_questions, evaluate_answer
from ..database import SessionLocal
from pydantic import BaseModel
import threading
import os
import re
import json

# In-memory download job tracker
# { course_id: { "status": "running"|"done", "total": N, "completed": N, "failed": N, "results": [...] } }
_download_jobs: dict = {}


def _to_int(value, default=0):
    """Best-effort int coercion for AI-produced score fields."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value, default=0.0):
    """Best-effort float coercion for AI-produced numeric fields."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

router = APIRouter()
templates = Jinja2Templates(directory="backend/templates")

class ProgressUpdate(BaseModel):
    video_id: int
    course_id: int
    timestamp: float
    completed: bool

def _get_course_thumbnail(course: Course, db: Session) -> Optional[str]:
    """Get or generate a thumbnail URL for a course."""
    if course.thumbnail:
        return course.thumbnail

    sorted_videos = sorted(course.videos, key=lambda v: v.order)
    if not sorted_videos:
        return None

    first_video = sorted_videos[0]

    # YouTube course: use YouTube thumbnail
    if first_video.youtube_id:
        thumb_url = f"https://img.youtube.com/vi/{first_video.youtube_id}/mqdefault.jpg"
        course.thumbnail = thumb_url
        db.commit()
        return thumb_url

    # Local video: extract a frame with ffmpeg
    if first_video.local_filename and os.path.isfile(first_video.local_filename):
        thumbs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "thumbs")
        os.makedirs(thumbs_dir, exist_ok=True)
        thumb_file = f"course_{course.id}.jpg"
        thumb_path = os.path.join(thumbs_dir, thumb_file)

        if not os.path.exists(thumb_path):
            try:
                import subprocess
                subprocess.run(
                    ['ffmpeg', '-ss', '30', '-i', first_video.local_filename,
                     '-vframes', '1', '-vf', 'scale=320:-1', '-q:v', '5',
                     '-y', thumb_path],
                    capture_output=True, timeout=15,
                )
            except Exception:
                pass

        if os.path.exists(thumb_path):
            thumb_url = f"/static/thumbs/{thumb_file}"
            course.thumbnail = thumb_url
            db.commit()
            return thumb_url

    return None

@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    # Only show non-hidden courses
    courses = db.query(Course).filter(Course.is_hidden == False).all()
    # Enrich with progress
    course_data = []
    for c in courses:
        total_vids = len(c.videos)
        completed = sum(1 for v in c.videos if any(p.completed for p in v.progress))
        progress = int((completed / total_vids * 100)) if total_vids > 0 else 0

        course_data.append({
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "video_count": total_vids,
            "progress_percent": progress,
            "thumbnail": _get_course_thumbnail(c, db),
        })

    return templates.TemplateResponse("dashboard.html", {"request": request, "courses": course_data})

@router.post("/ingest")
def ingest_course(playlist_url: str = Form(...), db: Session = Depends(get_db)):
    # 1. Fetch info
    info = get_playlist_info(playlist_url)
    if not info:
        return RedirectResponse(url="/?error=invalid_url", status_code=303)

    # 2. Check exists
    existing = db.query(Course).filter(Course.playlist_id == info['id']).first()
    if existing:
        return RedirectResponse(url=f"/course/{existing.id}", status_code=303)

    # 3. Create
    new_course = Course(title=info['title'], description=f"Imported from YouTube: {info['title']}", playlist_id=info['id'])
    db.add(new_course)
    db.commit()
    db.refresh(new_course)

    # 4. Videos
    for idx, v in enumerate(info.get('videos', [])):
        y_id = v['youtube_id']
        if '&' in y_id: y_id = y_id.split('&')[0]
        if '?' in y_id: y_id = y_id.split('?')[0]

        new_vid = Video(course_id=new_course.id, youtube_id=y_id, title=v['title'], order=idx, duration=v['duration'])
        db.add(new_vid)
    db.commit()

    return RedirectResponse(url=f"/", status_code=303)

def _import_single_folder(folder_path: str, db: Session) -> Optional[Course]:
    """Import a single local folder as a course. Returns the Course or None."""
    abs_path = os.path.abspath(folder_path)
    existing = db.query(Course).filter(Course.source_path == abs_path).first()
    if existing:
        return existing

    info = scan_local_folder(folder_path)
    if not info or not info['videos']:
        return None

    new_course = Course(
        title=info['title'],
        description=f"Imported from local folder",
        playlist_id=f"local:{info['source_path']}",
        source_path=info['source_path'],
    )
    db.add(new_course)
    db.commit()
    db.refresh(new_course)

    for v in info['videos']:
        new_vid = Video(
            course_id=new_course.id,
            youtube_id="",
            title=v['title'],
            order=v['order'],
            duration=v['duration'],
            local_filename=v['path'],
        )
        db.add(new_vid)
    db.commit()

    print(f"[LOCAL IMPORT] Imported {len(info['videos'])} videos from {folder_path}", flush=True)
    return new_course

@router.post("/ingest_local")
def ingest_local_course(folder_path: str = Form(...), db: Session = Depends(get_db)):
    """Import a course from a single local folder."""
    folder_path = folder_path.strip()
    if not os.path.isdir(folder_path):
        return RedirectResponse(url="/admin?status=invalid_folder", status_code=303)

    course = _import_single_folder(folder_path, db)
    if not course:
        return RedirectResponse(url="/admin?status=no_videos_found", status_code=303)

    return RedirectResponse(url=f"/", status_code=303)

@router.post("/ingest_local_batch")
def ingest_local_batch(folder_path: str = Form(...), db: Session = Depends(get_db)):
    """Import all subfolders of a root directory as separate courses."""
    folder_path = folder_path.strip()
    if not os.path.isdir(folder_path):
        return RedirectResponse(url="/admin?status=invalid_folder", status_code=303)

    imported = 0
    skipped = 0
    empty = 0

    # Each immediate subfolder becomes a course
    for entry in sorted(os.listdir(folder_path)):
        sub = os.path.join(folder_path, entry)
        if not os.path.isdir(sub):
            continue

        abs_sub = os.path.abspath(sub)
        if db.query(Course).filter(Course.source_path == abs_sub).first():
            skipped += 1
            continue

        course = _import_single_folder(sub, db)
        if course:
            imported += 1
        else:
            empty += 1

    print(f"[BATCH IMPORT] {folder_path}: {imported} imported, {skipped} skipped, {empty} empty", flush=True)
    return RedirectResponse(url=f"/admin?status=batch_done&imported={imported}&skipped={skipped}", status_code=303)

@router.get("/stream/{video_id}")
def stream_video(video_id: int, request: Request, db: Session = Depends(get_db)):
    """Serve a local video file with range request support for seeking."""
    from starlette.responses import StreamingResponse

    video = db.query(Video).filter(Video.id == video_id).first()
    if not video or not video.local_filename:
        raise HTTPException(status_code=404, detail="Video not found")

    file_path = video.local_filename
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Video file not found on disk")

    file_size = os.path.getsize(file_path)
    ext = os.path.splitext(file_path)[1].lower()
    media_types = {'.mp4': 'video/mp4', '.mkv': 'video/x-matroska', '.webm': 'video/webm', '.mov': 'video/quicktime'}
    media_type = media_types.get(ext, 'video/mp4')

    range_header = request.headers.get("range")
    if range_header:
        # Parse range: "bytes=start-end"
        range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
            end = min(end, file_size - 1)
            content_length = end - start + 1

            def iter_file():
                with open(file_path, 'rb') as f:
                    f.seek(start)
                    remaining = content_length
                    while remaining > 0:
                        chunk = f.read(min(8192, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk

            return StreamingResponse(
                iter_file(),
                status_code=206,
                media_type=media_type,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(content_length),
                },
            )

    return FileResponse(file_path, media_type=media_type)

@router.post("/api/download_video/{video_id}")
def download_video_endpoint(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.local_filename:
        return {"status": "already_downloaded", "filename": video.local_filename}

    course = video.course
    filename = download_video(
        video.youtube_id,
        course_title=course.title if course else "",
        video_title=video.title,
        video_order=video.order,
    )
    if not filename:
        raise HTTPException(status_code=500, detail="Failed to download video")

    video.local_filename = filename
    db.commit()
    return {"status": "ok", "filename": filename}

@router.post("/api/download_course/{course_id}")
def download_course_start(course_id: int, db: Session = Depends(get_db)):
    """Kick off a background download job for all videos in a course."""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    # Don't start a second job if one is already running
    existing = _download_jobs.get(course_id)
    if existing and existing["status"] == "running":
        return {"status": "already_running", "job": existing}

    to_download = []
    already = 0
    course_title = course.title
    for video in sorted(course.videos, key=lambda v: v.order):
        if video.local_filename:
            already += 1
        else:
            to_download.append({
                "video_id": video.id,
                "youtube_id": video.youtube_id,
                "video_title": video.title,
                "video_order": video.order,
            })

    if not to_download:
        return {"status": "all_downloaded", "total": already}

    job = {
        "status": "running",
        "total": len(to_download) + already,
        "already": already,
        "completed": 0,
        "failed": 0,
        "results": [],
        "current": [],
    }
    _download_jobs[course_id] = job

    def _run_downloads():
        total = len(to_download)
        for idx, item in enumerate(to_download):
            vid_id = item["video_id"]
            yt_id = item["youtube_id"]
            job["current"] = [yt_id]
            print(f"[QUEUE] ({idx + 1}/{total}) Starting: {item['video_title']}", flush=True)
            try:
                filename = download_video(
                    yt_id,
                    course_title=course_title,
                    video_title=item["video_title"],
                    video_order=item["video_order"],
                )
                if filename:
                    s = SessionLocal()
                    try:
                        v = s.query(Video).filter(Video.id == vid_id).first()
                        if v:
                            v.local_filename = filename
                            s.commit()
                    finally:
                        s.close()
                    job["completed"] += 1
                    job["results"].append({"video_id": vid_id, "status": "ok"})
                    print(f"[QUEUE] ({idx + 1}/{total}) Done: {item['video_title']}", flush=True)
                else:
                    job["failed"] += 1
                    job["results"].append({"video_id": vid_id, "status": "failed"})
                    print(f"[QUEUE] ({idx + 1}/{total}) Failed: {item['video_title']}", flush=True)
            except Exception as e:
                job["failed"] += 1
                job["results"].append({"video_id": vid_id, "status": "failed", "error": str(e)})
                print(f"[QUEUE] ({idx + 1}/{total}) Error: {item['video_title']}: {e}", flush=True)
        job["current"] = []
        job["status"] = "done"
        print(f"[QUEUE] All done. {job['completed']} ok, {job['failed']} failed.", flush=True)

    thread = threading.Thread(target=_run_downloads, daemon=True)
    thread.start()
    return {"status": "started", "job": job}

@router.get("/api/download_course/{course_id}/status")
def download_course_status(course_id: int):
    """Poll download progress for a course."""
    job = _download_jobs.get(course_id)
    if not job:
        return {"status": "no_job"}
    return {"status": job["status"], "job": job}

@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)):
    courses = db.query(Course).all()
    status_code = request.query_params.get("status")
    status_messages = {
        "next_video_unlocked": "Unlocked the next video in sequence.",
        "all_videos_completed": "All videos are already unlocked and completed.",
        "no_videos": "This course has no videos to unlock.",
        "course_not_found": "Course not found.",
        "invalid_folder": "Folder path does not exist or is not a directory.",
        "no_videos_found": "No video files found in that folder.",
    }
    # Dynamic status for batch import
    if status_code == "batch_done":
        imp = request.query_params.get("imported", "0")
        skp = request.query_params.get("skipped", "0")
        status_messages["batch_done"] = f"Batch import complete: {imp} courses imported, {skp} already existed."
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "courses": courses,
        "status_message": status_messages.get(status_code)
    })

@router.post("/admin/toggle_course/{course_id}")
def toggle_course_visibility(course_id: int, hide: bool = Form(...), db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if course:
        course.is_hidden = hide
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@router.post("/admin/unlock_next_video/{course_id}")
def unlock_next_video(course_id: int, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        return RedirectResponse(url="/admin?status=course_not_found", status_code=303)

    sorted_videos = sorted(course.videos, key=lambda v: v.order)
    if not sorted_videos:
        return RedirectResponse(url="/admin?status=no_videos", status_code=303)

    video_ids = [video.id for video in sorted_videos]
    progress_rows = db.query(VideoProgress).filter(
        VideoProgress.video_id.in_(video_ids),
        VideoProgress.user_id == "user"
    ).all()
    progress_by_video = {row.video_id: row for row in progress_rows}

    first_incomplete_video = None
    for video in sorted_videos:
        progress = progress_by_video.get(video.id)
        if not progress or not progress.completed:
            first_incomplete_video = video
            break

    if not first_incomplete_video:
        return RedirectResponse(url="/admin?status=all_videos_completed", status_code=303)

    progress = progress_by_video.get(first_incomplete_video.id)
    if not progress:
        progress = VideoProgress(video_id=first_incomplete_video.id, user_id="user")
        db.add(progress)

    progress.completed = True
    progress.updated_at = datetime.utcnow()
    db.commit()

    return RedirectResponse(url="/admin?status=next_video_unlocked", status_code=303)

@router.get("/course/{course_id}", response_class=HTMLResponse)
def player(request: Request, course_id: int, video_id: Optional[int] = None, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    sorted_videos = sorted(course.videos, key=lambda x: x.order)
    progress_rows = db.query(VideoProgress).filter(VideoProgress.video_id.in_([v.id for v in sorted_videos])).all() if sorted_videos else []
    progress_by_video_id = {p.video_id: p for p in progress_rows}

    def is_unlocked(video: Video) -> bool:
        # A video is unlocked only if all previous videos are completed.
        for v in sorted_videos:
            if v.id == video.id:
                return True
            if not (progress_by_video_id.get(v.id) and progress_by_video_id[v.id].completed):
                return False
        return True

    target_video = None
    if video_id:
        target_video = db.query(Video).filter(Video.id == video_id, Video.course_id == course_id).first()
        if target_video and not is_unlocked(target_video):
            target_video = None
    
    if not target_video:
        target_video = next((v for v in sorted_videos if is_unlocked(v)), sorted_videos[0] if sorted_videos else None)

    if not target_video:
        return RedirectResponse(url="/")

    prog = progress_by_video_id.get(target_video.id)
    
    video_data = {
        "id": target_video.id,
        "title": target_video.title,
        "youtube_id": target_video.youtube_id,
        "duration": target_video.duration,
        "last_watched_timestamp": prog.last_watched_timestamp if prog else 0,
        "local_filename": target_video.local_filename
    }

    # Sidebar
    sidebar_videos = []
    completed_count = 0
    previous_completed = True # First video is always unlocked
    
    for v in sorted_videos:
        p = progress_by_video_id.get(v.id)
        is_completed = p.completed if p else False
        if is_completed: completed_count += 1
        
        is_locked = not previous_completed
        
        sidebar_videos.append({
            "id": v.id,
            "title": v.title,
            "duration": v.duration,
            "completed": is_completed,
            "locked": is_locked
        })
        
        # Update previous_completed for the NEXT iteration
        # A video unlocks the next one only if IT is completed
        previous_completed = is_completed
    
    progress_percent = int((completed_count / len(course.videos) * 100)) if course.videos else 0

    return templates.TemplateResponse("player.html", {
        "request": request, 
        "course": {
            "id": course.id, 
            "title": course.title, 
            "videos": sidebar_videos, 
            "progress_percent": progress_percent,
            "playlist_id": course.playlist_id
        },
        "video": video_data
    })

@router.post("/api/progress")
def update_progress(data: ProgressUpdate, db: Session = Depends(get_db)):
    prog = db.query(VideoProgress).filter(VideoProgress.video_id == data.video_id).first()
    if not prog:
        prog = VideoProgress(video_id=data.video_id, user_id="user")
        db.add(prog)
    
    prog.last_watched_timestamp = data.timestamp
    if data.completed:
        prog.completed = True
    
    prog.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "ok"}

@router.get("/api/videos/{video_id}/quiz")
def get_quiz(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    if not video.questions:
        # Check if we have transcripts in DB
        transcripts_db = db.query(Transcript).filter(Transcript.video_id == video.id).all()
        
        if not transcripts_db:
            # Fetch from YouTube
            transcript_list = get_video_transcript(video.youtube_id)
            if transcript_list:
                # Save to DB
                for t in transcript_list:
                    new_t = Transcript(
                        video_id=video.id,
                        text=t['text'],
                        start_time=t['start'],
                        duration=t['duration']
                    )
                    db.add(new_t)
                db.commit()
                # Re-fetch from DB to be clean
                transcripts_db = db.query(Transcript).filter(Transcript.video_id == video.id).all()
        
        # Prepare text for AI
        if transcripts_db:
             full_text = " ".join([t.text for t in transcripts_db])
        else:
             full_text = f"Title: {video.title}. Use this title as context."

        generated = generate_questions(full_text)
        
        for q in generated:
            new_q = Question(
                video_id=video.id,
                text=q['question'],
                kind='text',
                correct_answer_summary=q.get('context', '') 
            )
            db.add(new_q)
        db.commit()
        db.refresh(video)
        
    return {
        "video_id": video.id,
        "questions": [
            {
                "id": q.id,
                "text": q.text,
                "kind": q.kind
            } for q in video.questions
        ]
    }

@router.post("/api/submit_exam")
async def submit_exam(
    video_id: int = Form(...),
    answer_text: Optional[str] = Form(None),
    audio_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    # 1. Logic to get text
    final_text = ""
    if audio_file:
        content = await audio_file.read()
        from ..services.ai_tutor import transcribe_audio
        final_text = transcribe_audio(content)
    else:
        final_text = answer_text or ""

    # 2. Get Questions
    questions = db.query(Question).filter(Question.video_id == video_id).all()
    if not questions:
        raise HTTPException(status_code=404, detail="No questions found for this video")
    
    question_dicts = [{"id": q.id, "text": q.text} for q in questions]

    # 3. Evaluate Batch
    from ..services.ai_tutor import evaluate_exam
    result = evaluate_exam(question_dicts, final_text)
    
    # 4. Normalize evaluator output and compute pass/fail deterministically.
    # Do not trust model-provided booleans for gating progression.
    answered_question_ids = [
        _to_int(q_id, default=-1) for q_id in result.get('answered_question_ids', [])
    ]
    answered_question_ids = [q_id for q_id in answered_question_ids if q_id > 0]

    raw_scores = result.get('individual_scores', {}) or {}
    score_by_qid = {}
    if isinstance(raw_scores, dict):
        for key, value in raw_scores.items():
            q_id = _to_int(key, default=-1)
            if q_id > 0:
                score_by_qid[q_id] = _to_float(value, default=0.0)

    per_answer_scores = []

    # 5. Save Answers (Individual)
    # We save individual records for history tracking, even if graded in batch
    for q_id in answered_question_ids:
        score = score_by_qid.get(q_id, 0)
        per_answer_scores.append(score)
        is_pass = score >= 70

        new_answer = Answer(
            question_id=q_id,
            user_answer=final_text, # We save full transcript for each
            is_correct=is_pass,
            rating=_to_int(score, default=0),
            feedback=result.get('feedback', "")
        )
        db.add(new_answer)

    # Require at least 2 answered questions and both to clear 70+.
    passing_answers = sum(1 for score in per_answer_scores if score >= 70)
    passed_exam = len(answered_question_ids) >= 2 and passing_answers >= 2
    overall_score = _to_float(
        result.get('overall_score'),
        default=(sum(per_answer_scores) / len(per_answer_scores)) if per_answer_scores else 0.0
    )

    # 6. Update Course Progress if Passed
    if passed_exam:
        prog = db.query(VideoProgress).filter(VideoProgress.video_id == video_id).first()
        if not prog:
            prog = VideoProgress(video_id=video_id, user_id="user")
            db.add(prog)
        prog.completed = True
        prog.score = _to_int(overall_score, default=0)
        prog.updated_at = datetime.utcnow()
    
    db.commit()

    # 7. Find Next Video ID
    next_video_id = None
    if passed_exam:
        current_vid = db.query(Video).filter(Video.id == video_id).first()
        if current_vid:
            # Find next video with higher order
            next_vid = db.query(Video).filter(
                Video.course_id == current_vid.course_id, 
                Video.order > current_vid.order
            ).order_by(Video.order).first()
            if next_vid:
                next_video_id = next_vid.id

    return {
        "transcription": final_text,
        "overall_score": overall_score,
        "passed": passed_exam,
        "feedback": result.get('feedback', ""),
        "next_video_id": next_video_id
    }
