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
from collections import defaultdict
import re
import random

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
        "- NEVER use placeholders like [your city], [your country], [your hobbies].\n"
        "- Do NOT invent personal facts the student did not say.\n"
        "- If info is missing, keep the corrected answer general and faithful to what was said.\n"
        "- The corrected answer MUST NOT add any new factual details.\n"
        "- Only use facts explicitly stated in the student's transcript.\n"
        "- You may add polite generic filler (e.g., 'Nice to meet you.') but no invented specifics.\n"
        "- If the student's answer correctly answers the question but is short, do NOT treat it as a major problem. Mention it as optional improvement only.\n"

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
        "Important: corrected_answer_target must not contain bracket placeholders and must not invent details.\n"

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


# Generated using ChatGPT
EXAM_QUESTION_BANK = {
    "introduction": {
        "english": {
            "beginner": [
                "Can you introduce yourself?",
                "How old are you?",
                "Where do you live?",
                "What do you like doing at the weekend?",
                "What is your favourite food?",
                "Tell me one thing you like about your town or city."
            ],
            "moderate": [
                "Can you introduce yourself?",
                "Where are you from, and what do you like about where you live?",
                "What do you usually do on a typical weekday?",
                "What do you like to do in your free time, and why?",
                "How would your friends describe you?",
                "What is one thing you are proud of about yourself?"
            ],
            "expert": [
                "Can you introduce yourself and give some background about your interests?",
                "How has the place where you live influenced you?",
                "What personal quality helps you most in study or work, and why?",
                "Tell me about a recent experience that taught you something important.",
                "How do you manage your time, and what would you improve?",
                "What goal are you working towards at the moment, and why does it matter?"
            ],
        },
        "french": {
            "beginner": [
                "Peux-tu te présenter ?",
                "Quel âge as-tu ?",
                "Où habites-tu ?",
                "Qu'est-ce que tu aimes faire le week-end ?",
                "Quel est ton plat préféré ?",
                "Dis-moi une chose que tu aimes dans ta ville."
            ],
            "moderate": [
                "Peux-tu te présenter ?",
                "D'où viens-tu et qu'est-ce que tu aimes dans l'endroit où tu habites ?",
                "Que fais-tu pendant une journée normale en semaine ?",
                "Qu'est-ce que tu aimes faire pendant ton temps libre et pourquoi ?",
                "Comment tes amis te décriraient-ils ?",
                "De quoi es-tu fier(e) chez toi ?"
            ],
            "expert": [
                "Peux-tu te présenter et donner un peu de contexte sur tes centres d'intérêt ?",
                "En quoi l'endroit où tu vis t'a-t-il influencé(e) ?",
                "Quelle qualité personnelle t'aide le plus dans tes études ou ton travail, et pourquoi ?",
                "Raconte une expérience récente qui t'a appris quelque chose d'important.",
                "Comment gères-tu ton temps et que voudrais-tu améliorer ?",
                "Quel objectif poursuis-tu en ce moment et pourquoi est-ce important pour toi ?"
            ],
        },
        "german": {
            "beginner": [
                "Kannst du dich vorstellen?",
                "Wie alt bist du?",
                "Wo wohnst du?",
                "Was machst du gern am Wochenende?",
                "Was ist dein Lieblingsessen?",
                "Nenne eine Sache, die dir an deiner Stadt gefällt."
            ],
            "moderate": [
                "Kannst du dich vorstellen?",
                "Woher kommst du und was gefällt dir an deinem Wohnort?",
                "Was machst du normalerweise an einem typischen Wochentag?",
                "Was machst du gern in deiner Freizeit und warum?",
                "Wie würden dich deine Freunde beschreiben?",
                "Worauf bist du besonders stolz?"
            ],
            "expert": [
                "Kannst du dich vorstellen und etwas über deine Interessen erzählen?",
                "Wie hat dich der Ort, an dem du lebst, beeinflusst?",
                "Welche persönliche Eigenschaft hilft dir am meisten beim Lernen oder Arbeiten, und warum?",
                "Erzähl von einer Erfahrung, aus der du etwas Wichtiges gelernt hast.",
                "Wie organisierst du deine Zeit und was würdest du verbessern?",
                "Welches Ziel verfolgst du gerade und warum ist es dir wichtig?"
            ],
        },
    },

    "school": {
        "english": {
            "beginner": [
                "Do you go to school or college?",
                "What subjects do you study?",
                "What is your favourite subject?",
                "What time do you start school?",
                "Do you have homework? Tell me about it.",
                "Do you like your teachers?"
            ],
            "moderate": [
                "What subjects are you studying?",
                "What do you like and dislike about school or college?",
                "Tell me about a recent project or assignment you worked on.",
                "Which subject do you find most interesting, and why?",
                "How do you usually study for exams or tests?",
                "What skills do you think you are improving at school or college?"
            ],
            "expert": [
                "How would you evaluate your current course or programme overall?",
                "Tell me about a project that challenged you and what you learned from it.",
                "Which skill is most important in your field of study, and why?",
                "How do you handle stress during busy academic periods?",
                "What changes would you make to improve your school or college experience?",
                "How do you think education prepares people for real life?"
            ],
        },
        "french": {
            "beginner": [
                "Tu vas à l'école ou à l'université ?",
                "Quelles matières étudies-tu ?",
                "Quelle est ta matière préférée ?",
                "À quelle heure commences-tu les cours ?",
                "As-tu des devoirs ? Parle-m'en.",
                "Aimes-tu tes professeurs ?"
            ],
            "moderate": [
                "Quelles matières étudies-tu ?",
                "Qu'est-ce que tu aimes et que n'aimes-tu pas à l'école ou à l'université ?",
                "Parle-moi d'un projet ou d'un devoir récent que tu as fait.",
                "Quelle matière trouves-tu la plus intéressante et pourquoi ?",
                "Comment révises-tu normalement pour les examens ?",
                "Quelles compétences penses-tu améliorer grâce à tes études ?"
            ],
            "expert": [
                "Comment évaluerais-tu ton programme d'études dans l'ensemble ?",
                "Parle-moi d'un projet difficile et de ce que tu en as appris.",
                "Quelle compétence est la plus importante dans ton domaine et pourquoi ?",
                "Comment gères-tu le stress pendant les périodes chargées ?",
                "Qu'est-ce que tu changerais pour améliorer ton expérience scolaire ?",
                "Selon toi, à quoi sert l'éducation dans la vie réelle ?"
            ],
        },
        "german": {
            "beginner": [
                "Gehst du zur Schule oder zur Uni?",
                "Welche Fächer lernst du?",
                "Was ist dein Lieblingsfach?",
                "Wann beginnt die Schule/Uni?",
                "Hast du Hausaufgaben? Erzähl davon.",
                "Magst du deine Lehrer?"
            ],
            "moderate": [
                "Welche Fächer lernst du?",
                "Was magst du und was magst du nicht an der Schule oder Universität?",
                "Erzähl mir von einem Projekt oder einer Aufgabe, die du kürzlich gemacht hast.",
                "Welches Fach findest du am interessantesten und warum?",
                "Wie lernst du normalerweise für Prüfungen?",
                "Welche Fähigkeiten verbesserst du deiner Meinung nach in der Schule/Uni?"
            ],
            "expert": [
                "Wie würdest du dein aktuelles Studium insgesamt bewerten?",
                "Erzähl von einem Projekt, das dich gefordert hat, und was du daraus gelernt hast.",
                "Welche Fähigkeit ist in deinem Studienbereich am wichtigsten und warum?",
                "Wie gehst du mit Stress in intensiven Phasen um?",
                "Was würdest du ändern, um deine Schul-/Uni-Erfahrung zu verbessern?",
                "Wie bereitet Bildung deiner Meinung nach auf das echte Leben vor?"
            ],
        },
    },

    "hobbies": {
        "english": {
            "beginner": [
                "What do you do in your free time?",
                "Do you like sports?",
                "Do you like music?",
                "Do you like watching films or TV?",
                "Do you like reading?",
                "Tell me about your favourite hobby."
            ],
            "moderate": [
                "What do you like to do in your free time?",
                "Tell me about a hobby you enjoy and why you like it.",
                "How often do you do it, and who do you usually do it with?",
                "Do you prefer indoor or outdoor activities? Why?",
                "Tell me about a film or TV series you enjoyed recently.",
                "What hobby would you like to try in the future, and why?"
            ],
            "expert": [
                "How do your hobbies affect your mood or stress levels?",
                "Tell me about a hobby that helped you develop a useful skill.",
                "Do you think hobbies should be productive, or just enjoyable? Why?",
                "How has your free time changed over the last few years?",
                "Describe a memorable experience connected to one of your hobbies.",
                "If you had more free time, what would you do differently and why?"
            ],
        },
        "french": {
            "beginner": [
                "Qu'est-ce que tu fais pendant ton temps libre ?",
                "Aimes-tu le sport ?",
                "Aimes-tu la musique ?",
                "Aimes-tu regarder des films ou des séries ?",
                "Aimes-tu lire ?",
                "Parle-moi de ton loisir préféré."
            ],
            "moderate": [
                "Qu'est-ce que tu aimes faire pendant ton temps libre ?",
                "Parle-moi d'un loisir que tu aimes et explique pourquoi.",
                "À quelle fréquence fais-tu cette activité et avec qui ?",
                "Tu préfères les activités à l'intérieur ou à l'extérieur ? Pourquoi ?",
                "Parle-moi d'un film ou d'une série que tu as apprécié(e) récemment.",
                "Quel loisir aimerais-tu essayer dans le futur et pourquoi ?"
            ],
            "expert": [
                "Comment tes loisirs influencent-ils ton humeur ou ton stress ?",
                "Parle-moi d'un loisir qui t'a aidé à développer une compétence utile.",
                "Selon toi, un loisir doit-il être productif ou simplement agréable ? Pourquoi ?",
                "Comment ton temps libre a-t-il changé ces dernières années ?",
                "Décris une expérience mémorable liée à un de tes loisirs.",
                "Si tu avais plus de temps libre, que ferais-tu différemment et pourquoi ?"
            ],
        },
        "german": {
            "beginner": [
                "Was machst du in deiner Freizeit?",
                "Magst du Sport?",
                "Magst du Musik?",
                "Schaust du gern Filme oder Serien?",
                "Liest du gern?",
                "Erzähl mir von deinem Lieblingshobby."
            ],
            "moderate": [
                "Was machst du gern in deiner Freizeit?",
                "Erzähl mir von einem Hobby, das dir gefällt, und warum.",
                "Wie oft machst du das und mit wem?",
                "Magst du lieber Aktivitäten drinnen oder draußen? Warum?",
                "Erzähl mir von einem Film oder einer Serie, die dir kürzlich gefallen hat.",
                "Welches Hobby würdest du gern in Zukunft ausprobieren und warum?"
            ],
            "expert": [
                "Wie beeinflussen deine Hobbys deine Stimmung oder deinen Stress?",
                "Erzähl von einem Hobby, durch das du eine nützliche Fähigkeit gelernt hast.",
                "Sollten Hobbys deiner Meinung nach produktiv sein oder einfach Spaß machen? Warum?",
                "Wie hat sich deine Freizeit in den letzten Jahren verändert?",
                "Beschreibe ein besonderes Erlebnis, das mit einem Hobby verbunden ist.",
                "Wenn du mehr Freizeit hättest, was würdest du anders machen und warum?"
            ],
        },
    },

    "family_friends": {
        "english": {
            "beginner": [
                "Do you have a big family or a small family?",
                "Do you have brothers or sisters?",
                "Who do you live with?",
                "Tell me about your best friend.",
                "What do you do with your friends?",
                "Do you like spending time with your family?"
            ],
            "moderate": [
                "Can you tell me about your family?",
                "Who are you closest to, and why?",
                "What do you and your family or friends like to do together?",
                "Tell me about a friend who is important to you.",
                "What do you value most in a friend?",
                "How do you keep in touch with friends or family members?"
            ],
            "expert": [
                "How have your family or friends influenced your decisions?",
                "What makes a friendship strong in your opinion?",
                "Describe a time when someone supported you and how it helped.",
                "Do you think social media improves or harms friendships? Why?",
                "How do you deal with disagreements with friends or family?",
                "What do you think is the most important value in relationships?"
            ],
        },
        "french": {
            "beginner": [
                "Tu as une grande famille ou une petite famille ?",
                "As-tu des frères ou des sœurs ?",
                "Avec qui habites-tu ?",
                "Parle-moi de ton/ta meilleur(e) ami(e).",
                "Qu'est-ce que tu fais avec tes amis ?",
                "Aimes-tu passer du temps avec ta famille ?"
            ],
            "moderate": [
                "Peux-tu me parler de ta famille ?",
                "Avec qui es-tu le plus proche et pourquoi ?",
                "Qu'est-ce que toi et ta famille ou tes amis aimez faire ensemble ?",
                "Parle-moi d'un ami important pour toi.",
                "Qu'est-ce que tu apprécies le plus chez un ami ?",
                "Comment gardes-tu le contact avec tes amis ou les membres de ta famille ?"
            ],
            "expert": [
                "Comment ta famille ou tes amis ont-ils influencé tes choix ?",
                "Selon toi, qu'est-ce qui rend une amitié solide ?",
                "Décris un moment où quelqu'un t'a soutenu et comment cela t'a aidé(e).",
                "Penses-tu que les réseaux sociaux améliorent ou abîment les amitiés ? Pourquoi ?",
                "Comment gères-tu les désaccords avec tes proches ?",
                "Quelle est, selon toi, la valeur la plus importante dans une relation ?"
            ],
        },
        "german": {
            "beginner": [
                "Hast du eine große oder eine kleine Familie?",
                "Hast du Brüder oder Schwestern?",
                "Mit wem wohnst du?",
                "Erzähl mir von deinem besten Freund/deiner besten Freundin.",
                "Was machst du mit deinen Freunden?",
                "Verbringst du gern Zeit mit deiner Familie?"
            ],
            "moderate": [
                "Kannst du mir von deiner Familie erzählen?",
                "Mit wem bist du am engsten verbunden und warum?",
                "Was machst du gern mit deiner Familie oder deinen Freunden zusammen?",
                "Erzähl mir von einem Freund, der dir wichtig ist.",
                "Was ist dir bei einem Freund am wichtigsten?",
                "Wie hältst du Kontakt zu Freunden oder Familienmitgliedern?"
            ],
            "expert": [
                "Wie haben Familie oder Freunde deine Entscheidungen beeinflusst?",
                "Was macht eine Freundschaft deiner Meinung nach stark?",
                "Beschreibe eine Situation, in der dich jemand unterstützt hat, und warum das wichtig war.",
                "Verbessern oder verschlechtern soziale Medien Freundschaften? Warum?",
                "Wie gehst du mit Konflikten in der Familie oder im Freundeskreis um?",
                "Welche Werte sind dir in Beziehungen am wichtigsten?"
            ],
        },
    },

    "future_plans": {
        "english": {
            "beginner": [
                "What do you want to do in the future?",
                "What job would you like to have?",
                "Do you want to travel in the future?",
                "Do you want to study more?",
                "Where would you like to live in the future?",
                "Tell me one goal you have."
            ],
            "moderate": [
                "What would you like to do in the future?",
                "What career interests you, and why?",
                "What is one goal you want to achieve in the next few years?",
                "Would you like to study more in the future? What and why?",
                "Do you want to work in your country or abroad? Why?",
                "What skills do you want to develop for your future?"
            ],
            "expert": [
                "What does success mean to you personally?",
                "How do you plan to reach your long-term goals?",
                "What challenges might you face in your future career, and how will you handle them?",
                "Would you rather have a stable job or take risks? Why?",
                "How do you think technology will change your future work or life?",
                "If you could change one thing about your future, what would it be and why?"
            ],
        },
        "french": {
            "beginner": [
                "Qu'est-ce que tu veux faire dans le futur ?",
                "Quel métier aimerais-tu faire ?",
                "Veux-tu voyager dans le futur ?",
                "Veux-tu continuer tes études ?",
                "Où aimerais-tu vivre plus tard ?",
                "Dis-moi un objectif que tu as."
            ],
            "moderate": [
                "Qu'aimerais-tu faire dans le futur ?",
                "Quel métier t'intéresse et pourquoi ?",
                "Quel est un objectif que tu veux atteindre dans les prochaines années ?",
                "Aimerais-tu continuer tes études ? Quoi et pourquoi ?",
                "Veux-tu travailler dans ton pays ou à l'étranger ? Pourquoi ?",
                "Quelles compétences veux-tu développer pour ton avenir ?"
            ],
            "expert": [
                "Que signifie la réussite pour toi, personnellement ?",
                "Comment comptes-tu atteindre tes objectifs à long terme ?",
                "Quels défis pourrais-tu rencontrer dans ta future carrière et comment vas-tu les gérer ?",
                "Préfères-tu un travail stable ou prendre des risques ? Pourquoi ?",
                "Selon toi, comment la technologie va-t-elle changer ton futur travail ou ta vie ?",
                "Si tu pouvais changer une chose dans ton avenir, laquelle serait-ce et pourquoi ?"
            ],
        },
        "german": {
            "beginner": [
                "Was möchtest du in der Zukunft machen?",
                "Welchen Beruf möchtest du haben?",
                "Möchtest du in Zukunft reisen?",
                "Möchtest du weiter studieren?",
                "Wo möchtest du später wohnen?",
                "Nenne ein Ziel, das du hast."
            ],
            "moderate": [
                "Was möchtest du in der Zukunft machen?",
                "Welcher Beruf interessiert dich und warum?",
                "Welches Ziel möchtest du in den nächsten Jahren erreichen?",
                "Möchtest du in Zukunft weiter studieren? Was und warum?",
                "Möchtest du in deinem Land oder im Ausland arbeiten? Warum?",
                "Welche Fähigkeiten möchtest du für deine Zukunft entwickeln?"
            ],
            "expert": [
                "Was bedeutet Erfolg für dich persönlich?",
                "Wie planst du, deine langfristigen Ziele zu erreichen?",
                "Welche Herausforderungen erwartest du in deiner Karriere, und wie gehst du damit um?",
                "Würdest du lieber einen sicheren Job haben oder Risiken eingehen? Warum?",
                "Wie wird Technologie deiner Meinung nach deine Arbeit oder dein Leben verändern?",
                "Wenn du eine Sache an deiner Zukunft ändern könntest, was wäre das und warum?"
            ],
        },
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

def generate_followup_question(language: str, difficulty: str, section: str, last_question: str, transcript: str) -> str:
    # Map language code to display name
    target_lang_name = "English"
    if language == "french":
        target_lang_name = "French"
    elif language == "german":
        target_lang_name = "German"

    system_msg = (
        "You are an oral exam examiner.\n"
        f"The exam language is {target_lang_name}. You MUST output only ONE question in {target_lang_name}.\n"
        "Rules:\n"
        "- Ask ONE clear follow-up question based on what the student just said.\n"
        "- Do not give feedback.\n"
        "- Do not include multiple questions.\n"
        "- Keep it answerable in 20–40 seconds.\n"
    )

    user_msg = (
        f"Section: {section}\n"
        f"Difficulty: {difficulty}\n"
        f"Previous question: {last_question}\n"
        f"Student answer (transcript): {transcript}\n\n"
        "Write the next follow-up question."
    )

    resp = openai_client.chat.completions.create(
        model=MODEL_ID,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.4,
        max_tokens=80,
        timeout=30,
    )

    q = (resp.choices[0].message.content or "").strip()
    return q.strip('"').strip()


# This code is from ChatGPT
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
            ("introduction", 0), ("introduction", 1), ("introduction", 2),
            ("school", 0), ("school", 1), ("school", 2),
            ("hobbies", 0), ("hobbies", 1), ("hobbies", 2),
            ("family_friends", 0), ("family_friends", 1), ("family_friends", 2),
            ("future_plans", 0), ("future_plans", 1), ("future_plans", 2),
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

        # Bank questions for first 2 in the section (q_idx 0 and 1)
        if q_idx in (0, 1):
            next_question_text = EXAM_QUESTION_BANK[next_section][language][session.difficulty][q_idx]

        # AI-generated ONLY for the final question in the section (q_idx 2)
        else:  # q_idx == 2
            try:
                next_question_text = generate_followup_question(
                    language=language,
                    difficulty=session.difficulty,
                    section=next_section,
                    last_question=turn.question_text,  # question they just answered
                    transcript=transcript  # what they just said
                )
            except Exception as e:
                print("FOLLOWUP GEN ERROR:", e)
                # fallback to bank q_idx 2 if AI fails
                next_question_text = EXAM_QUESTION_BANK[next_section][language][session.difficulty][2]

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


# This code is from ChatGPT
@bp_ai.post("/exam/skip")
@login_required
def exam_skip():
    """
    Replaces the current question with a different one from the same section.
    JSON:
    { "session_id": 123, "question_number": 4 }
    """
    data = request.get_json(force=True) or {}
    session_id = data.get("session_id")
    question_number = data.get("question_number")

    if not session_id or not question_number:
        return jsonify({"error": "session_id and question_number are required"}), 400

    db = db_session()
    try:
        session = db.get(ExamSession, int(session_id))
        if not session or session.user_id != current_user.id:
            return jsonify({"error": "session not found"}), 404
        if session.status != "in_progress" and session.status != "completed":
            # allow during in_progress; if you only use in_progress, keep just that
            pass

        turn = db.query(ExamTurn).filter(
            ExamTurn.session_id == session.id,
            ExamTurn.question_number == int(question_number)
        ).first()
        if not turn:
            return jsonify({"error": "turn not found"}), 404

        section = turn.section
        language = session.language

        # Get the question bank for this section/language
        section_bank = (EXAM_QUESTION_BANK.get(section, {})
                        .get(language, {})
                        .get(session.difficulty, []))

        if not section_bank:
            return jsonify({"error": f"no question bank for section={section}, language={language}"}), 400

        # Avoid repeating already-used questions in the section if possible
        used = set(
            q[0] for q in db.query(ExamTurn.question_text).filter(
                ExamTurn.session_id == session.id,
                ExamTurn.section == section
            ).all()
        )
        candidates = [q for q in section_bank if q not in used]
        if not candidates:
            # fallback: allow any other question except the current one
            candidates = [q for q in section_bank if q != turn.question_text] or section_bank

        new_q = random.choice(candidates)
        turn.question_text = new_q
        db.add(turn)
        db.commit()

        return jsonify({
            "session_id": session.id,
            "question_number": turn.question_number,
            "section": section,
            "question": new_q
        }), 200

    finally:
        db.close()

#This code is from ChatGPT
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
    bank = EXAM_QUESTION_BANK[section][language][difficulty]
    question_text = bank[0]

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



def summarize_sections_with_ai(language: str, difficulty: str, turns):
    by_section = defaultdict(list)
    for t in turns:
        if (t.transcript or "").strip():
            by_section[t.section].append(t)

    payload = []
    for section, items in by_section.items():
        payload.append({
            "section": section,
            "answers": [
                {
                    "question": it.question_text,
                    "transcript": it.transcript,
                    "overall_band": it.overall_band
                } for it in items
            ]
        })

    system_msg = (
        "You are an oral exam examiner. "
        "Return JSON with key 'sections'. "
        "Each section must include: section, summary_en, strengths (list), improvements (list). "
        "Be specific and professional."
    )

    payload_json = json.dumps(payload, ensure_ascii=False)

    user_msg = (
        f"Language: {language}\n"
        f"Difficulty: {difficulty}\n"
        "Answers grouped by section (JSON):\n"
        f"{payload_json}"
    )

    resp = openai_client.chat.completions.create(
        model=MODEL_ID,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.3,
        max_tokens=500,
        response_format={"type": "json_object"},
    )

    raw = (resp.choices[0].message.content or "").strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        print("SECTION SUMMARY RAW (bad JSON):", raw)
        return []

    return parsed.get("sections", [])


def generate_exam_report(language: str, difficulty: str, turns) -> dict:
    payload = []
    for t in turns:
        tx = (t.transcript or "").strip()
        if not tx:
            continue
        payload.append({
            "section": t.section,
            "question": t.question_text,
            "transcript": tx
        })

    system_msg = (
        "You are an oral exam examiner. Return JSON only.\n"
        "Grade by section and overall.\n"
        "Be fair: short but correct answers should not be heavily penalized.\n"
        "Do NOT invent facts.\n"
        "\n"
        "Return JSON with keys:\n"
        "- section_scores: object mapping section -> integer 0..10\n"
        "- section_feedback: list of objects with keys: section, summary_en, strengths (list), improvements (list)\n"
        "- overall_strengths: list (max 3)\n"
        "- overall_weaknesses: list (max 3)\n"
        "- overall_score: integer 0..10\n"
    )

    user_msg = (
        f"Exam language: {language}\n"
        f"Difficulty: {difficulty}\n"
        "Student answers as JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n"
    )

    resp = openai_client.chat.completions.create(
        model=MODEL_ID,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
        max_tokens=800,
        response_format={"type": "json_object"},
        timeout=30,
    )

    raw = (resp.choices[0].message.content or "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print("EXAM REPORT RAW (bad JSON):", raw)
        return {
            "section_scores": {},
            "section_feedback": [],
            "overall_strengths": [],
            "overall_weaknesses": ["Could not generate final report."],
            "overall_score": 0
        }


#This code is from ChatGPT
@bp_ai.post("/exam/finish")
@login_required
def exam_finish():
    """
    Marks an exam as completed and returns an end-of-exam report (ONE AI call).
    JSON:
    { "session_id": 123 }
    """
    print("FINISH: endpoint hit")

    data = request.get_json(force=True) or {}
    session_id = data.get("session_id")
    print("FINISH: session_id =", session_id)

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

        print("FINISH: turns loaded =", len(turns))

        # ✅ ONE-CALL EXAM REPORT
        report = generate_exam_report(session.language, session.difficulty, turns)

        print("FINISH: about to return response")

        # Return only what the student needs (no backend dump)
        return jsonify({
            "status": session.status,
            "language": session.language,
            "difficulty": session.difficulty,

            "overall_score": report.get("overall_score"),
            "overall_strengths": report.get("overall_strengths", []),
            "overall_weaknesses": report.get("overall_weaknesses", []),

            "section_scores": report.get("section_scores", {}),
            "section_feedback": report.get("section_feedback", []),
        }), 200

    finally:
        db.close()


