# routes_speech.py
from flask import Blueprint, request, jsonify, Response, send_file
from config import settings
from openai import OpenAI
import io, tempfile, os

# Calling API_key from .env file
bp_speech = Blueprint("speech_bp", __name__, url_prefix="/api")
client = OpenAI(api_key=settings.OPENAI_API_KEY)


# This code is from ChatGPT this file deals with how the programme will deal with users speech.
@bp_speech.post("/stt", endpoint="stt_v1")
def stt(): # This function explains the expected datafile and the language.
    """
    Multipart form-data:
      file: audio file (webm/ogg/wav/mp3/m4a)
      lang: BCP-47 like 'en-GB' (we map to 'en' for Whisper)
    """
    f = request.files.get("file") # Fetches the uploaded file form the http request
    lang_in = (request.form.get("lang") or "en-GB").strip() # reads the optional language from the field (default english)
    if not f:
        return jsonify({"error": "audio file is required (form field 'file')"}), 400 # If there is no file return 400

    lang = (lang_in.split('-')[0] or "en").lower()  # 'en-GB' -> 'en'
    data = f.read() # Reads the file into memory as bytes and logs how many bites were recieved.
    print("[STT] received bytes:", 0 if data is None else len(data))  # tiny debug log

    if not data or len(data) < 2000: # rejects empty audio files ( less than 2 kb)
        return jsonify({"error": "empty or too-small audio upload", "bytes": len(data or b'')}), 400

    buf = io.BytesIO(data) # Wraps the raw bytes in a bytesio object
    buf.name = f.filename or "audio.webm"  # Gives it a name so that the API knows what it is.
    buf.seek(0) # resets the read pointer to the start.

    try:
        tr = client.audio.transcriptions.create( # Client is OpenAI SDK client.
            model="whisper-1", # File is sent to Whisper1 model for transcription
            file=buf,
            response_format="text", # Whisper should return a plain text.
            language=lang,
            temperature=0, # Is meant to keep output deterministic (not random)
        )
        text = tr if isinstance(tr, str) else getattr(tr, "text", "") # Handels both possible return types (string, object)
        return jsonify({"transcript": (text or "").strip(), "lang_used": lang}), 200 # Returns a JSON response.
    except Exception as e:
        return jsonify({"error": "STT failed", "details": str(e)}), 500


# This code is from ChatGPT
@bp_speech.post("/answer", endpoint="answer_plain_v1")
def answer_plain():
    data = request.get_json(force=True) or {}
    user_q = (data.get("q") or "").strip()
    system_msg = (data.get("system") or
                  "You are an oral-exam interlocutor. Keep answers concise and ask one follow-up question.").strip()
    if not user_q:
        return jsonify({"error": "q is required"}), 400 # Parses JSON body; expects a question in q, validates q isn't empty

    try:
        resp = client.chat.completions.create( # Calls the chat model with the system and user messages
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_q},
            ],
            temperature=0.4, # Mild randomness for variety without being too much
        )
        text = resp.choices[0].message.content or "" # return the assistant text as text
        return jsonify({"text": text}), 200
    except Exception as e:
        return jsonify({"error": "LLM error", "details": str(e)}), 500 # any failure payload error


# This code is from ChatGPT
@bp_speech.get("/answer_stream", endpoint="answer_stream_v1")
def answer_stream(): # Reads q and optional system from query params
    user_q = (request.args.get("q") or "").strip()
    system_msg = (request.args.get("system") or
                  "You are an oral-exam interlocutor. Keep answers concise and ask one follow-up question.").strip()
    if not user_q:
        return jsonify({"error": "q is required"}), 400 # just normal error message

    def generate():
        try: # Opens a streaming completion,
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
                        yield f"data: {event.token}\n\n" #For each token, yields an SSE line
                yield "event: done\ndata: [DONE]\n\n" # Finishes with a done event and done payload
        except Exception as e:
            yield f"event: error\ndata: {type(e).__name__}: {e}\n\n"

    # <-- THIS WAS MISSING IN YOUR FILE
    return Response(generate(), mimetype="text/event-stream")


