from backend.database import SessionLocal
from backend.models import Video, Course

db = SessionLocal()
courses = db.query(Course).all()
for course in courses:
    print(f"Course: {course.title} (ID: {course.id})")
    for video in course.videos:
        print(f"  - [{video.id}] {video.title}: youtube_id='{video.youtube_id}' (len={len(video.youtube_id)})")
db.close()
