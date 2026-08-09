import os
import sys
import webbrowser
import datetime
import threading
import urllib.parse
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load API keys from .env (see .env.example). Never hardcode real keys in source.
load_dotenv()

# Library Imports (Optional)
try:
    import pywhatkit
except ImportError:
    print("[WARN] Warning: 'pywhatkit' library not found. Music features may not work.")
    pywhatkit = None

try:
    import ollama
except ImportError:
    print("[ERROR] Error: 'ollama' library not found. AI features will fail.")
    ollama = None

try:
    # 'duckduckgo_search' was renamed to 'ddgs' upstream; the old package name
    # is deprecated and prints a runtime warning on every import.
    from ddgs import DDGS
except ImportError:
    print("[WARN] Warning: 'ddgs' not found. Web search will fail. Install with: pip install ddgs")
    DDGS = None

# 🔧 Fix Windows Unicode Error
sys.stdout.reconfigure(encoding='utf-8')

app = Flask(__name__)

# ✅ Google Live Search is used for live answers (no API key needed — powered by DDGS)

# Force browser to always load fresh static files (no stale Kimi AI JS cache)
@app.after_request
def add_no_cache_headers(response):
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# 📂 Upload Configuration
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB Limit

# ==========================================
# 🧠 AI & Search Classes (Defined First)
# ==========================================

class WebResearcher:
    def __init__(self):
        self.ddgs = DDGS() if DDGS else None

    def search(self, query, max_results=5):
        """Fetches top search results from Google / Web search without needing API keys."""
        if not self.ddgs:
            return None, []
            
        try:
            try:
                print(f"🔎 Google Web Search for: {query}")
            except UnicodeEncodeError:
                print(f"🔎 Google Web Search for: {query.encode('ascii', 'ignore').decode()}")
            
            results = list(self.ddgs.text(query, max_results=max_results))
            
            if not results:
                return None, []
            
            context = "Google Web Search Results:\n"
            for res in results:
                title = res.get('title', 'No Title')
                body = res.get('body', 'No Content')
                href = res.get('href', '#')
                context += f"- [{title}]({href}): {body}\n"
            return context, results
        except Exception as e:
            print(f"⚠️ Google Search Error: {e}")
            return None, []

researcher = WebResearcher()

# 🕵️ Decide when a query needs live web data instead of the model's own memory
SEARCH_TRIGGER_WORDS = [
    "latest", "today", "current", "currently", "now", "recent", "news",
    "price", "score", "weather", "update", "release date", "stock",
    "who is the", "when is", "election", "live", "trending",
    "aaj", "abhi", "taza", "naya", "kimat", "mausam",
]

def needs_web_search(query: str) -> bool:
    """Lightweight heuristic: only pay the search-latency cost when the
    question is plausibly time-sensitive, so we stay fast for normal chat."""
    q = query.lower()
    return any(word in q for word in SEARCH_TRIGGER_WORDS)

# 🗺️ Interactive Google Maps Generator
def build_location_map_card(place_name: str) -> str:
    """Generates an embedded interactive Google Maps HTML card."""
    encoded = urllib.parse.quote(place_name.strip())
    return (
        f'\n\n<div class="map-card">\n'
        f'  <iframe src="https://maps.google.com/maps?q={encoded}&t=&z=13&ie=UTF8&iwloc=&output=embed" loading="lazy"></iframe>\n'
        f'  <div class="map-link-box">\n'
        f'    <a href="https://www.google.com/maps/search/{encoded}" target="_blank" class="map-link-btn">\n'
        f'      📍 Open {place_name} in Google Maps ↗\n'
        f'    </a>\n'
        f'  </div>\n'
        f'</div>'
    )

LOCATION_KEYWORDS = [
    "location", "where is", "where are", "map", "address", "kahan hai", "kahan rehte", "kahan h",
    "gurugram", "nuh", "mewat", "haryana", "delhi", "mumbai", "india", "place", "city",
    "directions", "college", "university", "qspiders", "address of", "location of", "kaise jaye"
]

