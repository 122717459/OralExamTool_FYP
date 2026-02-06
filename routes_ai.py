from flask import Blueprint, request, jsonify
from sqlalchemy.orm import Session
from db import get_db
from models import AnalysisLog, ExamSession, ExamTurn
from config import settings
from audit import write_event
from flask_login import login_required, current_user
import openai
import json
from datetime import datetime
import re

bp_ai = Blueprint("ai_bp", __name__, url_prefix="/api")

#  Configure the OpenAI client (OpenAI)  I am going with OpenAI will adjust this code later to remove the azure.
# This code is from ChatGPT
if settings.AZURE_OPENAI_ENDPOINT and settings.AZURE_OPENAI_API_KEY:
    # Azure OpenAI
    openai_client = openai.AzureOpenAI(
        api_key=settings.AZURE_OPENAI_API_KEY,
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        api_version="2024-05-01-preview",  # use your Azure resource's API version
    )
    MODEL_ID = settings.AZURE_OPENAI_DEPLOYMENT  # your deployment name
else:
    # Standard OpenAI
    openai_client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    MODEL_ID = "gpt-4o-mini"  # small/fast model



BANDS = ["Excellent", "Good", "OK", "Needs Work"]

def evaluate_answer_with_bands(language: str, difficulty: str, question: str, transcript: str) -> dict:
    """
    Returns a dict with:
      feedback_en, corrected_answer_target, tips_en,
      fluency_band, grammar_band, vocabulary_band, pronunciation_band, overall_band,
      major_mistakes_en (short)

    Rules:
    - feedback_en and tips_en are always English
    - corrected_answer_target is in the exam target language
    - major_mistakes_en should only contain serious errors
    """

    BANDS = ["Excellent", "Good", "OK", "Needs Work"]

    def band_or_default(value):
        return value if value in BANDS else "OK"

    def normalize_text(value):
        if isinstance(value, list):
            return "\n".join(str(v) for v in value).strip()
        if isinstance(value, str):
            return value.strip()
        return ""

    if language == "french":
        target_lang_name = "French"
    elif language == "german":
        target_lang_name = "German"
    else:
        target_lang_name = "English"

    system_msg = (
        "You are a strict but helpful oral-exam evaluator.\n"
        "You MUST output valid JSON only.\n"
        "Rules:\n"
        "- Feedback MUST be in English.\n"
        f"- The corrected answer MUST be written in {target_lang_name}.\n"
        "- Use ONLY these band labels: Excellent, Good, OK, Needs Work.\n"
        "- If there are no serious errors, return major_mistakes_en as an empty list.\n"
    )

    user_msg = (
        f"Exam language (student target): {target_lang_name}\n"
        f"Difficulty: {difficulty}\n"
        f"Question: {question}\n"
        f"Student answer (transcript): {transcript}\n\n"
        "Return JSON with keys:\n"
        "feedback_en: short bullet points in English\n"
        f"corrected_answer_target: one strong corrected answer in {target_lang_name}\n"
        "tips_en: 1–2 short tips in English\n"
        "bands: object with keys fluency, grammar, vocabulary, pronunciation, overall\n"
        "major_mistakes_en: list of 1–3 serious mistakes, or empty list if none\n"
    )

    resp = openai_client.chat.completions.create(
        model=MODEL_ID,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
        max_tokens=500,
        response_format={"type": "json_object"},
        timeout=30,  # <-- ADD THIS LINE
    )

    raw = (resp.choices[0].message.content or "").strip()
    result = json.loads(raw)

    bands = result.get("bands") or {}

    major = result.get("major_mistakes_en") or []
    if isinstance(major, str):
        major = [major]

    return {
        "feedback_en": normalize_text(result.get("feedback_en")),
        "corrected_answer_target": normalize_text(result.get("corrected_answer_target")),
        "tips_en": normalize_text(result.get("tips_en")),

        "fluency_band": band_or_default(bands.get("fluency")),
        "grammar_band": band_or_default(bands.get("grammar")),
        "vocabulary_band": band_or_default(bands.get("vocabulary")),
        "pronunciation_band": band_or_default(bands.get("pronunciation")),
        "overall_band": band_or_default(bands.get("overall")),

        "major_mistakes_en": "\n".join(f"- {m}" for m in major) if major else "",
    }






