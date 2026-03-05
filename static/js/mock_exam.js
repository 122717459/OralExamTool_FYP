// Wait until the page is finished loading then run all the javascript
document.addEventListener("DOMContentLoaded", function () {
// This is where we grab the html elements
  const startMockBtn = document.getElementById('startMockBtn');
  const statusEl = document.getElementById('status');
  const questionEl = document.getElementById('question');
  const transcriptEl = document.getElementById('transcript');
  const finalFeedbackEl = document.getElementById('finalFeedback');
  const examLangSel = document.getElementById('examLanguage');
  const difficultySel = document.getElementById('difficulty');
  const examLengthSel = document.getElementById('examLength');
  const speakQBtn = document.getElementById('speakQBtn');
  const skipBtn = document.getElementById('skipBtn');
  const retryBtn = document.getElementById('retryBtn');
  const submitBtn = document.getElementById('submitBtn');
  const timerEl = document.getElementById('timer');
  const progressText = document.getElementById('progressText');
  const dictInput = document.getElementById('dictInput');
  const dictBtn = document.getElementById('dictBtn');
  const dictResultEl = document.getElementById('dictResult');

// Stores information about the current exam
  let sessionId = null;
  let questionNumber = null;
  let examStartTime = null;

// This gets from the backend meaning, part of speech, examples and synonyms
async function lookupDictionary() {
  const term = (dictInput.value || '').trim();
  if (!term) {
    setStatus('Please type a word or phrase to explain.');
    dictResultEl.textContent = '(no word entered)';
    return;
  }

  setStatus(`Looking up "${term}"…`);
  dictResultEl.textContent = 'Looking up…';

  const difficulty = difficultySel.value;

  try {
    const resp = await fetch('/api/dictionary_ai', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ term, difficulty })
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || data.details || 'dictionary_ai failed');

    const headword = data.headword || term;
    const pos      = data.part_of_speech || '';
    const meaning  = data.meaning || '(no meaning returned)';
    const examples = Array.isArray(data.examples) ? data.examples : [];
    const synonyms = Array.isArray(data.synonyms) ? data.synonyms : [];

    let html = `<p><strong>${headword}</strong>${pos ? ' (' + pos + ')' : ''}</p>`;
    html += `<p>${meaning}</p>`;

    if (examples.length) {
      html += '<p><strong>Examples:</strong><ul>';
      for (const ex of examples) html += `<li>${ex}</li>`;
      html += '</ul></p>';
    }

    if (synonyms.length) {
      html += `<p><strong>Synonyms:</strong> ${synonyms.join(', ')}</p>`;
    }

    dictResultEl.innerHTML = html;
    setStatus('Dictionary result ready.');
  } catch (e) {
    dictResultEl.textContent = 'Could not get a dictionary result.';
    setStatus('Dictionary lookup failed: ' + e.message);
  }
}

dictBtn.addEventListener('click', lookupDictionary);

dictInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    lookupDictionary();
  }
});

// This updates the status indicator at the bottom of the page
  function setStatus(msg) {
    statusEl.textContent = msg;
  }
  // when the user clicks get the transcript, validate it's not empty and send answer to backend
submitBtn.addEventListener('click', async () => {
  const transcript = (transcriptEl.textContent || '').trim();

  if (!transcript) {
    setStatus('No transcript to submit.');
    return;
  }

  submitBtn.disabled = true;
  retryBtn.disabled = true;

  await submitAnswerAndAdvance(transcript);
});



 startMockBtn.addEventListener('click', async () => {
  sessionId = null;
  questionNumber = null;

  setStatus('Starting mock exam…');
  questionEl.textContent = '';
  transcriptEl.textContent = '';


    const language = examLangSel.value;      // "english" | "french" | "german"
    const difficulty = difficultySel.value;  // "beginner" | "moderate" | "expert"
    const total_questions = parseInt(examLengthSel.value);
    totalQuestions = total_questions;

    try {
      const resp = await fetch('/api/exam/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
  language,
  difficulty,
  total_questions
})
      });

      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || data.details || 'exam/start failed');

      sessionId = data.session_id;
      questionNumber = data.question_number;
      questionEl.textContent = (data.question || '').trim() || '(no question returned)';
      const setupCard = document.getElementById('setupCard');