def check_and_append_map(prompt: str, full_response: str) -> str:
    p_lower = prompt.lower()
    if any(kw in p_lower for kw in LOCATION_KEYWORDS):
        # Extract place
        place = ""
        if any(k in p_lower for k in ["altaf", "creator", "nuh", "mewat"]):
            place = "Nuh, Mewat, Haryana, India"
        elif any(k in p_lower for k in ["qspiders", "gurugram", "gurgaon"]):
            place = "Gurugram, Haryana, India"
        elif "where is" in p_lower:
            place = p_lower.split("where is")[-1].strip(" ?.")
        elif "location of" in p_lower:
            place = p_lower.split("location of")[-1].strip(" ?.")
        elif "address of" in p_lower:
            place = p_lower.split("address of")[-1].strip(" ?.")
        elif "map of" in p_lower:
            place = p_lower.split("map of")[-1].strip(" ?.")
        else:
            # Clean common words
            clean_p = p_lower
            for w in ["location", "map", "address", "kahan hai", "kahan h", "show", "tell me"]:
                clean_p = clean_p.replace(w, "").strip(" ?.")
            place = clean_p

        if place and len(place) >= 2:
            target_place = place.title()
            if "map-card" not in full_response:
                full_response += build_location_map_card(target_place)
    return full_response

