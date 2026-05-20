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


# -----------------------------
# Hilfslisten und Anonymisierung
# -----------------------------
COMMON_GERMAN_CITIES = [
    "Mainz", "Wiesbaden", "Frankfurt", "Köln", "Berlin", "Hamburg", "München",
    "Stuttgart", "Darmstadt", "Mannheim", "Heidelberg", "Bonn", "Leipzig",
    "Dresden", "Koblenz", "Trier", "Ingelheim", "Bad Kreuznach", "Ludwigshafen",
    "Bad Homburg", "Offenbach", "Kaiserslautern"
]

INSTITUTIONS = [
    "JGU",
    "Johannes Gutenberg-Universität",
    "Johannes Gutenberg Universität",
    "Universität Mainz",
    "Uni Mainz",
    "Universität",
    "Hochschule",
    "Schule",
    "Klinik",
    "Krankenhaus"
]

SAFE_CAPITALIZED_WORDS = {
    "Ich", "Heute", "Gestern", "Morgen", "Montag", "Dienstag", "Mittwoch",
    "Donnerstag", "Freitag", "Samstag", "Sonntag", "Januar", "Februar",
    "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
    "November", "Dezember", "Deutsch", "Deutschland", "Der", "Die", "Das"
}


def mask_capitalized_name_phrase(phrase):
    words = phrase.split()
    masked_words = []

    for w in words:
        cleaned = w.strip(",.!?:;")
        if cleaned in SAFE_CAPITALIZED_WORDS:
            masked_words.append(w)
        else:
            suffix = w[len(cleaned):] if len(w) > len(cleaned) else ""
            masked_words.append("[NAME]" + suffix)

    return " ".join(masked_words)


