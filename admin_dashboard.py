import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.models import Course, Video, VideoProgress, Question, Answer

# Page Config
st.set_page_config(page_title="LearningDB Explorer", layout="wide")

# Database Connection
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db = next(get_db())

# Title
st.title("📚 Learning System DB Explorer")

# Sidebar
st.sidebar.header("Navigation")
view_option = st.sidebar.radio("View", ["Courses & Progress", "All Videos", "Q&A Analysis"])

if view_option == "Courses & Progress":
    st.header("Courses Overview")
    courses = db.query(Course).all()
    
    if not courses:
        st.warning("No courses found.")
    else:
        # Create DataFrame
        data = []
        for c in courses:
            total_videos = len(c.videos)
            completed_videos = 0
            for v in c.videos:
                prog = db.query(VideoProgress).filter(VideoProgress.video_id == v.id).first()
                if prog and prog.completed:
                    completed_videos += 1
            
            progress = int((completed_videos / total_videos * 100)) if total_videos > 0 else 0
            
            data.append({
                "ID": c.id,
                "Title": c.title,
                "Videos": total_videos,
                "Progress (%)": f"{progress}%",
                "Playlist ID": c.playlist_id
            })
        
        st.dataframe(pd.DataFrame(data), hide_index=True, use_container_width=True)

        st.divider()
        st.subheader("Deep Dive: Select a Course")
        selected_course_title = st.selectbox("Choose Course", [c.title for c in courses])
        
        if selected_course_title:
            course = db.query(Course).filter(Course.title == selected_course_title).first()
            
            # Show Videos in this course
            v_data = []
            previous_completed = True
            sorted_videos = sorted(course.videos, key=lambda x: x.order)
            
            for v in sorted_videos:
                prog = db.query(VideoProgress).filter(VideoProgress.video_id == v.id).first()
                is_completed = prog.completed if prog else False
                is_locked = not previous_completed
                
                v_data.append({
                    "Order": v.order + 1,
                    "Title": v.title,
                    "Duration (s)": v.duration,
                    "Status": "✅ Completed" if is_completed else ("🔒 LOCKED" if is_locked else "🔓 Open"),
                    "Last Watched": prog.last_watched_timestamp if prog else 0
                })
                # Update for next
                previous_completed = is_completed
            
            st.table(pd.DataFrame(v_data))

elif view_option == "All Videos":
    st.header("All Videos Repository")
    videos = db.query(Video).all()
    # Simple list
    df = pd.DataFrame([{
        "ID": v.id, 
        "Course ID": v.course_id, 
        "Title": v.title, 
        "YouTube ID": v.youtube_id
    } for v in videos])
    st.dataframe(df, use_container_width=True)

elif view_option == "Q&A Analysis":
    st.header("Exam Results & Answers")
    
    # Filter by Video
    videos = db.query(Video).all()
    vid_map = {f"{v.id}: {v.title}": v.id for v in videos}
    
    selected_vid_label = st.selectbox("Filter by Video", ["All"] + list(vid_map.keys()))
    
    query = db.query(Answer)
    if selected_vid_label != "All":
        vid_id = vid_map[selected_vid_label]
        # Join Question to filter by video
        query = query.join(Question).filter(Question.video_id == vid_id)
    
    answers = query.order_by(Answer.created_at.desc()).all()
    
    if not answers:
        st.info("No answers found.")
    else:
        a_data = []
        for a in answers:
            # Fetch question text
            q = db.query(Question).filter(Question.id == a.question_id).first()
            a_data.append({
                "ID": a.id,
                "Time": a.created_at,
                "Question": q.text if q else "Unknown",
                "User Answer": a.user_answer,
                "Rating": a.rating,
                "Pass": "✅" if a.is_correct else "❌",
                "Feedback": a.feedback
            })
        
        st.dataframe(pd.DataFrame(a_data), use_container_width=True)