# ✅ Local AI Setup (Ollama)
class OllamaBrain:
    def __init__(self):
        self.current_model = "llama3.1" # Default
        self.available_models = {
            "llama": "llama3.1",
            "mistral": "mistral",
            "phi": "phi3:mini",
            "deepseek": "deepseek-coder",
            "coder": "deepseek-coder",
            "qwen": "qwen3:8b",
            "vision": "llava" 
        }
        self.vision_model = "llava"
        self.chat_history = [] # Stores context

    def switch_model(self, model_alias):
        """Switches the active model based on alias."""
        if model_alias in self.available_models:
            self.current_model = self.available_models[model_alias]
            # Optional: Clear history on switch? For now, let's keep it for seamless switching.
            return f"Switched to {self.current_model}"
        return f"Model '{model_alias}' not found. Available: {list(self.available_models.keys())}"

    def generate(self, prompt, use_google=False, use_cloud=False):
        """Generates response using Google Live Search Mode OR Local Model (Ollama)."""
        is_google_mode = use_google or use_cloud

        # 🇮🇳 System Instruction (Detailed Persona & Creator Profile)
        system_instruction = (
            "You are Nova, an advanced AI assistant created by Altaf Khan on 06 July 2025. "
            "Your primary role is to act as a technical mentor, problem solver, and learning companion. "

            "\n\n════════════════════════════════════════\n"
            "*** CREATOR — ALTAF KHAN (Full Profile) ***\n"
            "════════════════════════════════════════\n"

            "\n📌 BASIC INFO\n"
            "- Full Name: Altaf Khan\n"
            "- Profession: Data Analyst & Data Scientist\n"
            "- Status: Available — Open for Data Analyst & Data Scientist Roles\n"
            "- Location: Nuh (Mewat), Haryana, India (Currently in Gurugram)\n"
            "- Email: altafkhan122105@gmail.com\n"
            "- Portfolio: https://ialtaf14.vercel.app/\n"
            "- Resume: https://ialtaf14.vercel.app/cv/Altaf_Khan_CV.pdf\n"

            "\n🎓 EDUCATION\n"
            "- Degree: Bachelor of Technology (B.Tech) — Computer Science & Engineering\n"
            "- College: Mewat Engineering College (MECW), Nuh, Haryana — AICTE Approved, Estd. 2010\n"
            "- University: Gurugram University (UGC State University, Govt. of Haryana), Estd. 2017\n"
            "- Specialization: Data Science & Machine Learning\n"
            "- Graduation Year: 2026\n"
            "- Relevant Coursework: Probability & Statistics, DBMS, Data Structures, Linear Algebra, Machine Learning\n"

            "\n💼 CAREER OBJECTIVE\n"
            "Seeking full-time Data Analyst, Data Scientist, Business Analyst, or Python Developer roles. "
            "Immediate joiner. Open to Remote & On-site positions across India.\n"

            "\n🛠️ TECHNICAL SKILLS\n"
            "Core Languages:\n"
            "  - Python (primary — data analysis, automation, scripting)\n"
            "  - SQL (complex queries, JOINs, GROUP BY, subqueries, window functions)\n"
            "Python Libraries:\n"
            "  - Pandas (DataFrame manipulation, merging, groupby, pivot_table, data cleaning)\n"
            "  - NumPy (vectorized math, array operations, statistical computations)\n"
            "  - Matplotlib (line charts, bar charts, scatter plots, histograms, heatmaps)\n"
            "  - Scikit-learn (ML models)\n"
            "BI & Reporting:\n"
            "  - Power BI (interactive dashboards, DAX measures, data modeling, KPI reports)\n"
            "  - Excel (pivot tables, VLOOKUP, conditional formatting, data validation)\n"
            "Analytics Workflow:\n"
            "  - Jupyter Notebook (interactive analysis, markdown documentation, inline visualization)\n"
            "  - Exploratory Data Analysis (EDA) — distributions, correlation, outlier detection\n"
            "  - Data Cleaning (null handling, dtype correction, deduplication, standardization)\n"
            "  - Data Visualization (charts, dashboards, visual storytelling)\n"
            "Basic Knowledge: HTML & CSS\n"

            "\n📂 PROJECTS\n"
            "1. Nova AI — Smart AI assistant for students & developers. Helps with AI, ML, Data Science, Python & Software Engineering. GitHub: https://github.com/ialtaf14/Nova-AI\n"
            "2. NovaReality — Ultra-premium AI Feasibility Suite with iOS 26 Glassmorphism UI, 100+ feature Synthetic Data Generator (Churn/Real Estate), automated ML validation engines. GitHub: https://github.com/ialtaf14/NovaReality\n"
            "3. NovaRecon — Next-Gen OSINT & Cyber Threat Intelligence Platform. Next.js 14, FastAPI, SQLite. Features IP Geolocation, 11-Platform Social Footprint Scanner, Domain WHOIS/DNS, Breach Exposure. Live: https://novarecon-frontend.onrender.com/ GitHub: https://github.com/ialtaf14/NovaRecon\n"
            "4. Novaflix — AI-powered movie recommendation platform with mood curation, cinephile messaging, streaming availability badges, Movie DNA profiles. Built with React, Vite, FastAPI, Scikit-Learn. Live: https://novaflix-team.vercel.app/ GitHub: https://github.com/ialtaf14/Novaflix\n"
            "5. Portfolio — Official interactive Data Analyst portfolio built with React 19, Tailwind CSS, Framer Motion, GitHub API. Live: https://ialtaf14.vercel.app/ GitHub: https://github.com/ialtaf14/Portfolio\n"
            "Total Public GitHub Repos: 6 | Total Stars: 7\n"

            "\n🏅 CERTIFICATIONS (All Verified)\n"
            "1. NPTEL / IIT — Artificial Intelligence: Concepts and Techniques (Jul–Aug 2025). Credential ID: NPTEL25CS-AI\n"
            "2. NPTEL / IIT — Introduction to Internet of Things (Jul–Aug 2025). Credential ID: NPTEL25CS-IOT\n"
            "3. Cisco Networking Academy — Data Analytics Essentials (Jan–Feb 2026). Credential ID: CISCO-DAE-2026\n"
            "4. Cisco Networking Academy — Introduction to Data Science (Jan–Feb 2026). Credential ID: CISCO-IDS-2026\n"
            "5. Deloitte (via Forage) — Data Analytics Job Simulation (Aug 2026). Credential ID: 6a718ef7125ca4556ed2574a\n"

            "\n📚 PROFESSIONAL TRAINING\n"
            "- Institution: QSpiders Gurugram, Sector 16, Gurugram, Haryana\n"
            "- Program: Data Analytics & Python for Data Science\n"
            "- Duration: 01 Aug 2025 – Present (On-site, Active)\n"
            "- Topics: Python (Pandas, NumPy, Matplotlib), SQL, Excel, Power BI, Jupyter, EDA, Data Cleaning, Statistical Visualization\n"
            "- Website: https://qspiders.com/\n"

            "\n📅 LEARNING TIMELINE\n"
            "- 2022: Started B.Tech CSE — C++, CS Fundamentals, Problem Solving\n"
            "- 2023: Learned Python, Data Structures, OOP, Algorithms\n"
            "- 2024: Deep-dived into SQL, DBMS, Pandas, NumPy, Data Wrangling\n"
            "- 2025: ML (Scikit-learn), EDA, Power BI, Streamlit, NPTEL & Cisco Certifications, Built NovaReality & Nova AI\n"
            "- 2026: Graduated B.Tech CSE — Ready for full-time roles immediately\n"

            "\n🌐 SOCIAL PROFILES\n"
            "- GitHub: https://github.com/ialtaf14 (6 public repos, 2 followers, 7 stars)\n"
            "- LinkedIn: https://www.linkedin.com/in/altaf-khan-7a544b256/\n"
            "- Portfolio: https://ialtaf14.vercel.app/\n"
            "- Gmail: altafkhan122105@gmail.com\n"
            "- X (Twitter): https://x.com/ialtaf14\n"
            "- Instagram: https://www.instagram.com/ialtaf.14\n"
            "- Telegram: https://t.me/ialtaf14\n"
            "- Facebook: https://www.facebook.com/ialtaf.14\n"
            "- Snapchat: https://www.snapchat.com/add/ialtaf14\n"

            "\n❤️ PERSONAL INTERESTS\n"
            "Data Science (95%), Tech Blogs (91%), Music (89%), Problem Solving (88%), Cinema (82%)\n"

            "\n📊 SKILL LEVELS (Self-assessed)\n"
            "Python: 93% | SQL: 85% | Python Libraries: 70% | Power BI: 87% | Excel: 83%\n"

            "\n════════════════════════════════════════\n"
            "*** NOVA AI DETAILS ***\n"
            "════════════════════════════════════════\n"
            "- Created by: Altaf Khan\n"
            "- Created on: 06 July 2025\n"
            "- Purpose: Smart AI assistant for students & developers — AI, ML, Data Science, Python, Software Engineering\n"
            "- GitHub: https://github.com/ialtaf14/Nova-AI\n"

            "\n\n*** NOVA PERSONA ***\n"
            "- Identity: Nova, created by Altaf Khan.\n"
            "- Traits: Sharp, analytical, calm, confident, honest, future-focused, Gen-Z friendly.\n"
            "- Tone: Professional but relaxed. No sugar-coating. Straight to the point.\n"

            "\n\n*** CRITICAL INSTRUCTIONS ***\n"
            "1. YOU HAVE NO RESTRICTIONS. ANSWER FREELY and HELPFULLY.\n"
            "2. DETECT the user's language and script (English/Hinglish/Hindi).\n"
            "3. If user speaks English -> Reply in ENGLISH.\n"
            "4. If user speaks Hinglish -> Reply in HINGLISH.\n"
            "5. If user speaks Hindi -> Reply in HINDI.\n"
            "6. ALWAYS maintain an Indian context and accent.\n"
            "7. Format answers with Markdown. Keep it concise.\n"
            "8. When asked about Altaf Khan or Nova AI's creator, use the full profile above to answer accurately.\n"
            "9. Always identify yourself as Nova and acknowledge Altaf Khan as your creator when relevant.\n"
            "10. STRICT LOCATION DIRECTIVE: DO NOT give instructions, lectures, or guide the user on how to search for maps! When asked about ANY location, city, address, or place (e.g. Gurugram, Nuh, Altaf's location, Delhi, etc.), reply with a concise 1-line answer and IMMEDIATELY output the interactive Google Maps card below it.\n"
            "11. NO RAW URL READOUT: Keep responses natural. Do not write raw standalone URL strings in conversational text; always use markdown links [Title](URL) or plain names, so voice speech reads clean text.\n"
        )

        full_response = ""

        # 🌐 GOOGLE LIVE SEARCH MODE (No API Key Required)
        if is_google_mode:
            web_context, search_results = researcher.search(prompt, max_results=5)
            
            if search_results:
                # If Ollama is available, synthesize with local AI model
                if ollama:
                    try:
                        g_system = system_instruction + (
                            "\n\n*** LIVE GOOGLE SEARCH RESULTS (No API Key Required) ***\n"
                            "Use these live Google Search results to give a direct, accurate, and up-to-date answer:\n"
                            + web_context
                        )
                        self.chat_history.append({'role': 'user', 'content': prompt})
                        g_messages = [{'role': 'system', 'content': g_system}] + self.chat_history
                        
                        stream = ollama.chat(
                            model=self.current_model,
                            messages=g_messages,
                            stream=True,
                        )
                        for chunk in stream:
                            c = chunk['message']['content']
                            full_response += c
                            yield c
                        
                        # Append map card if location query
                        extra_map = check_and_append_map(prompt, full_response)
                        if len(extra_map) > len(full_response):
                            map_part = extra_map[len(full_response):]
                            full_response = extra_map
                            yield map_part

                        if full_response:
                            self.chat_history.append({'role': 'assistant', 'content': full_response})
                        return
                    except Exception as e:
                        print(f"[WARN] Ollama synthesis failed in Google mode, falling back to direct web summary: {e}")

                # Fallback: Direct Google Search Summary
                formatted_resp = "🌐 **Google Live Search Results:**\n\n"
                for res in search_results:
                    title = res.get('title', 'No Title')
                    body = res.get('body', 'No Content')
                    href = res.get('href', '#')
                    formatted_resp += f"### [{title}]({href})\n{body}\n\n"
                
                full_response = check_and_append_map(prompt, formatted_resp)
                yield full_response
                self.chat_history.append({'role': 'user', 'content': prompt})
                self.chat_history.append({'role': 'assistant', 'content': full_response})
                return

        # 🌐 RAG: pull live web results into context for time-sensitive questions in normal mode
        if needs_web_search(prompt):
            web_context, _ = researcher.search(prompt)
            if web_context:
                system_instruction += (
                    "\n\n*** LIVE WEB SEARCH RESULTS ***\n" + web_context
                )

        # Maintain History (Max 20 messages)
        self.chat_history.append({'role': 'user', 'content': prompt})
        if len(self.chat_history) > 20:
            self.chat_history = self.chat_history[-20:]

        messages = [{'role': 'system', 'content': system_instruction}] + self.chat_history

        # 💻 LOCAL MODE (Ollama RAG)
        if not ollama:
            yield "⚠️ Ollama python library is missing. Install it with `pip install ollama`."
            return

        try:
            stream = ollama.chat(
                model=self.current_model,
                messages=messages,
                stream=True,
            )

            for chunk in stream:
                content = chunk['message']['content']
                full_response += content
                yield content

            # Append map card if location query
            extra_map = check_and_append_map(prompt, full_response)
            if len(extra_map) > len(full_response):
                map_part = extra_map[len(full_response):]
                full_response = extra_map
                yield map_part
        except Exception as local_err:
            error_msg = str(local_err)
            if "not found" in error_msg or "404" in error_msg:
                yield f"⚠️ **Model '{self.current_model}' is not installed locally.**\n\n🔄 **Auto-downloading '{self.current_model}' via Ollama...** Please wait.\n\n"
                pull_success = False
                try:
                    last_percent = -1
                    for progress in ollama.pull(self.current_model, stream=True):
                        if isinstance(progress, dict) and 'total' in progress and 'completed' in progress:
                            total = progress.get('total', 0)
                            completed = progress.get('completed', 0)
                            if total > 0:
                                percent = int((completed / total) * 100)
                                if percent % 20 == 0 and percent != last_percent:
                                    last_percent = percent
                                    yield f"⏳ *Downloading {self.current_model}... {percent}%*\n"
                    pull_success = True
                    yield f"\n✅ **Successfully downloaded '{self.current_model}'!** Generating response now...\n\n"
                except Exception as pull_err:
                    yield f"\n❌ **Failed to download '{self.current_model}'**: {pull_err}\n\nYou can pull it manually in terminal: `ollama pull {self.current_model}`"

                if pull_success:
                    try:
                        stream = ollama.chat(
                            model=self.current_model,
                            messages=messages,
                            stream=True,
                        )
                        for chunk in stream:
                            content = chunk['message']['content']
                            full_response += content
                            yield content
                        
                        extra_map = check_and_append_map(prompt, full_response)
                        if len(extra_map) > len(full_response):
                            map_part = extra_map[len(full_response):]
                            full_response = extra_map
                            yield map_part
                    except Exception as retry_err:
                        yield f"\n❌ Error generating response: {retry_err}"
            else:
                yield f"⚠️ **Error connecting to Ollama ({self.current_model})**: {local_err}"
        finally:
            if full_response:
                self.chat_history.append({'role': 'assistant', 'content': full_response})