def db_session():
    return next(get_db())
# generates a SQLAlchemy session, Calling above pulls one session you can use with a block.



EXAM_QUESTION_BANK = {
    "introduction": {
        "english": [
            "Can you introduce yourself?",
            "Tell me a little about your hobbies."
        ],
        "french": [
            "Peux-tu te présenter ?",
            "Parle-moi de tes loisirs."
        ],
        "german": [
            "Kannst du dich vorstellen?",
            "Erzähl mir etwas über deine Hobbys."
        ],
    },
    "school": {
        "english": [
            "What subjects are you studying?",
            "What do you like or dislike about school?"
        ],
        "french": [
            "Quelles matières étudies-tu ?",
            "Qu’est-ce que tu aimes ou n’aimes pas à l’école ?"
        ],
        "german": [
            "Welche Fächer lernst du?",
            "Was magst oder magst du nicht an der Schule?"
        ],
    },
}








@bp_ai.post("/start_exam")
def start_exam():
    """
    Starts an oral exam style conversation.

    JSON:
    {
      "topic": "school life",
      "difficulty": "beginner" | "moderate" | "expert"
    }
    """
    data = request.get_json(force=True) or {}
    topic = (data.get("topic") or "general English conversation").strip()
    difficulty = (data.get("difficulty") or "moderate").strip().lower()
    language = (data.get("language") or "english").strip().lower()

    # Map your difficulty labels to approximate CEFR-like descriptions.
    if difficulty == "beginner":
        level_desc = "A2 (beginner)"
        difficulty_hint = "Use simple sentences and common vocabulary. Avoid complex grammar."
    elif difficulty == "expert":
        level_desc = "B2–C1 (advanced)"
        difficulty_hint = "Ask more challenging, detailed questions. Encourage longer, more complex answers."
    else:
        level_desc = "B1 (intermediate)"
        difficulty_hint = "Use everyday vocabulary but allow some detail and explanation."

    if language == "french":
        lang_name = "French"
    elif language == "german":
        lang_name = "German"
    else:
        lang_name = "English"

    system_msg = (
        f"You are an oral-exam interlocutor for a {level_desc} learner. "
        f"The exam language is {lang_name}. "
        f"ALWAYS speak and write in {lang_name}. "
        f"The practice topic is: {topic}. "
        f"{difficulty_hint} "
        "Ask ONE clear, open-ended question that the student can answer in 20–40 seconds. "
        "Do not include any explanations or meta text. Only output the question itself."
    )

    try:
        resp = openai_client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": f"Start the exam with a question about: {topic}."},
            ],
            temperature=0.4,
            max_tokens=100,
        )
        question = (resp.choices[0].message.content or "").strip()
        return jsonify({
            "question": question,
            "model": MODEL_ID
        }), 200

    except Exception as e:
        return jsonify({"error": "start_exam failed", "details": str(e)}), 500



