import speech_recognition as sr
import pyttsx3
import datetime
import wikipedia
import webbrowser
import pywhatkit
import google.generativeai as genai

# ✅ Gemini API Setup
genai.configure(api_key="AIzaSyCHZ2ePJCxAK45XARCJdcefsyGyQ3hpy6w")
  # replace this

# ✅ Voice Engine Setup
engine = pyttsx3.init()
engine.setProperty('rate', 175)
engine.setProperty('volume', 1)

import msvcrt
import re
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text

# ✅ Rich Console Setup
console = Console()

# Global variable to store last spoken text for "read" command
last_response_text = ""

def print_nova_response(text):
    """Displays Nova's response in a styled panel."""
    md = Markdown(text)
    console.print(Panel(md, title="[bold cyan]Nova AI[/bold cyan]", border_style="cyan", expand=False))

def speak(text):
    global last_response_text
    last_response_text = text

    # Use the new Rich UI
    print_nova_response(text)
    
    # Chunking text for interruption
    chunks = re.split(r'([.?!,])', text)
    
    sentences = []
    # Re-attach punctuation
    for i in range(0, len(chunks)-1, 2):
        if chunks[i+1]:
            sentences.append(chunks[i] + chunks[i+1])
        else:
            sentences.append(chunks[i])
    if len(chunks) % 2 == 1 and chunks[-1]:
        sentences.append(chunks[-1])

    for sentence in sentences:
        if not sentence.strip():
            continue
            
        # Check for interruption (Keyboard only)
        if msvcrt.kbhit():
            msvcrt.getch() # clear buffer
            console.print("[bold red][Interrupted][/bold red]")
            engine.stop()
            return 
            
        engine.say(sentence)
        engine.runAndWait()

def listen():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        # console.print("[dim]Listening...[/dim]") # Optional: adding visual cue
        print("[Listening...]")
        r.pause_threshold = 1
        audio = r.listen(source)
    try:
        print("[Recognizing...]")
        query = r.recognize_google(audio, language='en-IN')
        # console.print(f"[bold green]You (Voice):[/bold green] {query}") # handled in main loop
        print(f"[You said]: {query}")
    except Exception:
        speak("Sorry, I didn't catch that. Please repeat.")
        return ""
    return query.lower()

def ai_response(prompt):
    try:
        # ✅ Use Gemini 2.5 Flash for free-tier compatibility
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content([prompt])
        if hasattr(response, "text") and response.text:
            return response.text.strip()
        else:
            return "Sorry, I didn't get any response from my AI brain."
    except Exception as e:
        print("[Error]:", e)
        return "Error occurred while connecting to Gemini API."