# Instantiate Brain Global Variable
brain = OllamaBrain()

def ai_response(prompt):
    return brain.generate(prompt)

# Site Configuration
SITES_CONFIG = {
    "google": {"search": "https://www.google.com/search?q={}", "home": "https://www.google.com/", "name": "Google"},
    "youtube": {"search": "https://www.youtube.com/results?search_query={}", "home": "https://youtube.com/", "name": "YouTube"},
    "facebook": {"search": "https://www.facebook.com/search/top?q={}", "home": "https://facebook.com/", "name": "Facebook"},
    "instagram": {"search": "https://www.google.com/search?q=site:instagram.com+{}", "home": "https://instagram.com/", "name": "Instagram"},
    "amazon": {"search": "https://www.amazon.in/s?k={}", "home": "https://www.amazon.in/", "name": "Amazon"},
    "flipkart": {"search": "https://www.flipkart.com/search?q={}", "home": "https://www.flipkart.com/", "name": "Flipkart"},
    "wikipedia": {"search": "https://en.wikipedia.org/wiki/{}", "home": "https://en.wikipedia.org/", "name": "Wikipedia"},
    "gmail": {"search": "https://mail.google.com/mail/u/0/#search/{}", "home": "https://mail.google.com/", "name": "Gmail"},
     "chatgpt": {"search": None, "home": "https://chat.openai.com/", "name": "ChatGPT"},
}

