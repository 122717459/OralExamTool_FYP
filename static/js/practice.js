// Waits until the page loads before running the script
document.addEventListener("DOMContentLoaded", function () {
//Stores references to HTML elements
  const startExamBtn = document.getElementById('startExamBtn');
  const startMockExamBtn = document.getElementById('startMockExamBtn');
  const readCorrectedBtn = document.getElementById('readCorrectedBtn');

  const startBtn = document.getElementById('startBtn');
  const stopBtn = document.getElementById('stopBtn');
  const retryBtn = document.getElementById('retryBtn');
  const nextQuestionBtn = document.getElementById('nextQuestionBtn');
  const practiceSpeakBtn = document.getElementById('practiceSpeakBtn');

  const statusEl = document.getElementById('status');
  const questionEl = document.getElementById('question');
  const transcriptEl = document.getElementById('transcript');
  const feedbackEl = document.getElementById('feedback');
  const player = document.getElementById('player');

  const difficultySel = document.getElementById('difficulty');
  const topicSel = document.getElementById('topic');
  const examLangSel = document.getElementById('examLanguage');

  const dictInput = document.getElementById('dictInput');
  const dictBtn = document.getElementById('dictBtn');
  const dictResultEl = document.getElementById('dictResult');

// These are audio recording variables used for capturing speech
  let mediaStream = null;
  let recorder = null;
  let chunks = [];

// This allows the system to progress through practice questions
  let currentQuestion = "";
  let pendingNextQuestion = "";
  let lastCorrectedAnswerTarget = "";

// THis is from Chatgpt
// Chooses a compatible audio format supported by the browser, different browsers support different audio formats
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

// Displays system messages like starting practice, and getting Feedback
  function setStatus(msg) {
    statusEl.textContent = msg;
  }

// This code is from chatgpt
// Stops the audio player if it's currently playing. To prevent overlapping audio when hearing questions and corrected answers.
  function stopAudio() {
    try {
      player.pause();
      player.currentTime = 0;
    } catch (_) {}
  }

//THIS is frim chatgpt
// Reads text aloud using AI speech synthesis. Voices changes based on language
  async function speakText(text) {
    if (!text) return;
    setStatus('Speaking…');
    stopAudio();

    const voice =
      examLangSel?.value === 'french' ? 'shimmer' :
      examLangSel?.value === 'german' ? 'nova' :
      'alloy';

    try {
      const ttsResp = await fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voice })
      });

      if (!ttsResp.ok) {
        const j = await ttsResp.json().catch(()=>({}));
        throw new Error(j.details || j.error || 'TTS failed');
      }

      const audioBlob = await ttsResp.blob();
      player.src = URL.createObjectURL(audioBlob);
      await player.play().catch(()=>{});
    } catch (e) {
      setStatus('TTS failed: ' + e.message);
    }
  }

// This is from Chatgpt
// Starts recording the microphone, requests permission, starts media recorder collects audio chunks updates ui showing recording is active.
  async function startRecording() {
    setStatus('Requesting microphone…');
    stopAudio();

    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      setStatus('Microphone permission denied.');
      return;
    }

    const mimeType = pickMime();
    try {
      recorder = new MediaRecorder(mediaStream, mimeType ? { mimeType } : undefined);
    } catch (e) {
      setStatus('MediaRecorder not supported for this mime.');
      return;
    }

    chunks = [];
    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunks.push(e.data);
    };

    recorder.start(250);
    startBtn.disabled = true;
    stopBtn.disabled = false;
    startBtn.classList.add('recording-active');
    setStatus('Recording…');
  }

// This is from Chatgpt
// Stops the microphone recording and creates an audio file (blob)
  function stopRecording() {
    return new Promise((resolve) => {
      if (!recorder) { resolve(null); return; }

      recorder.onstop = () => {
        try { mediaStream.getTracks().forEach(t => t.stop()); } catch (_) {}
        const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
        resolve(blob);
      };

      try {
        if (recorder.state === "recording" && recorder.requestData) recorder.requestData();
        recorder.stop();
      } catch (_) {
        resolve(null);
      }
    });
  }

// This is from Chatgpt
// Triggers when the user clicks start practice.
// Restarts previous session reads settings (difficulty, topic, language)
// In the backend the AI generates the first question.
  async function startPractice() {
    lastCorrectedAnswerTarget = "";
    readCorrectedBtn.disabled = true;

    setStatus('Starting practice…');
    questionEl.textContent = '';
    transcriptEl.textContent = '';
    feedbackEl.textContent = '';
    pendingNextQuestion = '';
    retryBtn.disabled = true;
    nextQuestionBtn.disabled = true;

    const difficulty = difficultySel.value;
    const topic = topicSel.value;
    const language = examLangSel.value;

    try {
      const resp = await fetch('/api/start_exam', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
  topic,
  difficulty,
  language,
  last_question: currentQuestion
})
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || data.details || 'start_exam failed');

      currentQuestion = (data.question || '').trim();
      questionEl.textContent = currentQuestion || '(no question returned)';
      if (skipBtn) {
  skipBtn.disabled = false;
}

      setStatus('Practice started. Listen, then record.');
    } catch (e) {
      setStatus('Could not start practice: ' + e.message);
    }
  }