@bp_ai.post("/exam/answer")
@login_required
def exam_answer():
    """
    Saves the student's transcript for the current question and returns the next question.

    JSON:
    {
      "session_id": 123,
      "question_number": 1,
      "transcript": "..."
    }
    """
    data = request.get_json(force=True) or {}

    session_id = data.get("session_id")
    question_number = data.get("question_number")
    transcript = (data.get("transcript") or "").strip()

    if not session_id or not question_number:
        return jsonify({"error": "session_id and question_number are required"}), 400
    if not transcript:
        return jsonify({"error": "transcript is required"}), 400

    db = db_session()
    try:
        # 1) Load session and confirm ownership
        session = db.get(ExamSession, int(session_id))
        if not session or session.user_id != current_user.id:
            return jsonify({"error": "session not found"}), 404
        if session.status != "in_progress":
            return jsonify({"error": "session is not in progress"}), 400

        # 2) Load the current turn
        turn = db.query(ExamTurn).filter(
            ExamTurn.session_id == session.id,
            ExamTurn.question_number == int(question_number)
        ).first()
        if not turn:
            return jsonify({"error": "turn not found"}), 404

        # 3) Save transcript
        turn.transcript = transcript
        db.add(turn)
        db.commit()

        # 4) Decide next question (fixed bank)
        # For now: 2 intro questions, then 2 school questions, then finish.
        language = session.language

        sequence = [
            ("introduction", 0),
            ("introduction", 1),
            ("school", 0),
            ("school", 1),
        ]

        next_index = int(question_number)  # if we just answered #1, next_index points to item 2
        if next_index >= len(sequence):
            # no more questions -> finish (we'll make a proper /finish endpoint next)
            session.status = "completed"
            session.completed_at = datetime.utcnow()
            db.add(session)
            db.commit()

            return jsonify({
                "done": True,
                "needs_finish": True,
                "session_id": session.id
            }), 200

        next_section, q_idx = sequence[next_index]
        next_question_text = EXAM_QUESTION_BANK[next_section][language][q_idx]
        next_q_number = int(question_number) + 1

        # 5) Create next turn (question only)
        next_turn = ExamTurn(
            session_id=session.id,
            question_number=next_q_number,
            section=next_section,
            question_text=next_question_text,
        )
        db.add(next_turn)
        db.commit()


        return jsonify({
            "done": False,
            "session_id": session.id,
            "question_number": next_q_number,
            "section": next_section,
            "question": next_question_text,

        }), 200



    finally:
        db.close()