def anonymize_text(text):
    if not text:
        return text

    # Strukturierte Daten
    text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '[EMAIL]', text)
    text = re.sub(r'(\+?\d[\d\s\/\-\(\)]{6,}\d)', '[PHONE]', text)
    text = re.sub(r'https?://\S+|www\.\S+', '[URL]', text)
    text = re.sub(r'\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b', '[IBAN]', text)
    text = re.sub(r'\b\d{5}\b', '[PLZ]', text)
    text = re.sub(r'\b\d{1,2}\.\d{1,2}\.\d{2,4}\b', '[DATUM]', text)
    text = re.sub(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', '[DATUM]', text)
    text = re.sub(r'@[A-Za-z0-9_\.]+', '[USERNAME]', text)

    # Adressen
    text = re.sub(
        r'\b[A-ZÄÖÜ][a-zäöüß\-]+(?:straße|str\.|weg|allee|platz|gasse|ring|ufer)\s+\d+[a-zA-Z]?\b',
        '[ADRESSE]',
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r'\b(meine adresse ist|ich wohne in der|ich wohne in dem)\s+([^,.\n]+)',
        r'\1 [ADRESSE]',
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r'\b(ich wohne in|ich lebe in|ich komme aus|ich bin aus|mein wohnort ist)\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+(?:\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+){0,4})',
        r'\1 [ORT]',
        text,
        flags=re.IGNORECASE
    )

    # Alter / Geburtsangaben
    text = re.sub(
        r'\b(geboren am|mein geburtsdatum ist)\s+[^,.\n]+',
        r'\1 [DATUM]',
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r'\bich bin\s+\d{1,3}\s+jahre?\s+alt\b',
        'ich bin [ALTER] jahre alt',
        text,
        flags=re.IGNORECASE
    )

    # Explizite Namensangaben
    text = re.sub(
        r'\b(Ich heiße|Mein Name ist|Ich bin)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+){0,2})',
        r'\1 [NAME]',
        text
    )

    text = re.sub(
        r'\b(Herr|Frau|Dr\.|Prof\.)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+){0,2})',
        r'\1 [NAME]',
        text
    )

    text = re.sub(
        r'\b(mein Freund|meine Freundin|mein Mann|meine Frau|mein Bruder|meine Schwester|meine Mutter|mein Vater|mein Sohn|meine Tochter|mein Kollege|meine Kollegin)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+){0,2})',
        r'\1 [NAME]',
        text,
        flags=re.IGNORECASE
    )

    # Institutionen
    text = re.sub(
        r'\b(Ich arbeite bei|Ich arbeite an|Ich studiere an|Ich studiere bei|Ich bin an der|Ich bin bei)\s+([^,.\n]+)',
        r'\1 [INSTITUTION]',
        text,
        flags=re.IGNORECASE
    )

    # Feste Orte / Institutionen aus Listen
    for city in sorted(COMMON_GERMAN_CITIES, key=len, reverse=True):
        text = re.sub(rf'\b{re.escape(city)}\b', '[ORT]', text, flags=re.IGNORECASE)

    for inst in sorted(INSTITUTIONS, key=len, reverse=True):
        text = re.sub(rf'\b{re.escape(inst)}\b', '[INSTITUTION]', text, flags=re.IGNORECASE)

    # Namen nach typischen Kontexten
    context_patterns = [
        r'(\bmit)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)',
        r'(\bbei)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)',
        r'(\bvon)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)',
        r'(\bfür)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)',
        r'(\bzusammen mit)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)',
        r'(\bneben)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)',
        r'(\bgegenüber von)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)'
    ]

    for pattern in context_patterns:
        def repl(match):
            prefix = match.group(1)
            name_phrase = match.group(2)
            return f"{prefix} {mask_capitalized_name_phrase(name_phrase)}"
        text = re.sub(pattern, repl, text)

    # Verben + Name
    verb_patterns = [
        r'(\b(?:habe|hatte|treffe|traf|gesehen|sah|kenne|kannte|schrieb|schreibe|rief|rufe|kontaktierte|sprach mit|telefonierte mit|besuchte)\b)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)'
    ]

    for pattern in verb_patterns:
        def repl2(match):
            verb = match.group(1)
            name_phrase = match.group(2)
            return f"{verb} {mask_capitalized_name_phrase(name_phrase)}"
        text = re.sub(pattern, repl2, text, flags=re.IGNORECASE)

    # Weitere lockere Formulierungen
    text = re.sub(
        r'\b(war mit)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)',
        lambda m: f"{m.group(1)} {mask_capitalized_name_phrase(m.group(2))}",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r'\b(habe mich mit)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)',
        lambda m: f"{m.group(1)} {mask_capitalized_name_phrase(m.group(2))}",
        text,
        flags=re.IGNORECASE
    )

    return text



def ask_mistral(chat_history):
    messages = [
        {
            "role": "system",
            "content": (
                "Du bist ein freundlicher, aufmerksamer Gesprächspartner in einer wissenschaftlichen Studie. "
                "Deine Aufgabe ist es, mit der teilnehmenden Person ein kurzes Gespräch über ihren aktuellen Alltag zu führen. "

                "Ziel des Gesprächs: "
                "Die Person soll über mehrere verschiedene Bereiche ihres Alltags sprechen. "
                "Der Fokus liegt auf Breite, nicht auf Tiefe. "
                "Die Person soll verschiedene Themen kurz ansprechen, statt lange bei einem einzelnen persönlichen Thema zu bleiben. "

                "Gesprächsstil: "
                "Sei freundlich, wertschätzend und interessiert. "
                "Reagiere passend auf das, was die Person schreibt. "
                "Halte deine Antworten eher kurz. "
                "Stelle offene, einfache Anschlussfragen. "
                "Lenke das Gespräch auf unterschiedliche Alltagsbereiche. "
                "Bleibe bei alltagsnahen Themen. "
                "Vermeide Nachfragen, die stark emotional, intim oder sehr persönlich werden könnten. "
                "Vermeide therapeutische, interpretierende oder stark vertiefende Formulierungen. "
                "Gib keine Ratschläge, keine Diagnosen und keine Bewertungen. "
                "Teile keine eigenen Erfahrungen oder persönlichen Informationen. "

                "Wichtige Regel: "
                "Wenn die Person beginnt, sehr tief über Gefühle, Unsicherheiten, innere Konflikte oder sehr persönliche Erlebnisse zu sprechen, "
                "reagiere kurz verständnisvoll, aber lenke das Gespräch wieder behutsam auf einen anderen alltagsnahen Bereich. "
                "Gehe nicht intensiv auf emotionale Tiefe ein. "

                "Geeignete Themenbereiche sind: Tagesablauf, Studium, Arbeit oder andere Aufgaben, Freizeit und Hobbys, "
                "Routinen und Gewohnheiten, soziale Kontakte im Alltag, aktuelle Pläne für die nächsten Tage und allgemeine Interessen. "

                "Ein geeigneter Gesprächseinstieg ist: Wie sieht dein Alltag im Moment aus? "

                "Beispiele für passende Anschlussfragen sind: "
                "Was gehört sonst noch zu deinem Alltag? "
                "Wie sieht das in anderen Bereichen deines Tages aus? "
                "Was machst du aktuell in deiner Freizeit? "
                "Gibt es im Moment noch andere Dinge, die deinen Alltag prägen? "
                "Wie sieht es bei dir mit Studium, Arbeit oder anderen Aufgaben aus? "
                "Was steht in den nächsten Tagen bei dir an? "

                "Beispiele für passende Reaktionen sind: "
                "Das klingt nach einem ziemlich vollen Alltag. Welche anderen Dinge gehören gerade noch zu deinem Tagesablauf? "
                "Danke, das gibt schon einen guten Einblick. Was spielt im Moment sonst noch eine Rolle in deinem Alltag? "
                "Verstehe. Wie sieht es daneben mit Freizeit, Routinen oder anderen Themen aus? "

                "Wenn die Person sehr persönlich oder emotional wird, kannst du zum Beispiel so reagieren: "
                "Danke, dass du das teilst. Wenn du magst, können wir auch auf einen anderen Bereich deines Alltags schauen – zum Beispiel, was dich im Moment sonst beschäftigt. "
                "Das klingt wichtig. Gleichzeitig würde mich auch interessieren, wie dein Alltag in anderen Bereichen gerade aussieht. "

                "Antworte in einem natürlichen, warmen und einfachen Deutsch. "
                "Halte den Fokus immer auf einem breiten Überblick über den Alltag und mehreren Themenbereichen statt auf persönlicher Tiefe."
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


@app.route("/test_anonymization")
def test_anonymization():
    sample = (
        "Ich heiße Lisa Müller, wohne in Mainz, "
        "meine Adresse ist Musterstraße 12. "
        "Ich war mit Paul einkaufen und habe Anna getroffen. "
        "Mein Freund Max war auch dabei. "
        "Ich wohne in Bad Kreuznach. "
        "Meine E-Mail ist lisa@example.com, "
        "meine Telefonnummer ist 0171 1234567 "
        "und meine PLZ ist 55116."
    )

    return jsonify({
        "original": sample,
        "anonymized": anonymize_text(sample)
    })


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