#  TTS (Text to Speech) This code is from ChatGPT
@bp_speech.post("/tts", endpoint="tts_v1")
def tts(): # Registers a post endpoint /tts inside the bp_speech blueprint, This will be called whenever a client sends text to convert into speech
    data = request.get_json(force=True) or {} # Parses the incoming JSON body.
    text = (data.get("text") or "").strip() #Extracts text: the text to speak
    language = (data.get("language") or "").strip().lower()

    # Default voices per language
    voice_by_language = {
        "english": "alloy",
        "french": "nova",
        "german": "alloy",
    }

    # If frontend passes voice explicitly, respect it.
    # Otherwise pick by language, fallback to alloy.
    voice = (data.get("voice") or voice_by_language.get(language) or "alloy").strip()

    if not text:
        return jsonify({"error": "text is required"}), 400 # Validation the text field must be provided

    try:
        # NOTE: no "format=" here; the SDK streams audio (defaults to mp3)
        with client.audio.speech.with_streaming_response.create( #Calls OpenAI's tts API using the gpt-40-tts model
            model="gpt-4o-mini-tts",
            voice=voice,
            input=text,
        ) as resp: # the .with_streaming_response.create streams the generated audio back incrementally,
            # save as MP3
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp: # creats a temporary MP3 file on disk
                tmp_path = tmp.name
                resp.stream_to_file(tmp_path) # Streams the audio data into that file as it arrives from the model

        # send back as audio/mpeg
        with open(tmp_path, "rb") as f: #Reads the MP3 into memory.l
            audio_bytes = f.read()
        try:
            os.remove(tmp_path) # Deletes the temporary file afterward (cleanup)
        except Exception:
            pass

        return send_file( # Wraps the audio bytes in an in-memory stream and sends them back to the client.
            io.BytesIO(audio_bytes),
            mimetype="audio/mpeg", # Response MIME type: audio/mpeg, so browsers can play it directly.
            as_attachment=False,
            download_name="speech.mp3",
        )
    except Exception as e:
        return jsonify({"error": "TTS failed", "details": str(e)}), 500 # Any error returns HTTP 500






""" This is the Prompt for def stt
Write a Python Flask backend function called **stt()** for a language speaking mock exam application.
The function should create a **POST API endpoint `/api/stt`** that performs **speech-to-text transcription**.
The endpoint will receive a multipart form request containing:
file – an uploaded audio recording from the user's microphone (webm, ogg, wav, mp3, or m4a)
lang – the language code for the audio (for example: `en`, `fr`, `de`)
The function should:
1. Check that an audio file was uploaded.
2. Read the uploaded audio file into memory.
3. Send the audio file to an AI speech-to-text model (such as OpenAI Whisper).
4. Ask the model to transcribe the audio into text.
5. Return the transcript as JSON so the frontend can display it.
Example response:
```json
{
  "transcript": "I usually play football with my friends after school.",
  "lang_used": "en"
}
```
The function should also:
reject empty or extremely small audio files
return a clear error message if transcription fails
handle exceptions so the API does not crash.
"""



""" THis is the promp for def answer_plain
Write a Python Flask backend function called **answer_plain()** for a language speaking mock exam application.
The function should create a POST API endpoint `/api/answer` that sends a user's question to an AI model and returns a text response.
The endpoint will receive JSON data from the frontend containing:
q – the user's question or message
system (optional) – a system instruction that tells the AI how it should behave
The function should:
1. Read the JSON data from the request.
2. Check that a question (**q**) was provided.
3. Send the system instruction and the user's question to an AI chat model (for example `gpt-4o-mini`).
4. Ask the AI to generate a short response.
5. Return the AI's answer as JSON so the frontend can display it.
Example response:
```json id="9v1g0y"
{
  "text": "That's a great question. Can you tell me more about your hobbies?"
}
```
The function should also include basic error handling if the AI request fails.
"""



""" This is the prompt for def tts
Write a Python Flask backend function called tts() for a language learning application.
The function should create a **POST API endpoint `/api/tts`** that converts text into spoken audio using an AI text-to-speech model.
The endpoint will receive JSON data from the frontend containing:
text – the text that should be spoken
language – the language of the text (english / french / german)
voice (optional) – the voice that should be used for the audio
The function should:
1. Read the JSON request data.
2. Check that the text field is provided.
3. Choose a default voice based on the language if no voice is provided.
4. Send the text to an AI text-to-speech model (for example an OpenAI TTS model).
5. Generate speech audio from the text.
6. Return the audio file so the browser can play it.
The response should return **audio data** (for example an MP3 file) with the correct audio MIME type so it can be played directly in the browser.
The function should also:
temporarily store the generated audio file if needed
return an error message if speech generation fails
include basic error handling so the API does not crash.
"""



