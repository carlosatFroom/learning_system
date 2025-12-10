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

import os
from dotenv import load_dotenv

# Load env variables for local check
env_path = os.path.join(os.path.dirname(__file__), 'backend', '.env')
load_dotenv(env_path)

# Sidebar
st.sidebar.header("Navigation")

options = ["Courses & Progress", "All Videos", "Q&A Analysis"]
if os.getenv("sql_host") or os.getenv("REMOTE_DB_URL"):
    options.append("Cloud Sync")

view_option = st.sidebar.radio("View", options)

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
        
        st.dataframe(pd.DataFrame(data), hide_index=True, width='stretch')

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
    st.dataframe(df, width='stretch')

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
        
        st.dataframe(pd.DataFrame(a_data), width='stretch')

elif view_option == "Cloud Sync":
    st.header("☁️ Cloud Database Sync")

    # Fetch status from API
    import requests
    try:
        res = requests.get("http://127.0.0.1:8000/api/sync/status")
        if res.status_code == 200:
            status = res.json()
            
            # Metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Remote DB", "Configured" if status['remote_configured'] else "Not Configured")
            with col2:
                last_sync = status['last_sync'] or "Never"
                st.metric("Last Sync", last_sync)
            with col3:
                st.metric("Can Sync Now?", "Yes" if status['can_sync'] else "No")

            if not status['can_sync'] and status['message']:
                st.warning(f"Wait Condition: {status['message']}")
            
            st.divider()
            
            # Trigger
            if st.button("🔄 Sync Now (Force)", type="primary"):
                with st.spinner("Syncing data to Remote DB..."):
                    try:
                        sync_res = requests.post("http://127.0.0.1:8000/api/sync/trigger?force=true")
                        if sync_res.status_code == 200:
                            result = sync_res.json()
                            if result['status'] == 'success':
                                st.success("Sync Successful!")
                                st.json(result['details'])
                            else:
                                st.error(f"Sync Skipped: {result.get('message')}")
                        else:
                            st.error(f"Error: {sync_res.text}")
                    except Exception as e:
                        st.error(f"Request failed: {e}")
            
            st.write("") # Spacer
            if st.button("⚠️ Reset Remote DB & Sync", type="secondary"):
                st.warning("This will DELETE ALL DATA on the remote database and re-sync from local.")
                if st.button("Confirm Reset & Sync"):
                    with st.spinner("Resetting Remote DB and Syncing..."):
                        try:
                            sync_res = requests.post("http://127.0.0.1:8000/api/sync/trigger?force=true&reset=true")
                            if sync_res.status_code == 200:
                                result = sync_res.json()
                                if result['status'] == 'success':
                                    st.success("Reset & Sync Successful!")
                                    st.json(result['details'])
                                else:
                                    st.error(f"Sync Skipped: {result.get('message')}")
                            else:
                                st.error(f"Error: {sync_res.text}")
                        except Exception as e:
                            st.error(f"Request failed: {e}")

        else:
            st.error("Could not fetch sync status from backend.")
            
    except Exception as e:
        st.error(f"Backend unreachable: {e}. Is uvicorn running?")