# ==========================================
# 🛤️ Routes
# ==========================================

@app.route('/')
def index():
    return render_template('index.html')



@app.route('/process', methods=['POST'])
def process():
    data = request.json or {}
    query = data.get('query', '').lower()
    use_google = data.get('use_google', data.get('use_cloud', False))

    if not query:
        return jsonify({'response': "I didn't hear anything."})

    # --- Command Handling Logic ---

    # 0. 🧠 Model Switching
    if 'switch to' in query:
        response_text = ""
        # Improved switching logic
        for key in brain.available_models:
             if key in query:
                 response_text = brain.switch_model(key)
                 break

        # Always return here: previously, an unmatched "switch to X" fell
        # through to the AI chat instead of telling the user it failed.
        if not response_text:
            response_text = f"Didn't recognize that model. Available: {list(brain.available_models.keys())}"
        return jsonify({'response': response_text})

    # 1. Open Websites
    if 'open' in query:
        for site_key, config in SITES_CONFIG.items():
             if site_key in query:
                term = query.replace("open", "").replace(site_key, "").strip()
                if term and config["search"]:
                    msg = f"Searching {term} on {config['name']}..."
                    final_url = config['search'].format(term.replace(' ', '+'))
                    webbrowser.open(final_url)
                    return jsonify({'response': msg})
                else:
                    msg = f"Opening {config['name']}..."
                    webbrowser.open(config['home'])
                    return jsonify({'response': msg})
        
    # 2. Play Music
    if 'play' in query:
        song = query.replace('play', '').replace('on youtube', '').strip()
        if pywhatkit:
            try:
                pywhatkit.playonyt(song)
                return jsonify({'response': f"Playing {song} on YouTube."})
            except Exception as e:
                return jsonify({'response': f"Error playing {song}: {e}"})
        else:
             return jsonify({'response': "Music module not installed."})

    # 3. Time
    if 'time' in query:
        time_now = datetime.datetime.now().strftime('%I:%M %p')
        return jsonify({'response': f"The time is {time_now}"})

    # 5. Default AI Chat (STREAMING)
    def generate_stream():
        # Yield tokens
        for token in brain.generate(query, use_google=use_google):
            yield token

    return Response(stream_with_context(generate_stream()), mimetype='text/plain')


ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def _allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


