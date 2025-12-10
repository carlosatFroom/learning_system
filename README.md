# Learning System

**A Learner-Centric, Accountable Video Learning Platform.**

## Philosophy: Why Build This?

In an era of abundant free educational content (Khan Academy, YouTube, Coursera), the bottleneck is no longer **access** to information, but **accountability** and **retention**.

While platforms like Khan Academy are excellent, they are closed ecosystems. This project empowers the **learner** to curate their own curriculum from the vast ocean of YouTube content while enforcing a rigorous "Active Recall" mechanism.

**Key Principles:**
1.  **Accountability**: You cannot simply "watch" a video. You must confirm understanding to unlock the next step.
2.  **No Passive Consumption**: Videos are gated. You must pass an AI-graded exam to proceed.
3.  **Active Recall**: The system asks open-ended questions, requiring you to articulate answers (via text or voice), which is proven to improve retention compared to multiple-choice quizzes.
4.  **Ownership**: You own the database (`learning.db`). You control the content selection.

## Features
- **YouTube Ingestion**: Import playlists directly into your course library.
- **AI Tutor (Groq/Llama 3)**: Automatically generates open-ended questions based on video transcripts.
- **Voice Answers**: Use your microphone to answer orally, transcribed by Whisper.
- **Gated Progression**: "Exam Mode" ensures you only move forward when you've mastered the current concept.
- **Detailed Tracking**: Dashboard visualizes completion and timestamps.

## Installation

### Prerequisites
- **Python 3.9+**
- **Git**
- **Groq API Key** (Get one at [console.groq.com](https://console.groq.com))

### 1. Clone the Repository
```bash
git clone https://github.com/carlosatFroom/learning_system.git
cd learning_system
```

### 2. Setup Virtual Environment & Dependencies

We have provided a helper script to automate the setup across platforms.

**Mac / Linux:**
```bash
python3 setup_env.py
```
*Note: If you encounter an error about `venv` missing on Linux, run `sudo apt-get install python3-venv` and try again.*

**Windows:**
```bash
python setup_env.py
```

### 3. Environment Configuration
Create a `.env` file in the `backend/` directory:
```bash
# Mac/Linux
touch backend/.env

# Windows
echo. > backend/.env
```
Add your keys and database config:
```ini
GROQ_API_KEY=your_actual_api_key_here

# Optional: Remote SQL Database for Sync (MariaDB/MySQL)
sql_user=myuser
sql_pwd=mypassword
sql_host=myserver.com
sql_db=learning_system
```

## Usage

### 1. Start the Backend Server
This runs the core application (Player, API, Database).
...
### 2. Start the Admin Dashboard (Optional)
Use this to explore the database, view exam grades, and manage Cloud Sync.
...

## Key Features
*   **Video Gating:** Inspects `VideoProgress` to unlock content sequentially.
*   **Exam Mode:** 3-question exams generated from transcripts. Passing (>70%) unlocks the next video.
*   **Transcript Storage:** Transcripts are fetched, saved locally, and used for quiz generation.
*   **Cloud Sync:** Backs up your local SQLite data to a remote SQL server (with `learning_system_` namespacing). Includes a "Reset Remote" feature to handle schema mismatches.

**Mac / Linux:**
```bash
venv/bin/uvicorn backend.main:app --reload
```

**Windows:**
```bash
venv\Scripts\uvicorn backend.main:app --reload
```
Open your browser to: **http://127.0.0.1:8000**

### 2. Start the Admin Dashboard (Optional)
Use this to explore the database contents, view grades, and manage data.

**Mac / Linux:**
```bash
venv/bin/streamlit run admin_dashboard.py
```

**Windows:**
```bash
venv\Scripts\streamlit run admin_dashboard.py
```

## Project Structure
- `backend/`: FastAPI application, database models, and services.
- `backend/services/`: AI integration (Groq) and YouTube services.
- `backend/templates/`: Jinja2 HTML templates for the frontend.
- `learning.db`: SQLite database file (created on first run).