# This code is from ChatGPT
@bp_ai.post("/exam_turn")
@login_required
def exam_turn():
    """
    Handles one turn of the oral exam:

    JSON:
    {
      "transcript": "student's spoken answer",
      "last_question": "What do you enjoy about your studies?",
      "topic": "school life",
      "difficulty": "beginner" | "moderate" | "expert"
    }
    """
    data = request.get_json(force=True) or {}
    transcript = (data.get("transcript") or "").strip()
    last_question = (data.get("last_question") or "").strip()
    topic = (data.get("topic") or "general English conversation").strip()
    difficulty = (data.get("difficulty") or "moderate").strip().lower()
    language = (data.get("language") or "english").strip().lower()

    if not transcript:
        return jsonify({"error": "transcript is required"}), 400
    if not last_question:
        return jsonify({"error": "last_question is required"}), 400

    # Map difficulty to descriptive text for the model.
    if difficulty == "beginner":
        level_desc = "A2 (beginner)"
        difficulty_hint = (
            "Expect short, simple answers with basic vocabulary. "
            "Focus feedback on simple grammar and basic mistakes."
        )
    elif difficulty == "expert":
        level_desc = "B2–C1 (advanced)"
        difficulty_hint = (
            "Expect longer, detailed answers with more complex grammar. "
            "Focus feedback on nuance, cohesion, and advanced accuracy."
        )
    else:
        level_desc = "B1 (intermediate)"
        difficulty_hint = (
            "Expect answers with everyday vocabulary and some detail. "
            "Focus feedback on common grammar mistakes and fluency."
        )

    if language == "french":
        lang_name = "French"
    elif language == "german":
        lang_name = "German"
    else:
        lang_name = "English"

    system_msg = (
        f"You are a strict but fair oral-exam tutor for a {level_desc} learner.\n"
        f"Target language (student should speak): {lang_name}.\n"
        "IMPORTANT OUTPUT RULES:\n"
        "- You MUST return a JSON object with keys: feedback, corrected_answer, tip, score, next_question.\n"
        "- feedback and tip MUST be in English.\n"
        f"- corrected_answer MUST be written in {lang_name}.\n"
        "- Do NOT give generic advice. Only mention issues that actually appear in the student's transcript.\n"
        "- In feedback, include 1–2 short quoted snippets from the student's transcript as evidence "
        "for any criticism. If there are no real errors, explicitly say so.\n"
        "- corrected_answer rules:\n"
        f"  * If the student answer is already good and natural in {lang_name}, set corrected_answer to 'NO_CHANGES_NEEDED'.\n"
        f"  * If there are problems, corrected_answer MUST be a better version in {lang_name} and MUST differ from the original.\n"
        "\n"
        "SCORING RUBRIC (be strict, avoid inflated scores):\n"
        "1–2: mostly unintelligible / off-topic\n"
        "3–4: very limited, many basic errors, hard to follow\n"
        "5–6: understandable, some errors and/or limited detail\n"
        "7: good, minor errors only, mostly natural\n"
        "8: very good, clear + natural, minor slips\n"
        "9: excellent, fluent + accurate, strong vocabulary\n"
        "10: near-native for this level (rare)\n"
        "\n"
        "The next_question MUST be one clear open-ended question in the TARGET language "
        f"({lang_name}) and should fit a 20–40 second spoken answer.\n"
    )

    user_msg = (
        f"Exam topic: {topic}\n"
        f"Examiner question: {last_question}\n"
        f"Student answer (spoken transcript): {transcript}\n\n"
        "Analyse this as a SPOKEN answer: prioritize clarity and natural phrasing over perfect writing punctuation.\n"
        "Now analyse the student's answer and continue the exam."
    )

    try:
        resp = openai_client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=400,
            response_format={"type": "json_object"},  # Ask the model for proper JSON
        )
        raw = (resp.choices[0].message.content or "").strip()

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: if the model gives non-JSON, still return something useful.
            result = {
                "feedback": raw,
                "corrected_answer": "",
                "tip": "",
                "score": None,
                "next_question": "Can you tell me more about this topic?"
            }

            def _normalize_for_compare(s: str) -> str:
                s = (s or "").strip().lower()
                s = re.sub(r"\s+", " ", s)
                s = re.sub(r"[^\w\s]", "", s)  # drop punctuation
                return s

            student = (transcript or "").strip()
            corrected = (result.get("corrected_answer") or "").strip()

            # If corrected answer is effectively identical to student answer, treat as no changes needed
            if corrected and _normalize_for_compare(corrected) == _normalize_for_compare(student):
                result["corrected_answer"] = "NO_CHANGES_NEEDED"

            # If no changes are needed, score should be high (9–10 depending on length)
            if result.get("corrected_answer") == "NO_CHANGES_NEEDED":
                word_count = len(student.split())
                if word_count < 6:
                    # too short to be a "10"
                    result["score"] = max(int(result.get("score") or 0), 7)
                else:
                    result["score"] = max(int(result.get("score") or 0), 9)

        feedback_text = result.get("feedback", "")

        # Save a log row in the database (similar to /feedback)
        with db_session() as db:  # type: Session
            log = AnalysisLog(
                input_text=transcript,
                feedback_text=feedback_text,
                model_name=MODEL_ID,
                user_id=current_user.id
            )
            db.add(log)
            db.commit()
            write_event("AI_EXAM_TURN_CREATED", {
                "id": log.id,
                "model": MODEL_ID,
                "input_chars": len(transcript),
            })

        return jsonify({
            "feedback": result.get("feedback", ""),
            "corrected_answer": result.get("corrected_answer", ""),
            "tip": result.get("tip", ""),
            "score": result.get("score", None),
            "next_question": result.get("next_question", ""),
            "model": MODEL_ID
        }), 200

    except Exception as e:
        return jsonify({"error": "exam_turn failed", "details": str(e)}), 500