def main():
    console.clear()
    welcome_text = """
    [bold yellow]Welcome to your enhanced AI Assistant![/bold yellow]
    
    [bold white]Select your preferred Input Mode:[/bold white]
    1. [green]Voice Mode[/green] (Speak naturally)
    2. [blue]Text Mode[/blue]  (Type commands)
    """
    console.print(Panel(welcome_text, title="[bold magenta]System Startup[/bold magenta]", border_style="magenta"))
    
    try:
        mode_choice = console.input("\n[bold white]Enter choice (1 or 2): [/bold white]").strip()
    except UnicodeEncodeError:
        # Fallback if specific chars fail on some terminals
        mode_choice = input("\nEnter choice (1 or 2): ").strip()
    
    if mode_choice == '2':
        speak("Text mode activated.")
    else:
        speak("Voice mode activated. I'm listening.")

    while True:
        if mode_choice == '2':
            try:
                query = console.input("\n[bold green]You:[/bold green] ").lower()
            except UnicodeEncodeError:
                 query = input("\nYou: ").lower()
        else:
            query = listen()
            # If voice detected something, print it nicely
            if query:
                console.print(f"[bold green]You (Voice):[/bold green] {query}")

        if query == "":
            continue

        # 🔄 Dynamic Mode Switching
        if "switch to voice mode" in query:
            mode_choice = '1'
            speak("Switched to Voice Mode. I'm listening.")
            continue
        elif "switch to text mode" in query:
            mode_choice = '2'
            speak("Switched to Text Mode. Type your command.")
            continue
            
        # 📖 Read Command
        elif 'read' in query:
            if last_response_text:
                speak(last_response_text)
            else:
                speak("I haven't said anything yet to read.")
            continue

        # 🎵 Play Songs
        if 'play' in query:
            song = query.replace('play', '').strip()
            speak(f"Playing {song}")
            pywhatkit.playonyt(song)

        # 🕒 Time Query
        elif 'time' in query:
            time = datetime.datetime.now().strftime('%I:%M %p')
            speak(f"The time is {time}")

        # 🌐 Generic Website Handling
        # Site Configuration: key -> (search_url_template, home_url, display_name)
        # using {} placeholders for search queries
        sites_config = {
            "google": {
                "search": "https://www.google.com/search?q={}",
                "home": "https://www.google.com/",
                "name": "Google"
            },
            "facebook": {
                "search": "https://www.google.com/search?q=site:facebook.com+{}",
                "home": "https://facebook.com/",
                "name": "Facebook"
            },
            "twitter": {
                "search": "https://www.google.com/search?q=site:x.com+{}",
                "home": "https://x.com/",
                "name": "Twitter"
            },
            "x": {
                "search": "https://www.google.com/search?q=site:x.com+{}",
                "home": "https://x.com/",
                "name": "Twitter"
            },
            "instagram": {
                "search": "https://www.google.com/search?q=site:instagram.com+{}",
                "home": "https://instagram.com/",
                "name": "Instagram"
            },
            "snapchat": {
                "search": "https://www.google.com/search?q=site:snapchat.com+{}",
                "home": "https://snapchat.com/",
                "name": "Snapchat"
            },
            "telegram": {
                "search": "https://www.google.com/search?q=site:t.me+{}",
                "home": "https://web.telegram.org/",
                "name": "Telegram"
            },
            "linkedin": {
                "search": "https://www.google.com/search?q=site:linkedin.com/in+{}",
                "home": "https://linkedin.com/",
                "name": "LinkedIn"
            },
            "youtube": {
                "search": "https://www.google.com/search?q=site:youtube.com+{}",
                "home": "https://youtube.com/",
                "name": "YouTube"
            },
            "reddit": {
                "search": "https://www.google.com/search?q=site:reddit.com+{}",
                "home": "https://reddit.com/",
                "name": "Reddit"
            },
            "pinterest": {
                "search": "https://www.google.com/search?q=site:pinterest.com+{}",
                "home": "https://pinterest.com/",
                "name": "Pinterest"
            },
            "threads": {
                "search": "https://www.google.com/search?q=site:threads.net+{}",
                "home": "https://threads.net/",
                "name": "Threads"
            },
            "discord": {
                "search": "https://www.google.com/search?q=site:discord.com+{}",
                "home": "https://discord.com/",
                "name": "Discord"
            },
            # Shopping
            "amazon": {
                "search": "https://www.amazon.in/s?k={}",
                "home": "https://www.amazon.in/",
                "name": "Amazon"
            },
            "flipkart": {
                "search": "https://www.flipkart.com/search?q={}",
                "home": "https://www.flipkart.com/",
                "name": "Flipkart"
            },
            "meesho": {
                "search": "https://www.meesho.com/search?q={}",
                "home": "https://www.meesho.com/",
                "name": "Meesho"
            },
            "myntra": {
                "search": "https://www.myntra.com/{}",
                "home": "https://www.myntra.com/",
                "name": "Myntra"
            },
            "ajio": {
                "search": "https://www.ajio.com/search/?text={}",
                "home": "https://www.ajio.com/",
                "name": "Ajio"
            },
            "snapdeal": {
                "search": "https://www.snapdeal.com/search?keyword={}",
                "home": "https://www.snapdeal.com/",
                "name": "Snapdeal"
            },
            "aliexpress": {
                "search": "https://www.aliexpress.com/wholesale?SearchText={}",
                "home": "https://www.aliexpress.com/",
                "name": "AliExpress"
            },
            "ebay": {
                "search": "https://www.ebay.com/sch/i.html?_nkw={}",
                "home": "https://www.ebay.com/",
                "name": "eBay"
            },
            # Streaming
            "netflix": {
                "search": "https://www.netflix.com/search?q={}",
                "home": "https://www.netflix.com/",
                "name": "Netflix"
            },
            "hotstar": {
                "search": "https://www.hotstar.com/in/search?q={}",
                "home": "https://www.hotstar.com/in",
                "name": "Hotstar"
            },
            "spotify": {
                "search": "https://open.spotify.com/search/{}",
                "home": "https://open.spotify.com/",
                "name": "Spotify"
            },
            "gaana": {
                "search": "https://gaana.com/search/{}",
                "home": "https://gaana.com/",
                "name": "Gaana"
            },
            "jio saavn": {
                "search": "https://www.jiosaavn.com/search/{}",
                "home": "https://www.jiosaavn.com/",
                "name": "JioSaavn"
            },
            "saavn": {
                "search": "https://www.jiosaavn.com/search/{}",
                "home": "https://www.jiosaavn.com/",
                "name": "JioSaavn"
            },
             # Gaming
            "twitch": {
                "search": "https://www.twitch.tv/search?term={}",
                "home": "https://www.twitch.tv/",
                "name": "Twitch"
            },
            "steam": {
                "search": "https://store.steampowered.com/search/?term={}",
                "home": "https://store.steampowered.com/",
                "name": "Steam"
            },
             "epic games": {
                "search": "https://store.epicgames.com/en-US/browse?q={}",
                "home": "https://store.epicgames.com/",
                "name": "Epic Games"
            },
            "valorant": {
                "search": None, # No search, just open
                "home": "https://playvalorant.com/",
                "name": "Valorant"
            },
            # Productivity
            "gmail": {
                "search": "https://www.google.com/search?q=site:mail.google.com+{}",
                "home": "https://mail.google.com/",
                "name": "Gmail"
            },
             "google drive": {
                "search": "https://www.google.com/search?q=site:drive.google.com+{}",
                "home": "https://drive.google.com/",
                "name": "Google Drive"
            },
            "google docs": {
                "search": "https://www.google.com/search?q=site:docs.google.com+{}",
                "home": "https://docs.google.com/",
                "name": "Google Docs"
            },
             "google sheets": {
                "search": "https://www.google.com/search?q=site:sheets.google.com+{}",
                "home": "https://sheets.google.com/",
                "name": "Google Sheets"
            },
             "canva": {
                "search": "https://www.google.com/search?q=site:canva.com+{}",
                "home": "https://www.canva.com/",
                "name": "Canva"
            },
            "notion": {
                "search": "https://www.google.com/search?q=site:notion.so+{}",
                "home": "https://www.notion.so/",
                "name": "Notion"
            },
            "github": {
                "search": "https://www.google.com/search?q=site:github.com+{}",
                "home": "https://github.com/",
                "name": "GitHub"
            },
             "chatgpt": {
                "search": "https://www.google.com/search?q=site:chat.openai.com+{}",
                "home": "https://chat.openai.com/",
                "name": "ChatGPT"
            },

        }
        
        # Check for open commands
        if 'open' in query:
            found_site = False
            for site_key, config in sites_config.items():
                if site_key in query:
                    found_site = True
                    try:
                        # Extract search term: remove 'open', the site name, and common filler words
                        search_term = query.replace("open", "").replace(site_key, "").replace("search", "").replace(" on ", " ").strip()
                        
                        if search_term and config["search"]:
                            speak(f"Searching {search_term} on {config['name']}.")
                            # URL encode spaces slightly differently depending on the site if needed, 
                            # but simple replacement usually works for basic needs.
                            formatted_term = search_term.replace(' ', '+') if 'search?q=' in config['search'] or 'search/?text=' in config['search'] else search_term.replace(' ', '%20')
                            
                            # Correction for specific URL format requirements if any (simplified here)
                            final_url = config['search'].format(formatted_term)
                            webbrowser.open(final_url)
                        else:
                            speak(f"Opening {config['name']}.")
                            webbrowser.open(config['home'])
                    except Exception as e:
                        speak(f"Sorry, I couldn't open {config['name']} right now.")
                        print(e)
                    break # Stop after finding the first matching site
            
            # If 'open' was used but no site matched, pass through or handle generically?
            # For now, if no specific site matched but 'open' is there, 
            # the original code didn't have a catch-all 'open X' where X is unknown.
            # We can leave it to fall through to AI response if not matched.
            pass

        # 👋 Exit Command
        elif 'stop' in query or 'exit' in query or 'bye' in query:
            speak("Goodbye! Have a great day.")
            break

        # 📘 General Knowledge (Wikipedia)
        elif 'who is' in query or 'what is' in query or 'tell me about' in query or 'specs' in query or 'specifications' in query:
            try:
                # Check if user wants only specifications
                if any(word in query for word in ['specs', 'specifications', 'technical specs', 'give specs']):
                    topic = query.replace('specs', '').replace('specifications', '').replace('technical specs', '').replace('give', '').replace('of', '').strip()
                    speak(f"Okay, let's talk only about {topic}'s specifications.")
                    
                    while True:
                        from time import sleep
                        info = ai_response_spec(topic)  # strict spec mode response
                        speak(info)
                        print("\n" + info + "\n")
                        
                        speak("Do you want to know more about its specs or stop here?")
                        follow = listen()
                        
                        if any(x in follow for x in ['stop', 'done', 'that’s it', 'that is it', 'bas']):
                            speak("Got it. Exiting specification mode.")
                            break
                        elif follow.strip():
                            speak("Alright, what else about the specifications?")
                            topic = follow
                        else:
                            speak("Didn’t catch that. Please repeat.")
                        sleep(0.5)

                else:
                    topic = query.replace('who is', '').replace('what is', '').replace('tell me about', '').strip()
                    info = wikipedia.summary(topic, 2)
                    speak(info)

            except Exception:
                speak("Hmm, let me think deeper about that.")
                reply = ai_response(query)
                speak(reply)


        # 🧠 Default – Full AI Mode (for any type of question)
        else:
            print("[Thinking...]")
            reply = ai_response(query)
            speak(reply)
if __name__ == "__main__":
    main()