from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import requests
import base64
import io
import os
import threading
import datetime
import os
from dotenv import load_dotenv

load_dotenv()



# Optional voice-assistant imports
try:
    import speech_recognition as sr
    import pyttsx3
    import wikipedia
    import pywhatkit
    import webbrowser
    VOICE_DEPS_AVAILABLE = True
except Exception:
    VOICE_DEPS_AVAILABLE = False

app = Flask(__name__)
CORS(app)

# =========================
# CONFIG
# =========================
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SARVAM_URL = "https://api.sarvam.ai/text-to-speech"
MAX_CHARS = 2400  # Sarvam limit is close to 2500


# =========================
# HELPERS
# =========================
def split_text(text, limit=MAX_CHARS):
    parts = []
    while len(text) > limit:
        parts.append(text[:limit])
        text = text[limit:]
    parts.append(text)
    return parts


def load_history(question=""):
    history_text = ""
    raigad_text = ""

    try:
        with open("history.txt", "r", encoding="utf-8") as f:
            history_text = f.read()
    except Exception:
        print("history.txt not found")

    if "raigad" in question.lower():
        try:
            with open("raigad_data.txt", "r", encoding="utf-8") as f:
                raigad_text = f.read()
        except Exception:
            print("raigad_data.txt not found")

    if raigad_text:
        return history_text + "\n" + raigad_text
    return history_text


def ai_brain(question):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "Jarvis Assistant"
    }

    history_context = load_history(question)

    final_prompt = f"""
You are an AI historical storyteller.

Answer the user's question clearly and accurately.
Use the provided historical data only if it is relevant to the user's question.
Do not force connections to Raigad Fort or any other place unless the user explicitly asks about it.

Historical Data:
{history_context}

User Question:
{question}
"""

    data = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "user", "content": final_prompt}
        ]
    }

    try:
        response = requests.post(OPENROUTER_URL, headers=headers, json=data, timeout=30)
        result = response.json()

        if "choices" in result:
            return result["choices"][0]["message"]["content"]

        print("API Error:", result)
        return "Sorry boss, AI brain error."

    except Exception as e:
        print("AI Error:", e)
        return "Sorry boss, I cannot connect to the AI brain."


def generate_tts_audio(text):
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json"
    }

    parts = split_text(text)
    combined_audio = b""

    for part in parts:
        payload = {
            "text": part,
            "target_language_code": "hi-IN",
            "speaker": "anushka"
        }

        response = requests.post(SARVAM_URL, headers=headers, json=payload, timeout=60)
        data = response.json()

        if "audios" not in data:
            raise ValueError(f"Sarvam TTS error: {data}")

        audio_base64 = data["audios"][0]
        audio_bytes = base64.b64decode(audio_base64)
        combined_audio += audio_bytes

    return combined_audio


# =========================
# OPTIONAL LOCAL VOICE MODE
# =========================
def speak_local(text):
    if not VOICE_DEPS_AVAILABLE:
        print("Voice dependencies are not installed.")
        return

    print("Assistant:", text)
    engine = pyttsx3.init()
    engine.setProperty("rate", 170)
    engine.say(str(text))
    engine.runAndWait()


def take_command():
    if not VOICE_DEPS_AVAILABLE:
        return "none"

    listener = sr.Recognizer()
    with sr.Microphone() as source:
        print("Listening...")
        listener.pause_threshold = 1
        audio = listener.listen(source)

    try:
        print("Recognizing...")
        command = listener.recognize_google(audio)
        command = command.lower()
        print("You said:", command)
        return command
    except Exception:
        print("Say that again...")
        return "none"


def start_voice_assistant():
    if not VOICE_DEPS_AVAILABLE:
        print("Voice assistant dependencies are missing.")
        return

    speak_local("Hello boss, how can I help you")

    while True:
        command = take_command()

        if command == "none":
            continue

        if "time" in command:
            current_time = datetime.datetime.now().strftime("%I:%M %p")
            speak_local("The time is " + current_time)

        elif "who is" in command:
            person = command.replace("who is", "").strip()
            try:
                info = wikipedia.summary(person, 1)
                speak_local(info)
            except Exception:
                speak_local("Sorry boss, I could not find information.")

        elif "play" in command:
            song = command.replace("play", "").strip()
            speak_local("Playing " + song)
            pywhatkit.playonyt(song)

        elif "open google" in command:
            speak_local("Opening Google")
            webbrowser.open("https://google.com")

        elif "stop" in command or "exit" in command:
            speak_local("Goodbye boss")
            break

        else:
            answer = ai_brain(command)
            print("AI:", answer)
            speak_local(answer)


# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return "Historical AI + TTS Server Running"


@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()

    if not question:
        return jsonify({"error": "No question provided"}), 400

    answer = ai_brain(question)
    return jsonify({"answer": answer})


@app.route("/speak", methods=["POST"])
def speak_route():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        audio_bytes = generate_tts_audio(text)
        return send_file(
            io.BytesIO(audio_bytes),
            mimetype="audio/wav",
            as_attachment=False,
            download_name="speech.wav"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/ask-and-speak", methods=["POST"])
def ask_and_speak():
    data = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()

    if not question:
        return jsonify({"error": "No question provided"}), 400

    answer = ai_brain(question)
    return jsonify({"answer": answer})


@app.route("/start-voice", methods=["POST"])
def start_voice():
    if not VOICE_DEPS_AVAILABLE:
        return jsonify({
            "error": "Voice assistant dependencies are not installed. Install speech_recognition, pyttsx3, wikipedia, pywhatkit and pyaudio."
        }), 500

    thread = threading.Thread(target=start_voice_assistant, daemon=True)
    thread.start()
    return jsonify({"message": "Voice assistant started in background"})


# =========================
# MAIN
# =========================
import os

if __name__ == "__main__":
    print("Starting merged Historical AI Server...")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
