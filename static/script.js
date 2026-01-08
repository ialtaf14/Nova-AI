const chatBox = document.getElementById('chat-box');
const textInput = document.getElementById('text-input');
const sendBtn = document.getElementById('send-btn');
const micBtn = document.getElementById('mic-btn');
const muteBtn = document.getElementById('mute-btn');
const modelSelect = document.getElementById('model-select');
const statusDot = document.querySelector('.status-dot');

const cloudBtn = document.getElementById('cloud-btn');

let isMuted = false;
let isCloudModeOn = false;

// Kimi (Cloud) Toggle Logic
cloudBtn.addEventListener('click', () => {
    isCloudModeOn = !isCloudModeOn;

    if (isCloudModeOn) {
        cloudBtn.classList.add('cloud-active');
        appendMessage('nova', '☁️ **Connected to Kimi AI** (Moonshot Cloud)');
    } else {
        cloudBtn.classList.remove('cloud-active');
        appendMessage('nova', '💻 **Switched to Local AI** (Ollama)');
    }
});

let synthesis = window.speechSynthesis;
let recognition = null;

// Initialize Speech Recognition
if ('webkitSpeechRecognition' in window) {
    recognition = new webkitSpeechRecognition();
    recognition.continuous = false;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
        micBtn.classList.add('listening');
        textInput.placeholder = "Listening...";
    };

    recognition.onend = () => {
        micBtn.classList.remove('listening');
        textInput.placeholder = "Type a command...";
    };

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        textInput.value = transcript;
        sendMessage();
    };
} else {
    micBtn.style.display = 'none';
    console.warn("Speech Recognition not supported.");
}

// Event Listeners
sendBtn.addEventListener('click', sendMessage);
textInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
});

micBtn.addEventListener('click', () => {
    if (recognition) recognition.start();
});

muteBtn.addEventListener('click', () => {
    isMuted = !isMuted;
    muteBtn.textContent = isMuted ? '🔇' : '🔊';
    if (isMuted) synthesis.cancel();
});

// Append Message to UI
function appendMessage(sender, text) {
    const msgDiv = document.createElement('div');
    msgDiv.classList.add('message', sender === 'user' ? 'user-message' : 'nova-message');

    const avatar = document.createElement('div');
    avatar.classList.add('avatar');
    avatar.textContent = sender === 'user' ? '👤' : '🤖';

    const content = document.createElement('div');
    content.classList.add('content');

    // Parse Markdown for bot responses
    if (sender === 'nova' && typeof marked !== 'undefined') {
        content.innerHTML = marked.parse(text);
    } else {
        content.textContent = text;
    }

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(content);
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

let currentController = null; // Global controller for interruptions

// Send Message Logic
async function sendMessage() {
    const text = textInput.value.trim();
    if (!text) return;

    // ⛔️ AUTO-INTERRUPTION LOGIC
    // If a request is already running, abort it immediately
    if (currentController) {
        currentController.abort();
        currentController = null;
    }
    // Also stop any ongoing speech immediately
    if (synthesis.speaking) {
        synthesis.cancel();
    }

    // Detect language of the input
    lastDetectedLang = detectLanguage(text);
    console.log(`📝 Detected Language: ${lastDetectedLang}`);

    appendMessage('user', text);
    textInput.value = '';

    // Prepare bot message bubble for streaming
    const botMsgDiv = document.createElement('div');
    botMsgDiv.classList.add('message', 'nova-message');
    botMsgDiv.innerHTML = `<div class="avatar">🤖</div><div class="content"><span class="typing">Thinking...</span></div>`;
    chatBox.appendChild(botMsgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    const contentDiv = botMsgDiv.querySelector('.content');
    let fullResponse = "";

    // UI State: Showing thinking/generating
    sendBtn.style.display = 'none';
    const stopBtn = document.getElementById('stop-btn');
    stopBtn.style.display = 'block';

    // Create New Controller
    currentController = new AbortController();
    const signal = currentController.signal;

    // Stop Button Logic (Manual)
    const stopGeneration = () => {
        if (currentController) {
            currentController.abort();
            currentController = null;
        }
        if (synthesis.speaking) synthesis.cancel();
        contentDiv.innerHTML += " <i>[Interrupted]</i>";
        resetUI(signal); // Pass signal to identify this specific request
    };

    stopBtn.onclick = stopGeneration;

    const resetUI = (requestSignal) => {
        // Only reset UI if we are the ACTIVE controller
        // If currentController has changed (new request started), do NOT touch UI
        if (currentController && currentController.signal !== requestSignal) {
            return;
        }
        // If we are the active one (or null), it's safe to reset
        sendBtn.style.display = 'block';
        stopBtn.style.display = 'none';
        stopBtn.onclick = null; // Clean up listener
        if (currentController && currentController.signal === requestSignal) {
            currentController = null; // Clear if we finished naturally
        }
    };

    try {
        const response = await fetch('/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: text,
                use_cloud: isCloudModeOn
            }),
            signal: signal
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        // Remove typing indicator
        contentDiv.innerHTML = "";

        let sentenceBuffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            fullResponse += chunk;
            sentenceBuffer += chunk;

            // Smart Scrolling Logic
            // Check if user is near bottom BEFORE updating content
            const threshold = 100; // pixels
            const wasAtBottom = chatBox.scrollHeight - chatBox.scrollTop - chatBox.clientHeight <= threshold;

            contentDiv.innerHTML = marked.parse(fullResponse);

            // Only scroll if user was already at the bottom
            if (wasAtBottom) {
                chatBox.scrollTop = chatBox.scrollHeight;
            }

            // Speak available sentences if not muted
            if (!isMuted) {
                // Check for sentence boundaries: periods, questions, exclamations, newlines
                // We look for punctuation followed by space or end of string
                let match = sentenceBuffer.match(/[.!?\n]+(?=\s|$)/);
                if (match) {
                    let endIdx = match.index + match[0].length;
                    let sentence = sentenceBuffer.substring(0, endIdx).trim();

                    if (sentence.length > 0) {
                        speak(sentence);
                    }

                    // Remove spoken part from buffer
                    sentenceBuffer = sentenceBuffer.substring(endIdx);
                }
            }
        }

        // Speak any remaining text in buffer
        if (!isMuted && sentenceBuffer.trim().length > 0) {
            speak(sentenceBuffer.trim());
        }

    } catch (error) {
        if (error.name === 'AbortError') {
            console.log("Generation aborted by user.");
        } else {
            contentDiv.textContent = "Error: " + error.message;
        }
    } finally {
        resetUI(signal);
    }
}

