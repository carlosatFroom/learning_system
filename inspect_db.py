from backend.database import SessionLocal
from backend.models import Course, Video, Question, Answer, VideoProgress
from sqlalchemy.orm import Session
import sys

def inspect():
    db: Session = SessionLocal()
    try:
        print("="*50)
        print("DATABASE INSPECTION")
        print("="*50)
        
        courses = db.query(Course).all()
        print(f"\n[ COURSES FOUND: {len(courses)} ]")
        for c in courses:
            print(f"ID: {c.id} | Title: {c.title} | Playlist ID: {c.playlist_id}")
            print(f"  > Videos: {len(c.videos)}")
            
            for v in sorted(c.videos, key=lambda x: x.order):
                prog = db.query(VideoProgress).filter(VideoProgress.video_id == v.id).first()
                status = "COMPLETED" if prog and prog.completed else "LOCKED/OPEN"
                print(f"    - Vid {v.id}: {v.title} [{status}]")
                
                # Questions
                if v.questions:
                    print(f"      > Questions ({len(v.questions)}):")
                    for q in v.questions:
                        print(f"        Q{q.id}: {q.text[:60]}... (Kind: {q.kind})")
                        for a in q.answers:
                            print(f"          - Answer: {a.user_answer[:40]}... | Score: {a.rating} | Pass: {a.is_correct}")

    except Exception as e:
        print(f"Error inspecting DB: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    inspect()