if (setupCard) {
  setupCard.style.display = 'none';
}

      examStartTime = Date.now();

      setStatus(`Mock exam started. Session ${sessionId}, Q${questionNumber}.`);
      progressText.textContent = `Question ${questionNumber} of ${totalQuestions}`;

      skipBtn.disabled = false; // ✅ enable skip once exam starts

    } catch (e) {
      setStatus('Failed to start mock exam: ' + e.message);
    }
  });

      const startRecBtn = document.getElementById('startRecBtn');
  const stopRecBtn = document.getElementById('stopRecBtn');
  const player = document.getElementById('player');

  let mediaStream = null;
  let recorder = null;
  let chunks = [];

  function pickMime() {
    const candidates = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/mp4',
      'audio/ogg;codecs=opus'
    ];
    for (const c of candidates) {
      if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(c)) return c;
    }
    return '';
  }

  async function startRecording() {
    setStatus('Requesting microphone…');

    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true }); // This asks for permission to access microphone
    } catch (e) {
      setStatus('Microphone permission denied.');
      return;
    }

    const mimeType = pickMime();
    try {
      recorder = new MediaRecorder(mediaStream, mimeType ? { mimeType } : undefined); // This is a browser api used to capture microphone audio, store audio chunks and create an audio file
    } catch (e) {
      setStatus('MediaRecorder not supported for this mime.');
      return;
    }

    chunks = [];
    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunks.push(e.data);
    };

    recorder.start(); // keep it stable
    startTimer();
    startRecBtn.disabled = true;
    stopRecBtn.disabled = false;
    startRecBtn.classList.add('recording-active');
    setStatus('Recording…');
  }

  function stopRecording() {
    return new Promise((resolve) => {
      if (!recorder) return resolve(null);

      recorder.onstop = () => {
        try { mediaStream.getTracks().forEach(t => t.stop()); } catch (_) {}
        const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
        resolve(blob);
      };

      try { recorder.stop(); }
      catch (_) { resolve(null); }
    });
  }

// Sends the audio to stt
  async function transcribeBlob(blob) {
    if (!blob || blob.size < 2000) {
      transcriptEl.textContent = '(no usable audio)';
      setStatus('No usable audio captured.');
          return '';

    }

    const filename = (blob.type || '').includes('mp4') ? 'speech.m4a' : 'speech.webm';
    const form = new FormData();
    form.append('file', blob, filename);

    const sttLang =
      examLangSel.value === 'french' ? 'fr' :
      examLangSel.value === 'german' ? 'de' : 'en';
    form.append('lang', sttLang);

    setStatus('Transcribing…');

    try {
      const sttResp = await fetch('/api/stt', { method: 'POST', body: form });
      const data = await sttResp.json();
      if (!sttResp.ok) throw new Error(data.error || data.details || 'STT failed');

         const transcript = (data.transcript || '').trim();
    transcriptEl.textContent = transcript || '(empty transcript)';
    setStatus('Transcription complete.');
    return transcript;

      } catch (e) {
    setStatus('Transcription failed: ' + e.message);
    return '';
  }

  }


let timerInterval = null;
let timerStartMs = null;

function formatTime(ms) {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  return String(minutes).padStart(2, '0') + ':' +
         String(seconds).padStart(2, '0');
}

// Displays a timer during each answer
function startTimer() {
  stopTimer(); // safety
  timerStartMs = Date.now();
  timerEl.textContent = '00:00';
  timerInterval = setInterval(() => {
    timerEl.textContent = formatTime(Date.now() - timerStartMs);
  }, 200);
}

function stopTimer() {
  if (timerInterval) clearInterval(timerInterval);
  timerInterval = null;
}


