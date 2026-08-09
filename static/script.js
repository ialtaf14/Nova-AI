const chatBox = document.getElementById('chat-box');
const textInput = document.getElementById('text-input');
const sendBtn = document.getElementById('send-btn');
const micBtn = document.getElementById('mic-btn');
const muteBtn = document.getElementById('mute-btn');
const modelSelect = document.getElementById('model-select');
const statusDot = document.querySelector('.status-dot');

const googleBtn = document.getElementById('google-btn');

let isMuted = false;
let isGoogleModeOn = false;

// Google Search Mode Toggle Logic
if (googleBtn) {
    googleBtn.addEventListener('click', () => {
        isGoogleModeOn = !isGoogleModeOn;

        if (isGoogleModeOn) {
            googleBtn.classList.add('google-active');
            appendMessage('nova', '🌐 **Google Search Mode Activated** (Live results from Google — No API key needed!)');
        } else {
            googleBtn.classList.remove('google-active');
            appendMessage('nova', '💻 **Switched to Local AI** (Ollama)');
        }
    });
}

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
    muteBtn.classList.toggle('muted-active', isMuted);
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
                use_google: isGoogleModeOn
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

// Helper to strip URLs, HTML tags, and Markdown formatting before speaking aloud
function cleanTextForSpeech(text) {
    if (!text) return "";
    
    let clean = text;

    // 1. Remove HTML tags (e.g. <div class="map-card">, <iframe>, <a>)
    clean = clean.replace(/<[^>]*>/g, ' ');

    // 2. Convert markdown links [Link Title](https://...) -> keep ONLY "Link Title"
    clean = clean.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');

    // 3. Remove raw URLs (https://..., http://..., www....) completely
    clean = clean.replace(/https?:\/\/\S+/gi, '');
    clean = clean.replace(/www\.\S+/gi, '');

    // 4. Remove Markdown formatting symbols (*, #, _, `, ~, >, |, -, =)
    clean = clean.replace(/[*#_`~>|\-=]/g, ' ');

    // 5. Clean up multiple spaces
    clean = clean.replace(/\s+/g, ' ').trim();

    return clean;
}

// Text to Speech
function speak(text) {
    const cleanText = cleanTextForSpeech(text);
    if (!cleanText) return;

    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = 1.1;

    // Apply Voice based on last detected language
    const voice = getVoice(lastDetectedLang);
    if (voice) {
        utterance.voice = voice;
        console.log(`🗣️ Queued Speech: "${cleanText.substring(0, 30)}..." with ${voice.name}`);
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

let stagedImageFile = null;

// Image Attachment Staging (Does NOT auto-send — waits until user clicks Send/Enter!)
const imageInput = document.getElementById('image-input');
const imageBtn = document.getElementById('image-btn');
const imagePreviewContainer = document.getElementById('image-preview-container');
const imagePreviewThumb = document.getElementById('image-preview-thumb');
const imagePreviewName = document.getElementById('image-preview-name');
const removeImageBtn = document.getElementById('remove-image-btn');

if (imageBtn && imageInput) {
    imageBtn.addEventListener('click', () => imageInput.click());

    imageInput.addEventListener('change', () => {
        const file = imageInput.files[0];
        if (!file) return;

        stagedImageFile = file;
        imagePreviewName.textContent = file.name;
        imagePreviewThumb.src = URL.createObjectURL(file);
        imagePreviewContainer.style.display = 'block';
        textInput.focus();
    });
}

if (removeImageBtn) {
    removeImageBtn.addEventListener('click', clearStagedImage);
}

function clearStagedImage() {
    stagedImageFile = null;
    if (imageInput) imageInput.value = '';
    if (imagePreviewContainer) imagePreviewContainer.style.display = 'none';
    if (imagePreviewThumb) imagePreviewThumb.src = '';
}

// Clear Chat Button Logic
const clearBtn = document.getElementById('clear-btn');
if (clearBtn) {
    clearBtn.addEventListener('click', () => {
        chatBox.innerHTML = `
            <div class="message nova-message">
                <div class="avatar">🤖</div>
                <div class="content">
                    Chat reset ho gaya hai! Main Nova hoon — created by <a href="https://ialtaf14.vercel.app/" target="_blank" style="color: #60a5fa; font-weight: 600; text-decoration: underline;">Altaf Khan</a>. Kaise help karoon aapki?
                    <div class="suggestion-chips">
                        <button class="chip" onclick="sendQuickPrompt('Who created you?')">👨‍💻 Creator Info</button>
                        <button class="chip" onclick="sendQuickPrompt('Tell me about Altaf Khan portfolio and skills')">🚀 Altaf's Portfolio</button>
                        <button class="chip" onclick="sendQuickPrompt('Help me write Python code')">🐍 Python Helper</button>
                        <button class="chip" onclick="sendQuickPrompt('What is Machine Learning?')">🧠 Machine Learning</button>
                    </div>
                </div>
            </div>
        `;
        clearStagedImage();
    });
}

// Quick Prompt Chips
function sendQuickPrompt(promptText) {
    textInput.value = promptText;
    sendMessage();
}

// Send Message Logic (Handles both staged image & text)
async function sendMessage() {
    const text = textInput.value.trim();
    if (!text && !stagedImageFile) return;

    // ⛔️ AUTO-INTERRUPTION LOGIC
    if (currentController) {
        currentController.abort();
        currentController = null;
    }
    if (synthesis.speaking) {
        synthesis.cancel();
    }

    // Language Detection
    lastDetectedLang = detectLanguage(text || 'Describe this image');
    console.log(`📝 Detected Language: ${lastDetectedLang}`);

    // If an image is staged, send Image + Prompt
    if (stagedImageFile) {
        const fileToSend = stagedImageFile;
        const promptText = text || 'Describe this image in detail.';
        
        appendMessage('user', `📷 Attached Image: ${fileToSend.name}${text ? '\n\n' + text : ''}`);
        textInput.value = '';
        clearStagedImage();

        const botMsgDiv = document.createElement('div');
        botMsgDiv.classList.add('message', 'nova-message');
        botMsgDiv.innerHTML = `<div class="avatar">🤖</div><div class="content"><span class="typing">Analyzing image with vision model...</span></div>`;
        chatBox.appendChild(botMsgDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
        const contentDiv = botMsgDiv.querySelector('.content');

        const formData = new FormData();
        formData.append('image', fileToSend);
        formData.append('query', promptText);

        try {
            const response = await fetch('/upload', { method: 'POST', body: formData });
            const data = await response.json();
            const formattedText = typeof marked !== 'undefined' ? marked.parse(data.response) : data.response;
            contentDiv.innerHTML = formattedText + `<div class="message-actions"><button class="copy-btn" onclick="copyMessageText(this)">📋 Copy</button></div>`;
            if (!isMuted && data.response) speak(data.response);
        } catch (error) {
            contentDiv.textContent = "Error: " + error.message;
        }
        return;
    }

    // Regular Text Stream Request
    appendMessage('user', text);
    textInput.value = '';

    const botMsgDiv = document.createElement('div');
    botMsgDiv.classList.add('message', 'nova-message');
    botMsgDiv.innerHTML = `<div class="avatar">🤖</div><div class="content"><span class="typing">Thinking...</span></div>`;
    chatBox.appendChild(botMsgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    const contentDiv = botMsgDiv.querySelector('.content');
    let fullResponse = "";

    sendBtn.style.display = 'none';
    const stopBtn = document.getElementById('stop-btn');
    stopBtn.style.display = 'block';

    currentController = new AbortController();
    const signal = currentController.signal;

    const stopGeneration = () => {
        if (currentController) {
            currentController.abort();
            currentController = null;
        }
        if (synthesis.speaking) synthesis.cancel();
        contentDiv.innerHTML += " <i>[Interrupted]</i>";
        resetUI(signal);
    };

    stopBtn.onclick = stopGeneration;

    const resetUI = (requestSignal) => {
        if (currentController && currentController.signal !== requestSignal) return;
        sendBtn.style.display = 'block';
        stopBtn.style.display = 'none';
        stopBtn.onclick = null;
        if (currentController && currentController.signal === requestSignal) {
            currentController = null;
        }
    };

    try {
        const response = await fetch('/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: text,
                use_google: isGoogleModeOn
            }),
            signal: signal
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        contentDiv.innerHTML = "";
        let sentenceBuffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            fullResponse += chunk;
            sentenceBuffer += chunk;

            const threshold = 100;
            const wasAtBottom = chatBox.scrollHeight - chatBox.scrollTop - chatBox.clientHeight <= threshold;

            contentDiv.innerHTML = marked.parse(fullResponse);

            if (wasAtBottom) {
                chatBox.scrollTop = chatBox.scrollHeight;
            }

            if (!isMuted) {
                let match = sentenceBuffer.match(/[.!?\n]+(?=\s|$)/);
                if (match) {
                    let endIdx = match.index + match[0].length;
                    let sentence = sentenceBuffer.substring(0, endIdx).trim();

                    if (sentence.length > 0) {
                        speak(sentence);
                    }

                    sentenceBuffer = sentenceBuffer.substring(endIdx);
                }
            }
        }

        // Add copy button to finished bot message
        contentDiv.innerHTML += `<div class="message-actions"><button class="copy-btn" onclick="copyMessageText(this)">📋 Copy</button></div>`;

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

// Copy Message Helper
function copyMessageText(btn) {
    const messageContent = btn.closest('.content').innerText.replace('📋 Copy', '').trim();
    navigator.clipboard.writeText(messageContent).then(() => {
        const originalText = btn.textContent;
        btn.textContent = '✅ Copied!';
        setTimeout(() => btn.textContent = originalText, 2000);
    }).catch(err => console.error("Copy failed:", err));
}

modelSelect.addEventListener('change', async () => {
    const model = modelSelect.value;
    const description = modelDescriptions[model] || 'Ready to assist capabilities';
    const realName = modelRealNames[model] || model.toUpperCase();

    appendMessage('nova', `🔄 Switched to model: <span class="flashlight-text">${realName}</span><br>✨ *${description}*`);

    await fetch('/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: `switch to ${model}` })
    });
    statusDot.style.backgroundColor = '#00ff88';
    setTimeout(() => statusDot.style.backgroundColor = '#333', 1000);
    updateModelStatusBadges();
});

// Update status badges in Model Select dropdown
async function updateModelStatusBadges() {
    try {
        const response = await fetch('/models/status');
        if (!response.ok) return;
        const data = await response.json();
        const installed = data.installed_models || [];
        const available = data.available_models || {};

        Array.from(modelSelect.options).forEach(opt => {
            const alias = opt.value;
            const realName = modelRealNames[alias] || opt.textContent.split(' (')[0];
            const targetModel = available[alias];
            if (!targetModel) return;

            const isInstalled = installed.some(m => 
                m === targetModel || 
                m.startsWith(targetModel + ':') || 
                m === `${targetModel}:latest`
            );

            if (isInstalled) {
                opt.textContent = `${realName} (Installed)`;
            } else {
                opt.textContent = `${realName} (Auto-download)`;
            }
        });
    } catch (e) {
        console.warn("Unable to fetch model status:", e);
    }
}

// Initial check on page load
updateModelStatusBadges();
