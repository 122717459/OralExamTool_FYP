# mock_exam.py
from flask import Blueprint, request, jsonify, session
import uuid
import time

mock_exam_bp = Blueprint("mock_exam", __name__)

# Dev-only in-memory store (key: exam_id)
MOCK_EXAMS = {}

EXAM_BLUEPRINT = [
    {
        "id": "intro",
        "title": "Introduction",
        "description": "Introduce yourself, basic personal info, where you live, family, general background.",
        "num_questions": 2,
    },
    {
        "id": "school",
        "title": "School Life",
        "description": "Talk about school subjects, teachers, timetable, what you like/dislike, school routine.",
        "num_questions": 2,
    },
    {
        "id": "hobbies",
        "title": "Hobbies & Free Time",
        "description": "Talk about hobbies, sports, music, friends, what you do on weekends.",
        "num_questions": 2,
    },
    {
        "id": "future",
        "title": "Future Plans",
        "description": "Talk about future career plans, dreams, goals, where you want to travel or live.",
        "num_questions": 2,
    },
    {
        "id": "opinion",
        "title": "Opinion / Discussion",
        "description": "Give opinions and justify them, discuss pros/cons, simple debate style.",
        "num_questions": 2,
    },
]

# Creates a new mock exam session this prepares everything needed to run the exam
def _new_exam_session(target_language: str, difficulty: str):
    # Expand blueprint into a question queue
    question_queue = []
    for section in EXAM_BLUEPRINT:
        for i in range(section["num_questions"]):
            question_queue.append({
                "section_id": section["id"],
                "section_title": section["title"],
                "section_description": section["description"],
                "index_in_section": i,
            })

    return {
        "created_at": time.time(),
        "target_language": target_language,
        "difficulty": difficulty,
        "current_index": 0,
        "question_queue": question_queue,
        "responses": [],  # appended as user answers
        # each response will later look like:
        # { section_id, question, transcript, corrected, score, ... }
    }

# Creates a new exam session when the user presses start exam
@mock_exam_bp.route("/api/mock/start", methods=["POST"])
def start_mock_exam():
    data = request.get_json(force=True) or {}
    target_language = data.get("target_language", "French")
    difficulty = data.get("difficulty", "Beginner")

    exam_id = str(uuid.uuid4())
    MOCK_EXAMS[exam_id] = _new_exam_session(target_language, difficulty)

    # Store exam_id in flask session so frontend doesn't have to manage it (optional but handy)
    session["mock_exam_id"] = exam_id

    return jsonify({
        "exam_id": exam_id,
        "blueprint": EXAM_BLUEPRINT,
        "current_index": 0,
        "total_questions": len(MOCK_EXAMS[exam_id]["question_queue"]),
        "message": "Mock exam session created."
    })
