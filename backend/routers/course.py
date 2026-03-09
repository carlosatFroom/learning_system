from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, UploadFile, File
from datetime import datetime
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List, Optional
from ..database import get_db
from ..models import Course, Video, VideoProgress, Question, Answer, Transcript
from ..services.youtube import get_playlist_info, get_video_transcript
from ..services.ai_tutor import generate_questions, evaluate_answer
from pydantic import BaseModel
import json


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
            "progress_percent": progress
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

@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)):
    courses = db.query(Course).all()
    status_code = request.query_params.get("status")
    status_messages = {
        "next_video_unlocked": "Unlocked the next video in sequence.",
        "all_videos_completed": "All videos are already unlocked and completed.",
        "no_videos": "This course has no videos to unlock.",
        "course_not_found": "Course not found."
    }
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
        "last_watched_timestamp": prog.last_watched_timestamp if prog else 0
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
