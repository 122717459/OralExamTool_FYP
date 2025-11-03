# (OpenAI-only; Whisper STT forced language; unique endpoints)
from flask import Blueprint, request, jsonify, Response, send_file
from config import settings
from openai import OpenAI
import io, tempfile, os

bp_speech = Blueprint("speech_bp", __name__, url_prefix="/api")
client = OpenAI(api_key=settings.OPENAI_API_KEY)

# ---------- STT ----------
@bp_speech.post("/stt", endpoint="stt_v1")
def stt():
    """
    Multipart form-data:
      file: audio file (webm/ogg/wav/mp3/m4a)
      lang: BCP-47 like 'en-GB' (we map to 'en' for Whisper)
    """
    f = request.files.get("file")
    lang_in = (request.form.get("lang") or "en-GB").strip()
    if not f:
        return jsonify({"error": "audio file is required (form field 'file')"}), 400

    lang = (lang_in.split('-')[0] or "en").lower()  # 'en-GB' -> 'en'
    data = f.read()
    print("[STT] received bytes:", 0 if data is None else len(data))  # tiny debug log

    if not data or len(data) < 2000:
        return jsonify({"error": "empty or too-small audio upload", "bytes": len(data or b'')}), 400

    buf = io.BytesIO(data)
    buf.name = f.filename or "audio.webm"
    buf.seek(0)

    try:
        tr = client.audio.transcriptions.create(
            model="whisper-1",
            file=buf,
            response_format="text",
            language=lang,
            temperature=0,
        )
        text = tr if isinstance(tr, str) else getattr(tr, "text", "")
        return jsonify({"transcript": (text or "").strip(), "lang_used": lang}), 200
    except Exception as e:
        return jsonify({"error": "STT failed", "details": str(e)}), 500


# ---------- Non-streaming Chat (fallback) ----------
@bp_speech.post("/answer", endpoint="answer_plain_v1")
def answer_plain():
    data = request.get_json(force=True) or {}
    user_q = (data.get("q") or "").strip()
    system_msg = (data.get("system") or
                  "You are an oral-exam interlocutor. Keep answers concise and ask one follow-up question.").strip()
    if not user_q:
        return jsonify({"error": "q is required"}), 400

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_q},
            ],
            temperature=0.4,
        )
        text = resp.choices[0].message.content or ""
        return jsonify({"text": text}), 200
    except Exception as e:
        return jsonify({"error": "LLM error", "details": str(e)}), 500


# ---------- Streamed Chat ----------
@bp_speech.get("/answer_stream", endpoint="answer_stream_v1")
def answer_stream():
    user_q = (request.args.get("q") or "").strip()
    system_msg = (request.args.get("system") or
                  "You are an oral-exam interlocutor. Keep answers concise and ask one follow-up question.").strip()
    if not user_q:
        return jsonify({"error": "q is required"}), 400

    def generate():
        try:
            with client.chat.completions.stream(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_q},
                ],
                temperature=0.4,
            ) as stream:
                for event in stream:
                    if event.type == "token":
                        yield f"data: {event.token}\n\n"
                yield "event: done\ndata: [DONE]\n\n"
        except Exception as e:
            yield f"event: error\ndata: {type(e).__name__}: {e}\n\n"

    # <-- THIS WAS MISSING IN YOUR FILE
    return Response(generate(), mimetype="text/event-stream")


# ---------------- TTS (Text to Speech) ----------------
@bp_speech.post("/tts", endpoint="tts_v1")
def tts():
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    voice = (data.get("voice") or "alloy").strip()

    if not text:
        return jsonify({"error": "text is required"}), 400

    try:
        # NOTE: no "format=" here; the SDK streams audio (defaults to mp3)
        with client.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=text,
        ) as resp:
            # save as MP3
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name
                resp.stream_to_file(tmp_path)

        # send back as audio/mpeg
        with open(tmp_path, "rb") as f:
            audio_bytes = f.read()
        try:
            os.remove(tmp_path)
        except Exception:
            pass

        return send_file(
            io.BytesIO(audio_bytes),
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name="speech.mp3",
        )
    except Exception as e:
        return jsonify({"error": "TTS failed", "details": str(e)}), 500