// This is from chatgpt
// Converts recorded speech to text. Displayed in the transcript box.
// In the backend the AI evaluates the answer and returns feedback, corrected answer, tip, score, etc.
  async function processAudioBlob(blob) {
    if (!blob || blob.size < 2000) {
      setStatus('No usable audio captured.');
      transcriptEl.textContent = '(no speech detected)';
      return;
    }

    if (!currentQuestion) {
      setStatus('No current question. Click Start Practice first.');
      return;
    }

    const filename = (blob.type || '').includes('mp4') ? 'speech.m4a' : 'speech.webm';
    const form = new FormData();
    form.append('file', blob, filename);

    const sttLang =
      examLangSel.value === 'french' ? 'fr' :
      examLangSel.value === 'german' ? 'de' : 'en';
    form.append('lang', sttLang);

    setStatus('Transcribing…');
    let transcript = '';

    try {
      const sttResp = await fetch('/api/stt', { method: 'POST', body: form });
      const data = await sttResp.json();
      if (!sttResp.ok) throw new Error(data.error || data.details || 'STT failed');
      transcript = (data.transcript || '').trim();
    } catch (e) {
      setStatus('Transcription failed: ' + e.message);
      return;
    }

    transcriptEl.textContent = transcript || '(empty transcript)';
    if (!transcript) {
      setStatus('Empty transcript.');
      return;
    }

    setStatus('Getting feedback…');
    feedbackEl.textContent = '';

    const topic = topicSel.value;
    const difficulty = difficultySel.value;
    const language = examLangSel.value;

    try {
      const resp = await fetch('/api/exam_turn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transcript,
          last_question: currentQuestion,
          topic,
          difficulty,
          language
        })
      });

      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || data.details || 'exam_turn failed');

      const feedback = (data.feedback || '').trim();
      const corrected = (data.corrected_answer || '').trim();
      const tip = (data.tip || '').trim();
      const score = data.score;

      lastCorrectedAnswerTarget =
        (corrected && corrected !== 'NO_CHANGES_NEEDED') ? corrected : '';
      readCorrectedBtn.disabled = !lastCorrectedAnswerTarget;

      let out = '';
      if (feedback) out += feedback;
      if (lastCorrectedAnswerTarget) out += `\n\nCorrected answer:\n${lastCorrectedAnswerTarget}`;
      if (tip) out += `\n\nTip:\n${tip}`;
      if (score !== null && score !== undefined) out += `\n\nScore: ${score}/10`;

      feedbackEl.textContent = out || '(no feedback returned)';

      pendingNextQuestion = (data.next_question || '').trim();
      retryBtn.disabled = false;
      nextQuestionBtn.disabled = !pendingNextQuestion;

      setStatus('Feedback ready.');
    } catch (e) {
      setStatus('Feedback failed: ' + e.message);
      retryBtn.disabled = false;
    }
  }

// This is from Chatgpt
// Allows the user to type a word they don't understand then the AI returns definition, part of speech, example sentences, and synonyms.
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
      const pos = data.part_of_speech || '';
      const meaning = data.meaning || '(no meaning returned)';
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

// This is from Chatgpt
//  EVENTS

// Practice start
if (startExamBtn) {
  startExamBtn.addEventListener('click', startPractice);
}

// Mock page redirect
if (startMockExamBtn) {
  startMockExamBtn.addEventListener('click', () => {
    window.location.href = '/mock';   // <-- fixed route
  });
}

// Read corrected answer
if (readCorrectedBtn) {
  readCorrectedBtn.addEventListener('click', async () => {
    if (!lastCorrectedAnswerTarget) return;
    await speakText(lastCorrectedAnswerTarget);
  });
}

// Start recording
if (startBtn) {
  startBtn.addEventListener('click', startRecording);
}

// Stop recording
if (stopBtn) {
  stopBtn.addEventListener('click', async () => {
    stopBtn.disabled = true;
    const blob = await stopRecording();

    if (startBtn) {
      startBtn.classList.remove('recording-active');
      startBtn.disabled = false;
    }

    await processAudioBlob(blob);
    stopBtn.disabled = false;
  });
}

// Speak question (practice page)
if (practiceSpeakBtn) {
  practiceSpeakBtn.addEventListener('click', async () => {
    if (!currentQuestion) return;
    await speakText(currentQuestion);
  });
}

// Retry
if (retryBtn) {
  retryBtn.addEventListener('click', () => {
    if (transcriptEl) transcriptEl.textContent = '';
    if (feedbackEl) feedbackEl.textContent = '';

    setStatus('Retry ready. Click 🔊 to hear the question.');
  });
}