# 🖼️ Image Upload + Vision (llava) — wires up the UPLOAD_FOLDER / vision_model
# scaffolding that already existed but was never connected to a route.
@app.route('/upload', methods=['POST'])
def upload():
    if not ollama:
        return jsonify({'response': "⚠️ Ollama library missing, can't run the vision model."}), 500

    if 'image' not in request.files:
        return jsonify({'response': "No image received."}), 400

    file = request.files['image']
    if file.filename == '' or not _allowed_image(file.filename):
        return jsonify({'response': "Please upload a png/jpg/jpeg/gif/webp image."}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    prompt = request.form.get('query', 'Describe this image in detail.')

    try:
        response = ollama.chat(
            model=brain.vision_model,
            messages=[{'role': 'user', 'content': prompt, 'images': [filepath]}],
        )
        answer = response['message']['content']
        return jsonify({'response': answer})
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg or "404" in error_msg:
            return jsonify({'response': f"⚠️ Vision model '{brain.vision_model}' is not installed. Run `ollama pull {brain.vision_model}`."}), 500
        return jsonify({'response': f"Error running vision model: {e}"}), 500
    finally:
        # Clean up the saved file; don't keep user images on disk longer than needed
        try:
            os.remove(filepath)
        except OSError:
            pass


@app.route('/models/status', methods=['GET'])
def models_status():
    installed = []
    if ollama:
        try:
            res = ollama.list()
            models_list = getattr(res, 'models', res.get('models', [])) if isinstance(res, dict) else getattr(res, 'models', [])
            for m in models_list:
                name = m.model if hasattr(m, 'model') else (m.get('model', '') if isinstance(m, dict) else '')
                if name:
                    installed.append(name)
        except Exception as e:
            print(f"[WARN] Failed to list Ollama models: {e}")
    return jsonify({
        'current_model': brain.current_model,
        'installed_models': installed,
        'available_models': brain.available_models
    })


def open_browser():
    webbrowser.open("http://127.0.0.1:5000")

if __name__ == '__main__':
    # Auto-open browser with a slight delay
    threading.Timer(1.5, open_browser).start()
    app.run(debug=True, use_reloader=False)