#This Code is from ChatGPT
@bp_ai.post("/feedback")
@login_required
def get_feedback(): # Registers a post endpoint at /api/feedback. lays out expected JSON payload.
    """
    POST JSON:
    {
      "transcript": "I go to school every day and I like study English",
      "prompt": "Talk about your school."
    }
    """
    data = request.get_json(force=True) or {}
    transcript = (data.get("transcript") or "").strip()
    prompt = (data.get("prompt") or "").strip()

    if not transcript:
        return jsonify({"error": "transcript is required"}), 400
    # Parses JSON body, Extracts transcript (required) and prompt ( optional) trimming white space. If transcript is empty returns error.

    system_msg = "You are a concise, supportive language tutor for oral exams." # Sets the assistant's role
    user_msg = (
        f"Question (optional): {prompt}\n"
        f"Student answer: {transcript}\n\n"
        "Return:\n"
        "1) Key mistakes (grammar/word choice/fluency)\n"
        "2) Corrected answer (one good version)\n"
        "3) One tip to improve"
        "4) Score the student's answer from 1 to 10. Anchors: 10=excellent, 7–8=good, 5=okay, 3=weak, 1=very poor."
    ) # Keeps the model focused, structured, and consice.

    try:
        resp = openai_client.chat.completions.create( # Calls the chat API
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2, # low randomness - consistent exam-like feedback
            max_tokens=250, # Caps the output length.
        )
        feedback = resp.choices[0].message.content.strip() # Extracts the assistant's text (feedback) from the first choice).

        # Save a log row
        with db_session() as db:  # type: Session # Opens a DB session, creates an AnalysisLog row capturing, The original input, The full model feedback, Which model name was used.
            log = AnalysisLog(
                input_text=transcript,
                feedback_text=feedback,
                model_name=MODEL_ID,
                user_id=current_user.id
            )

            db.add(log)
            db.commit()
            write_event("AI_FEEDBACK_CREATED", {
                "id": log.id,
                "model": MODEL_ID,
                "input_chars": len(transcript),
            }) # Commits the row and sends an audit event with a few metadata fields (ID, model, input, length)

        return jsonify({"feedback": feedback, "model": MODEL_ID}), 200

    except Exception as e:
        # Surface error message for debugging during PoC
        return jsonify({"error": str(e)}), 500 # If anything fails return 500 error internal server error.



@bp_ai.post("/dictionary_ai")
def dictionary_ai():
    """
    Simple dictionary helper using the chat model.

    Expects JSON:
    {
      "term": "complicated",
      "difficulty": "beginner" | "moderate" | "expert"   (optional)
    }

    Returns JSON:
    {
      "headword": "complicated",
      "part_of_speech": "adjective",
      "meaning": "...simple explanation...",
      "examples": ["...", "..."],
      "synonyms": ["..."]
    }
    """
    data = request.get_json(force=True) or {}
    term = (data.get("term") or "").strip()
    difficulty = (data.get("difficulty") or "moderate").strip().lower()

    if not term:
        return jsonify({"error": "term is required"}), 400

    # Map difficulty to explanation style
    if difficulty == "beginner":
        level_desc = "A2 (beginner)"
        style_hint = (
            "Use very simple, clear English. Avoid advanced grammar. "
            "Imagine you are explaining this to a younger learner."
        )
    elif difficulty == "expert":
        level_desc = "B2–C1 (advanced)"
        style_hint = (
            "Use more precise language. You can mention nuances, but stay concise. "
            "Assume the learner has a strong base but still wants clarity."
        )
    else:
        # 'moderate'
        level_desc = "B1 (intermediate)"
        style_hint = (
            "Explain in clear, everyday English. "
            "Avoid very technical words, but allow some detail."
        )

    system_msg = (
        f"You are a concise, learner-friendly English dictionary for {level_desc} learners. "
        f"{style_hint} "
        "You MUST respond in JSON with keys: headword, part_of_speech, meaning, examples, synonyms.\n"
        "Rules:\n"
        "- headword: the main word or phrase being explained.\n"
        "- part_of_speech: e.g. 'noun', 'verb', 'adjective'.\n"
        "- meaning: 1–2 short sentences in simple English.\n"
        "- examples: a short list (1–3) of example sentences using the word naturally.\n"
        "- synonyms: a short list (0–5) of common synonyms, or an empty list if not relevant.\n"
        "Do not include any extra commentary outside the JSON structure."
    )

    user_msg = (
        f"Explain this word or phrase for an English learner: '{term}'. "
        "If it has several meanings, pick the most common everyday meaning."
    )

    try:
        resp = openai_client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=250,
            response_format={"type": "json_object"},
        )
        raw = (resp.choices[0].message.content or "").strip()

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: return something useful even if JSON parsing fails
            result = {
                "headword": term,
                "part_of_speech": "",
                "meaning": raw,
                "examples": [],
                "synonyms": []
            }

        # Small cleanup: make sure examples and synonyms are always lists
        examples = result.get("examples") or []
        synonyms = result.get("synonyms") or []
        if isinstance(examples, str):
            examples = [examples]
        if isinstance(synonyms, str):
            synonyms = [synonyms]

        clean = {
            "headword": result.get("headword", term),
            "part_of_speech": result.get("part_of_speech", ""),
            "meaning": result.get("meaning", ""),
            "examples": examples,
            "synonyms": synonyms,
        }

        return jsonify(clean), 200

    except Exception as e:
        return jsonify({"error": "dictionary_ai failed", "details": str(e)}), 500