//  Allows the student to skip a question
skipBtn.addEventListener('click', async () => {
  if (!sessionId || !questionNumber) {
    setStatus('No active mock session.');
    return;
  }

  setStatus('Skipping… loading a new question in this section.');

  try {
    const resp = await fetch('/api/exam/skip', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, question_number: Number(questionNumber) })
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || data.details || 'exam/skip failed');

    questionEl.textContent = (data.question || '').trim() || '(no question returned)';
    transcriptEl.textContent = '';
    setStatus(`Skipped. New question loaded (Q${questionNumber}).`);
  } catch (e) {
    setStatus('Skip failed: ' + e.message);
  }
});



  startRecBtn.addEventListener('click', startRecording);

  stopRecBtn.addEventListener('click', async () => {
    stopRecBtn.disabled = true;
    const blob = await stopRecording();
    stopTimer();
    startRecBtn.classList.remove('recording-active');




    startRecBtn.disabled = false;
    const transcript = await transcribeBlob(blob);

// Just show transcript.
setStatus('Review your transcript. Click Submit when ready.');
submitBtn.disabled = false;
retryBtn.disabled = false;


    retryBtn.disabled = false;
    stopRecBtn.disabled = false;
  });

// Sends the students answer to exam/answer where in the backend stores the transcript, checks if exam is finished sends next question
    async function submitAnswerAndAdvance(transcript) {
  if (!sessionId || !questionNumber) {
    setStatus('No active mock session. Click Start Mock Exam first.');
    timerEl.textContent = '00:00';
    return;
  }
  if (!transcript) {
    setStatus('Empty transcript — not saved.');
    return;
  }

  setStatus(`Saving answer for session ${sessionId}, Q${questionNumber}…`);


  try {
    const resp = await fetch('/api/exam/answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        question_number: Number(questionNumber),
        transcript
    })

    });

    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || data.details || 'exam/answer failed');

    if (data.done) {
  setStatus('Mock exam complete. Click Finish to see feedback.');
  questionEl.textContent = '(completed)';
  startRecBtn.disabled = true;
  stopRecBtn.disabled = true;
  finishBtn.disabled = false;
  progressText.textContent = `Completed (${totalQuestions} questions)`;
  return;
}


    // Move to next question
    questionNumber = data.question_number;
    questionEl.textContent = (data.question || '').trim() || '(no question returned)';
    setStatus(`Answer saved. Now on Q${questionNumber}.`);
    transcriptEl.textContent = '';
submitBtn.disabled = true;
retryBtn.disabled = true;
    progressText.textContent = `Question ${questionNumber} of ${totalQuestions}`;

  } catch (e) {
    setStatus('Could not save answer: ' + e.message);
  }
}



speakQBtn.addEventListener('click', async () => {
  const text = (questionEl.textContent || '').trim();
  if (!text) {
    setStatus('No question to read yet.');
    return;
  }

  setStatus('Generating question audio…');

  try {
    const resp = await fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text,
        language: examLangSel.value  // "english" | "french" | "german"
      })
    });

    // If your /api/tts returns audio bytes:
    const blob = await resp.blob();
    if (!resp.ok) throw new Error('TTS failed');

    player.src = URL.createObjectURL(blob);
    await player.play().catch(() => {});
    setStatus('Playing question audio.');
  } catch (e) {
    setStatus('TTS error: ' + e.message);
  }
});

retryBtn.addEventListener('click', () => {
  transcriptEl.textContent = '';
  submitBtn.disabled = true;
  setStatus('Retry recording when ready.');
});


