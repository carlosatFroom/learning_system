import os
import json
import tempfile
from typing import List, Dict, Optional, Union
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Initialize Groq client
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

MODEL_TEXT = "llama-3.1-8b-instant"
MODEL_AUDIO = "whisper-large-v3-turbo"

def transcribe_audio(audio_bytes: bytes) -> str:
    """
    Transcribes audio bytes using Groq Whisper model.
    """
    try:
        # Groq API expects a file-like object or path. 
        # We'll use a temp file to be safe with the SDK.
        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as tmp_file:
            tmp_file.write(audio_bytes)
            tmp_path = tmp_file.name

        with open(tmp_path, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(tmp_path, file.read()),
                model=MODEL_AUDIO,
                temperature=0,
                response_format="json", # simpler than verbose_json for just text
            )
        
        os.unlink(tmp_path)
        return transcription.text
    except Exception as e:
        print(f"Error transcribing audio: {e}")
        return ""

def generate_questions(transcript_text: str, num_questions: int = 3) -> List[Dict]:
    """
    Generates open-ended questions based on the transcript.
    """
    prompt = f"""
    You are an AI Tutor. Create {num_questions} OPEN-ENDED questions based on the text below.
    The questions should test deep understanding, not just recall.
    
    Transcript:
    "{transcript_text[:12000]}..." 
    
    Return valid JSON list of objects with keys:
    'question' (string),
    'context' (string - brief snippet from text relevant to answer).
    """

    try:
        completion = client.chat.completions.create(
            model=MODEL_TEXT,
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant. Output strictly valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            response_format={"type": "json_object"} 
        )
        content = completion.choices[0].message.content
        data = json.loads(content)
        
        if isinstance(data, list): return data
        if 'questions' in data: return data['questions']
        return [data]

    except Exception as e:
        print(f"Gen Questions Error: {e}")
        return [{"question": "Describe the main topic.", "context": "Fallback"}]

def evaluate_answer(question_text: str, user_answer_text: str, history: Optional[Dict] = None) -> Dict:
    """
    Evaluates an answer on 0-100 scale using Llama 3.1.
    If 'history' is provided, it contains {'previous_answer': str, 'previous_rating': int}.
    """
    
    context_block = ""
    if history:
        context_block = f"""
        CONTEXT - PREVIOUS ATTEMPT:
        Student's Previous Answer: "{history.get('previous_answer')}"
        Previous Rating: {history.get('previous_rating')}
        
        INSTRUCTION:
        The student is attempting to improve their answer or answer a follow-up. 
        Evaluate the NEW Answer below in light of the previous attempt. 
        If they have addressed the gaps, give a higher score.
        """

    prompt = f"""
    Question: "{question_text}"
    {context_block}
    
    NEW Student Answer: "{user_answer_text}"
    
    Assess the quality of the answer. 
    Return a valid JSON object with:
    'rating': (integer 0-100),
    'feedback': (string, constructive criticism or praise),
    'follow_up_question': (string or null). 
    
    Logic:
    - If rating < 70, provide a follow-up question that clarifies the concept WITHOUT giving the answer.
    - If rating >= 70, 'follow_up_question' should be null.
    """
    
    try:
        completion = client.chat.completions.create(
            model=MODEL_TEXT,
            messages=[
                {"role": "system", "content": "You are a strict tutor. Output JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        content = completion.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        print(f"Eval Error: {e}")
        return {"rating": 0, "feedback": "Error evaluating.", "follow_up_question": None}

def evaluate_exam(questions: List[Dict], user_input: str) -> Dict:
    """
    Evaluates a batch exam where the user answers a subset of questions.
    Input:
        questions: List of dicts [{'id': 1, 'text': '...'}, ...]
        user_input: String containing answers like "1. answer... 2. answer..."
    
    Returns:
        {
            "passed": bool,
            "overall_score": int,
            "feedback": str,
            "answered_ids": [int]
        }
    """
    q_text = "\n".join([f"ID {q['id']}: {q['text']}" for q in questions])
    
    prompt = f"""
    The user was presented with these questions:
    {q_text}
    
    The user submitted this text (Audio Transcript or Typed):
    "{user_input}"
    
    INSTRUCTIONS:
    1. Identify which questions the user attempted to answer. Look for clear indicators like "1.", "Question 2", or context matching.
    2. Evaluate each answer.
    3. Calculate an overall score (0-100) based ONLY on the answered questions.
       - If they answered 0 questions, score is 0.
       - Requirement: They must have answered at least 2 questions reasonably well (>70 each) to pass.
    
    Return JSON:
    {{
        "answered_question_ids": [list of integers],
        "individual_scores": {{ "question_id": score_int, ... }},
        "overall_score": int,
        "passed": bool,
        "feedback": "Overall feedback summary..."
    }}
    """
    
    try:
        completion = client.chat.completions.create(
            model=MODEL_TEXT,
            messages=[
                {"role": "system", "content": "You are an Exam Proctor AI. Output strict JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        print(f"Exam Eval Error: {e}")
        return {"passed": False, "overall_score": 0, "feedback": f"Error: {e}", "answered_question_ids": []}

def generate_refresher(completed_videos: List[str]) -> str:
    return "Refresher functionality coming soon."
