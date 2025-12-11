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
        new_vid = Video(course_id=new_course.id, youtube_id=v['youtube_id'], title=v['title'], order=idx, duration=v['duration'])
        db.add(new_vid)
    db.commit()

    return RedirectResponse(url=f"/", status_code=303)

@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)):
    courses = db.query(Course).all()
    return templates.TemplateResponse("admin.html", {"request": request, "courses": courses})

@router.post("/admin/toggle_course/{course_id}")
def toggle_course_visibility(course_id: int, hide: bool = Form(...), db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if course:
        course.is_hidden = hide
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@router.get("/course/{course_id}", response_class=HTMLResponse)
def player(request: Request, course_id: int, video_id: Optional[int] = None, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    target_video = None
    if video_id:
        target_video = db.query(Video).filter(Video.id == video_id, Video.course_id == course_id).first()
    
    if not target_video:
        target_video = course.videos[0] if course.videos else None

    if not target_video:
        return RedirectResponse(url="/")

    prog = db.query(VideoProgress).filter(VideoProgress.video_id == target_video.id).first()
    
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
    for v in course.videos:
        p = db.query(VideoProgress).filter(VideoProgress.video_id == v.id).first()
    # Sidebar
    sidebar_videos = []
    completed_count = 0
    previous_completed = True # First video is always unlocked
    
    # Sort videos by order to ensure locking logic works sequentially
    sorted_videos = sorted(course.videos, key=lambda x: x.order)
    
    for v in sorted_videos:
        p = db.query(VideoProgress).filter(VideoProgress.video_id == v.id).first()
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
    
    # 4. Save Answers (Individual)
    # We save individual records for history tracking, even if graded in batch
    for q_id in result.get('answered_question_ids', []):
        score = result['individual_scores'].get(str(q_id), 0)
        # Check if actually passed (e.g. > 70)
        is_pass = score >= 70
        
        new_answer = Answer(
            question_id=q_id,
            user_answer=final_text, # We save full transcript for each
            is_correct=is_pass,
            rating=score,
            feedback=result.get('feedback', "")
        )
        db.add(new_answer)
    
    # 5. Update Course Progress if Passed
    passed_exam = result.get('passed', False)
    if passed_exam:
        prog = db.query(VideoProgress).filter(VideoProgress.video_id == video_id).first()
        if not prog:
            prog = VideoProgress(video_id=video_id, user_id="user")
            db.add(prog)
        prog.completed = True
        prog.updated_at = datetime.utcnow()
    
    db.commit()

    # 6. Find Next Video ID
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
        "overall_score": result.get('overall_score', 0),
        "passed": passed_exam,
        "feedback": result.get('feedback', ""),
        "next_video_id": next_video_id
    }
