from flask import Blueprint, request, jsonify
from sqlalchemy.orm import Session
from db import get_db
from models import AnalysisLog
from config import settings
from audit import write_event
import openai

bp_ai = Blueprint("ai", __name__, url_prefix="/api")

# --- Configure the OpenAI client (OpenAI or Azure OpenAI) ---
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
    MODEL_ID = "gpt-4o-mini"  # small/fast model is fine for PoC

def db_session():
    return next(get_db())

@bp_ai.post("/feedback")
def get_feedback():
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

    system_msg = "You are a concise, supportive language tutor for oral exams."
    user_msg = (
        f"Question (optional): {prompt}\n"
        f"Student answer: {transcript}\n\n"
        "Return:\n"
        "1) Key mistakes (grammar/word choice/fluency)\n"
        "2) Corrected answer (one good version)\n"
        "3) One tip to improve"
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
        )
        feedback = resp.choices[0].message.content.strip()

        # Save a log row
        with db_session() as db:  # type: Session
            log = AnalysisLog(
                input_text=transcript,
                feedback_text=feedback,
                model_name=MODEL_ID
            )
            db.add(log)
            db.commit()
            write_event("AI_FEEDBACK_CREATED", {
                "id": log.id,
                "model": model_used,
                "input_chars": len(transcript),
            })

        return jsonify({"feedback": feedback, "model": MODEL_ID}), 200

    except Exception as e:
        # Surface error message for debugging during PoC
        return jsonify({"error": str(e)}), 500