// Language Detection Logic
function detectLanguage(text) {
    const lowerText = text.toLowerCase();

    // 1. Check for Devanagari script (Hindi)
    const hindiRegex = /[\u0900-\u097F]/;
    if (hindiRegex.test(text)) return 'hindi';

    // 2. Check for common Hinglish keywords
    const hinglishKeywords = [
        "kya", "kaise", "kaisa", "hai", "hain", "ho", "hu", "hoon",
        "nahi", "haan", "acha", "bura", "theek", "tum", "main", "hum",
        "karo", "karna", "baat", "bol", "sun", "dekho", "bhai", "yaar",
        "kaun", "kab", "kahan", "kyun", "kisliye", "namaste", "shukriya"
    ];

    // Check if any keyword exists as a whole word
    const isHinglish = hinglishKeywords.some(word =>
        new RegExp(`\\b${word}\\b`).test(lowerText)
    );

    return isHinglish ? 'hinglish' : 'english';
}

let lastDetectedLang = 'english'; // Default

// Helper to get voice by gender preference
function getVoice(lang) {
    const voices = synthesis.getVoices();
    let preferredVoice = null;

    // Universal preference for Indian Accents
    // Checks for 'IN' region code, 'India', or 'Hindi' in name
    const indianVoices = voices.filter(v => v.lang.includes('IN') || v.name.includes('India') || v.name.includes('Hindi'));

    if (lang === 'hindi' || lang === 'hinglish') {
        // FEMALE Preference for Hindi/Hinglish (Indian Accent)
        // Prefer explicit Hindi voices, then any Indian Female
        preferredVoice = indianVoices.find(v => v.lang.includes('hi') || v.name.includes('Hindi') || v.name.includes('Kalpana') || v.name.includes('Heera'));

        // Fallback: Any Indian Female
        if (!preferredVoice) preferredVoice = indianVoices.find(v => v.name.includes('Female'));

        // Fallback: Any Indian voice found
        if (!preferredVoice) preferredVoice = indianVoices[0];

    } else {
        // MALE Preference for English (Indian Accent)
        // Look for "Ravi" (Windows) or generic Male Indian
        preferredVoice = indianVoices.find(v => (v.name.includes('Male') || v.name.includes('Ravi')) && !v.name.includes('Female'));

        // If no Male Indian found, try any English (India) voice that isn't explicitly Female (unless no choice)
        if (!preferredVoice) preferredVoice = indianVoices.find(v => v.lang.includes('en') && !v.name.includes('Female'));

        // Fallback: Any Indian Voice (even if female, better than US accent if user demands Indian)
        if (!preferredVoice) preferredVoice = indianVoices.find(v => v.lang.includes('en'));
    }

    // Final Fallback: If absolutely no Indian voices are found on the system
    if (!preferredVoice && voices.length > 0) {
        console.warn("No Indian voices found. Falling back to default.");
        preferredVoice = voices[0];
    }

    return preferredVoice;
}

// Text to Speech
// Text to Speech
function speak(text) {
    // Note: We do NOT cancel() here to allow sentence queuing.
    // Speech is cancelled explicitly by stop button or new message start.

    // Strip markdown symbols including * for bold, # for headers, etc.
    const cleanText = text.replace(/[*#_`]/g, '');

    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = 1.1;

    // Apply Voice based on last detected language
    const voice = getVoice(lastDetectedLang);
    if (voice) {
        utterance.voice = voice;
        console.log(`🗣️ Queued Chunk: "${cleanText.substring(0, 20)}..." with ${voice.name}`);
    }

    synthesis.speak(utterance);
}

function stopSpeaking() {
    if (synthesis.speaking) synthesis.cancel();
}

// Model Selection
const modelDescriptions = {
    'llama': 'Best for General Reasoning & Chat',
    'qwen': 'Best for Logic & Mathematics',
    'mistral': 'Best for Balanced Performance',
    'phi': 'Best for Speed & Efficiency',
    'coder': 'Best for Coding & Programming'
};

const modelRealNames = {
    'llama': 'Llama 3.1',
    'qwen': 'Qwen 3',
    'mistral': 'Mistral 7B',
    'phi': 'Phi-3',
    'coder': 'DeepSeek R1'
};

modelSelect.addEventListener('change', async () => {
    const model = modelSelect.value;
    const description = modelDescriptions[model] || 'Ready to assist capabilities';
    const realName = modelRealNames[model] || model.toUpperCase();

    // Notify user in chat with Flashlight Effect
    appendMessage('nova', `🔄 Switched to model: <span class="flashlight-text">${realName}</span><br>✨ *${description}*`);

    await fetch('/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: `switch to ${model}` })
    });
    statusDot.style.backgroundColor = '#00ff88'; // Green indicating active
    setTimeout(() => statusDot.style.backgroundColor = '#333', 1000);
});