@bp_ai.post("/exam/start")
@login_required
def exam_start():
    """
    Starts a new mock exam session and returns the first question.
    """
    data = request.get_json(force=True) or {}

    language = (data.get("language") or current_user.preferred_language or "english").lower()
    difficulty = (data.get("difficulty") or current_user.preferred_difficulty or "moderate").lower()

    # For now, always start with introduction section
    section = "introduction"
    question_text = EXAM_QUESTION_BANK[section][language][0]

    db = db_session()
    try:
        # 1) Create exam session
        session = ExamSession(
            user_id=current_user.id,
            language=language,
            difficulty=difficulty,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        # 2) Create first exam turn (question only)
        turn = ExamTurn(
            session_id=session.id,
            question_number=1,
            section=section,
            question_text=question_text,
        )
        db.add(turn)
        db.commit()

        return jsonify({
            "session_id": session.id,
            "question_number": 1,
            "section": section,
            "question": question_text,
        }), 200

    finally:
        db.close()


@bp_ai.post("/exam/finish")
@login_required
def exam_finish():
    """
    Marks an exam as completed and returns all turns.
    JSON:
    { "session_id": 123 }
    """
    data = request.get_json(force=True) or {}
    session_id = data.get("session_id")

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    db = db_session()
    try:
        session = db.get(ExamSession, int(session_id))
        if not session or session.user_id != current_user.id:
            return jsonify({"error": "session not found"}), 404

        if session.status != "completed":
            session.status = "completed"
            session.completed_at = datetime.utcnow()
            db.add(session)
            db.commit()

        turns = db.query(ExamTurn).filter(
            ExamTurn.session_id == session.id
        ).order_by(ExamTurn.question_number.asc()).all()

        # Generate evaluations now (mock exam: feedback only at the end)
        for t in turns[:1]:

            if not (t.transcript or "").strip():
                continue

            evaluation = evaluate_answer_with_bands(
                language=session.language,
                difficulty=session.difficulty,
                question=t.question_text,
                transcript=t.transcript
            )

            t.feedback_en = evaluation["feedback_en"]
            t.corrected_answer_target = evaluation["corrected_answer_target"]
            t.tips_en = evaluation["tips_en"]

            t.fluency_band = evaluation["fluency_band"]
            t.grammar_band = evaluation["grammar_band"]
            t.vocabulary_band = evaluation["vocabulary_band"]
            t.pronunciation_band = evaluation["pronunciation_band"]
            t.overall_band = evaluation["overall_band"]

            # Append major mistakes if present and needs work
            needs_work = (
                    evaluation["overall_band"] == "Needs Work" or
                    evaluation["fluency_band"] == "Needs Work" or
                    evaluation["grammar_band"] == "Needs Work" or
                    evaluation["vocabulary_band"] == "Needs Work" or
                    evaluation["pronunciation_band"] == "Needs Work"
            )
            if needs_work and evaluation.get("major_mistakes_en"):
                t.feedback_en = (
                        (t.feedback_en or "")
                        + "\n\nMajor mistakes:\n"
                        + evaluation["major_mistakes_en"]
                ).strip()

        db.commit()

        return jsonify({
            "session_id": session.id,
            "status": session.status,
            "language": session.language,
            "difficulty": session.difficulty,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "completed_at": session.completed_at.isoformat() if session.completed_at else None,
            "turns": [
    {
        "question_number": t.question_number,
        "section": t.section,
        "question_text": t.question_text,
        "transcript": t.transcript,

        "feedback_en": t.feedback_en,
        "corrected_answer_target": t.corrected_answer_target,
        "tips_en": t.tips_en,

        "bands": {
            "fluency": t.fluency_band,
            "grammar": t.grammar_band,
            "vocabulary": t.vocabulary_band,
            "pronunciation": t.pronunciation_band,
            "overall": t.overall_band,
        }
    } for t in turns
]

        }), 200

    finally:
        db.close()
