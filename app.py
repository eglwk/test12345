from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import requests
import os
import re

load_dotenv()

app = Flask(__name__)

# -----------------------------
# API / externe Dienste
# -----------------------------
LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip()
LLM_MODEL = os.environ.get("LLM_MODEL", "GPT OSS 120B").strip()
LLM_API_URL = os.environ.get(
    "LLM_API_URL",
    "https://ki-chat.uni-mainz.de/api/chat/completions"
).strip()


def ask_mistral(chat_history):
    messages = [
        {
            "role": "system",
            "content": (
                "Du bist Chatti, ein freundlicher, zugewandter Chatbot. "
                "Antworte klar, warm und nicht zu lang. "
                "Wenn die Person etwas Persönliches schreibt, reagiere empathisch, aber nicht übertrieben. "
                "Schreibe auf Deutsch."
            )
        }
    ]

    for msg in chat_history[-10:]:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": LLM_MODEL,
        "messages": messages
    }

    response = requests.post(
        LLM_API_URL,
        headers=headers,
        json=data,
        timeout=60
    )

    if response.status_code != 200:
        raise Exception(f"LLM-Fehler: {response.status_code} {response.text}")

    result = response.json()
    return result["choices"][0]["message"]["content"]

# -----------------------------
# Routen
# -----------------------------

@app.route("/")
def home():
    return render_template("index1.html")


@app.route("/load_chat", methods=["GET"])
def load_chat():
    # Es wird bewusst nichts geladen, weil keine Chatverläufe gespeichert werden.
    return jsonify({"chat_history": []})


@app.route("/send", methods=["POST"])
def send():
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()
    browser_history = data.get("chat_history", [])

    if not user_message:
        return jsonify({"error": "Leere Nachricht"}), 400

    try:
        # Verlauf nur aus dem aktuellen Browserzustand nutzen, nicht speichern.
        model_history = []
        if isinstance(browser_history, list):
            for msg in browser_history[-10:]:
                if (
                    isinstance(msg, dict)
                    and msg.get("role") in {"user", "assistant"}
                    and isinstance(msg.get("content"), str)
                ):
                    model_history.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })

        model_history.append({
            "role": "user",
            "content": user_message
        })

        reply = ask_mistral(model_history)

        # Keine Speicherung: weder lokal, noch Datenbank, noch Seafile.
        return jsonify({"reply": reply})
    except Exception as e:
        print("Fehler:", repr(e))
        return jsonify({"error": str(e)}), 500


@app.route("/healthz")
def healthz():
    return "ok", 200


@app.route("/test_models")
def test_models():
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}"
    }

    response = requests.get(
        "https://ki-chat.uni-mainz.de/api/models",
        headers=headers,
        timeout=30
    )

    try:
        data = response.json()
    except Exception:
        data = response.text

    return jsonify({
        "status_code": response.status_code,
        "data": data
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