// Next question moves to the next question after the block
if (nextQuestionBtn) {
  nextQuestionBtn.addEventListener('click', async () => {
    if (!pendingNextQuestion) return;

    currentQuestion = pendingNextQuestion;
    pendingNextQuestion = '';

    lastCorrectedAnswerTarget = '';
    if (readCorrectedBtn) readCorrectedBtn.disabled = true;

    if (questionEl) questionEl.textContent = currentQuestion;
    if (transcriptEl) transcriptEl.textContent = '';
    if (feedbackEl) feedbackEl.textContent = '';

    if (retryBtn) retryBtn.disabled = true;
    nextQuestionBtn.disabled = true;

    setStatus('Next question ready.');
    await speakText(currentQuestion);
  });
}

//Skip Loads a new question without answering
if (skipBtn) {
  skipBtn.addEventListener('click', async () => {

    if (!currentQuestion) return;

    setStatus('Loading new question…');

    transcriptEl.textContent = '';
    feedbackEl.textContent = '';
    pendingNextQuestion = '';

    const topic = topicSel.value;
    const difficulty = difficultySel.value;
    const language = examLangSel.value;

    try {
      const resp = await fetch('/api/start_exam', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic, difficulty, language })
      });

      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || data.details || 'start_exam failed');

      currentQuestion = (data.question || '').trim();
      questionEl.textContent = currentQuestion || '(no question returned)';

      retryBtn.disabled = true;
      nextQuestionBtn.disabled = true;

      setStatus('New question loaded. Click 🔊 to hear it.');

    } catch (e) {
      setStatus('Skip failed: ' + e.message);
    }

  });
}

// Dictionary
if (dictBtn) {
  dictBtn.addEventListener('click', lookupDictionary);
}

if (dictInput) {
  dictInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      lookupDictionary();
    }
  });
}
});

// This is the prompt for the pickmime function.
//Write a small JavaScript function called pickMime() that checks which audio MIME
//types the browser supports for MediaRecorder and returns the first supported type.
//Test common formats like audio/webm;codecs=opus, audio/webm, audio/mp4, and
//audio/ogg;codecs=opus. If none are supported, return an empty string.



// This is the prompt for the stopAudio function
//Write a small JavaScript function called stopAudio() that safely stops an HTML audio player if it is currently playing.
//The function should pause the audio and reset the playback position to the beginning using,
//currentTime = 0. Use a try/catch block so the function does not crash if the player is not available.



// This is the prompt for the speakText function.
//Write an async JavaScript function called speakText(text) that sends text to a backend /api/tts endpoint using fetch.
//The function should POST JSON containing the text and selected voice, receive an audio blob in response,
//and play it in an HTML <audio> element. It should also handle errors and update a status message if the request fails.



//This is the prompt for the startRecording function
//Write an async JavaScript function called startRecording() that requests microphone access,
//using navigator.mediaDevices.getUserMedia({ audio: true }), creates a MediaRecorder, and begins recording audio.
//The function should collect audio chunks in an array,
//update the UI to show recording has started, and handle cases where microphone permission is denied.



// This is the prompt for the stopRecording function
// Write a JavaScript function called stopRecording() that stops a running MediaRecorder,
//collects the recorded audio chunks, and returns a Promise that resolves to an audio Blob.
//The function should safely stop the microphone stream tracks and handle cases where the recorder is not active.



// This is the prompt for the startPractice function
//Write an async JavaScript function called startPractice() that begins a language practice session.
//The function should reset the UI, read the selected topic, difficulty, and language from dropdowns,
//and send them in a POST request to /api/start_exam.
//When the response returns, it should display the generated question on the page and update the status message.
//Handle errors if the request fails.




// This is the prompt for the processAudioBlob function
//Write an async JavaScript function called processAudioBlob(blob) that takes a recorded audio blob,
//checks that it contains usable audio, and sends it to a backend /api/stt endpoint using FormData.
//The function should receive the transcript from the server, display it on the page,
//then send the transcript along with the current question, topic, difficulty, and language to /api/exam_turn to get AI feedback.
//Finally, display the feedback, corrected answer, tip, score, and store the next question if provided. Include basic error handling if any request fails.




//This is the prompt for the lookupDictionary function
//Write an async JavaScript function called lookupDictionary() that reads a word or phrase from an input field and sends,
//it to a backend /api/dictionary_ai endpoint using a POST request with JSON.
//The function should receive a response containing the headword, part of speech, meaning, examples, and synonyms,
//then display the results in a dictionary results area on the page.
//Include basic validation if no word is entered and handle errors if the request fails.



// This is the prompt for the events section
//Write a JavaScript section that attaches event listeners to multiple UI elements for a language practice page.
//The events should handle actions such as starting practice, starting and stopping audio recording,
//playing a question with text-to-speech, retrying an answer, moving to the next question, skipping a question,
//and looking up a word in a dictionary.
//Each event listener should call the appropriate function,
//(like startPractice, startRecording, stopRecording, speakText, processAudioBlob, and lookupDictionary) and update the UI accordingly.
//Include checks to ensure the elements exist before attaching the event listeners.