// When the exam ends calculates total time call the backend so generates section feedback, scores, strengths, and weaknesses
    finishBtn.addEventListener('click', async () => {
  if (!sessionId) {
    setStatus('No session to finish.');
    return;
  }

  setStatus('Generating final feedback…');

finalFeedbackEl.innerHTML = `
  <div class="loading-feedback">
    <div class="spinner"></div>
    Generating feedback... Please wait.
  </div>
`;
document.getElementById('feedbackCard').style.display = 'block';
  finishBtn.disabled = true;
if (!examStartTime) {
  console.log("examStartTime:", examStartTime);
  setStatus("Exam timing error.");
  finalFeedbackEl.textContent = "Could not calculate exam time.";
  finishBtn.disabled = false;
  return;
}

const totalMs = Date.now() - examStartTime;
const totalSeconds = Math.floor(totalMs / 1000);
const minutes = Math.floor(totalSeconds / 60);
const seconds = totalSeconds % 60;

const totalTimeFormatted =
  String(minutes).padStart(2, '0') +
  " mins " +
  String(seconds).padStart(2, '0') +
  " seconds";
  try {
    const resp = await fetch('/api/exam/finish', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId })
    });

    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || data.details || 'exam/finish failed');

//  Render only section summaries (hide backend JSON)
const sections = Array.isArray(data.section_feedback)
  ? data.section_feedback
  : [];

if (!sections.length) {
  finalFeedbackEl.textContent = "No section feedback returned.";
  setStatus("Final feedback returned, but section feedback was empty.");
  return;
}

const sectionScores = (data.section_scores && typeof data.section_scores === "object")
  ? data.section_scores
  : {};

const overallScore = (typeof data.overall_score === "number")
  ? data.overall_score
  : null;

const overallStrengths = Array.isArray(data.overall_strengths) ? data.overall_strengths : [];
const overallWeaknesses = Array.isArray(data.overall_weaknesses) ? data.overall_weaknesses : [];

finalFeedbackEl.innerHTML = `
  <div style="margin-bottom:10px;">
    <strong>Total Exam Time:</strong> ${totalTimeFormatted}
  </div>

  ${overallScore !== null ? `
    <div style="margin-bottom:14px;">
      <strong>Overall Score:</strong> ${overallScore}/10
    </div>
  ` : ""}

  ${sections.map(s => {
    const score = (s.section in sectionScores)
      ? sectionScores[s.section]
      : null;

    return `
      <div style="margin-bottom:14px;">
        <div style="font-weight:700; margin-bottom:6px;">
          ${s.section.toUpperCase()}${score !== null ? ` — ${score}/10` : ""}
        </div>

        <div style="margin-bottom:8px;">
          ${s.summary_en || ""}
        </div>

        <div><strong>Strengths</strong></div>
        <ul>
          ${(s.strengths || []).map(x => `<li>${x}</li>`).join("")}
        </ul>

        <div><strong>Improvements</strong></div>
        <ul>
          ${(s.improvements || []).map(x => `<li>${x}</li>`).join("")}
        </ul>
      </div>
    `;
  }).join("")}

  <div style="margin-top:18px; padding-top:12px; border-top:1px solid #ddd;">
    <div style="font-weight:700; margin-bottom:6px;">OVERALL STRENGTHS</div>
    ${overallStrengths.length ? `
      <ul>${overallStrengths.map(x => `<li>${x}</li>`).join("")}</ul>
    ` : `<div class="muted">No overall strengths returned.</div>`}

    <div style="font-weight:700; margin:12px 0 6px;">OVERALL WEAKNESSES</div>
    ${overallWeaknesses.length ? `
      <ul>${overallWeaknesses.map(x => `<li>${x}</li>`).join("")}</ul>
    ` : `<div class="muted">No overall weaknesses returned.</div>`}
  </div>
`;

setStatus('Final feedback ready.');
document.getElementById('questionCard').style.display = 'none';
document.getElementById('answerCard').style.display = 'none';
document.getElementById('dictionaryCard').style.display = 'none';
document.getElementById('feedbackCard').style.display = 'block';
finishBtn.disabled = false;

  } catch (e) {
    finishBtn.disabled = false;
    finalFeedbackEl.textContent = 'Failed to generate feedback.';
    setStatus('Finish failed: ' + e.message);
  }
});
// Reloads the page which restarts the entire exam
const restartBtn = document.getElementById('restartBtn');

restartBtn.addEventListener('click', () => {
  location.reload();
});
});
