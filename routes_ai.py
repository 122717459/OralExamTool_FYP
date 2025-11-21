from flask import Blueprint, request, jsonify
from sqlalchemy.orm import Session
from db import get_db
from models import AnalysisLog
from config import settings
from audit import write_event
import openai
import json

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

def db_session():
    return next(get_db())
# generates a SQLAlchemy session, Calling above pulls one session you can use with a block.



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

    system_msg = (
        f"You are an oral-exam interlocutor for a {level_desc} English learner. "
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



# This code is from ChatGPT
@bp_ai.post("/exam_turn")
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

    system_msg = (
        f"You are a supportive but realistic oral-exam tutor for a {level_desc} English learner. "
        f"The practice topic is: {topic}. "
        f"{difficulty_hint} "
        "You are practising an oral exam with the student. "
        "You MUST return a JSON object with the following keys:\n"
        "  feedback: short paragraph or bullet points describing key mistakes and strengths.\n"
        "  corrected_answer: one good corrected version of the student's answer.\n"
        "  tip: one practical tip for improvement.\n"
        "  score: integer from 1 to 10.\n"
        "  next_question: one new open-ended question related to the topic and previous answer.\n"
        "Keep the next_question appropriate for a spoken answer of 20–40 seconds."
    )

    user_msg = (
        f"Exam topic: {topic}\n"
        f"Examiner question: {last_question}\n"
        f"Student answer: {transcript}\n\n"
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

        feedback_text = result.get("feedback", "")

        # Save a log row in the database (similar to /feedback)
        with db_session() as db:  # type: Session
            log = AnalysisLog(
                input_text=transcript,
                feedback_text=feedback_text,
                model_name=MODEL_ID
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
                model_name=MODEL_ID
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
