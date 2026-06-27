import os
import uuid
import sqlite3
import json
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from groq import Groq

# Load environment configurations
load_dotenv()

app = Flask(__name__)
DB_FILE = "provenance_guard.db"

# Initialize Groq Client
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("CRITICAL: GROQ_API_KEY environment variable is missing.")
groq_client = Groq(api_key=GROQ_API_KEY)

def init_db():
    """Initializes the structured SQLite database for logging and lifecycle status."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                content_id TEXT PRIMARY KEY,
                creator_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                text_preview TEXT NOT NULL,
                attribution TEXT NOT NULL,
                confidence REAL NOT NULL,
                llm_score REAL,
                heur_score REAL,
                status TEXT NOT NULL,
                appeal_reasoning TEXT
            )
        """)
        conn.commit()

# Ensure the database layer exists on boot
init_db()

def get_llm_score(text: str) -> float:
    """
    Evaluates semantic properties of text using Groq to estimate P(AI).
    Returns a float between 0.0 (Pure Human) and 1.0 (Pure AI).
    """
    try:
        system_prompt = (
            "You are an expert content forensics system specializing in identifying AI-generated text.\n"
            "Analyze the text submitted by the user. Evaluate its semantic rhythm, usage of common AI "
            "clichés, transition words, and linguistic uniformity.\n"
            "You MUST respond with a valid JSON object containing exactly one key: 'ai_probability'.\n"
            "The value must be a floating-point number between 0.0 (definitively human) and 1.0 (definitively AI).\n"
            "Do not include any introductory or explanatory text outside of the raw JSON object."
        )

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Analyze this text:\n\n{text}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.1 # Keep variance low for consistent classification profiles
        )

        raw_content = response.choices[0].message.content
        result_json = json.loads(raw_content)
        
        # Guard against key deviations or bad ranges
        score = float(result_json.get("ai_probability", 0.5))
        return max(0.0, min(1.0, score))
    except Exception as e:
        print(f"Error executing Groq API classification: {e}")
        return 0.5  # Neutral fallback uncertainty score if API is unreachable

@app.route("/submit", methods=["POST"])
def submit():
    """
    Accepts text submissions and coordinates the multi-signal pipeline.
    Expects JSON payload with 'text' and 'creator_id'.
    """
    data = request.get_json() or {}
    text = data.get("text")
    creator_id = data.get("creator_id")

    if not text or not creator_id:
        return jsonify({"error": "Missing required fields: text and creator_id"}), 400

    content_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat() + "Z"

    # Execute Signal 1: Semantic Evaluation
    llm_score = get_llm_score(text)

    # For Milestone 3, our aggregate score and classification will temporarily reflect just Signal 1
    # We will incorporate Signal 2 and your exact thresholds in Milestone 4.
    temp_attribution = "likely_ai" if llm_score > 0.5 else "likely_human"
    temp_label = f"Temporary Label — Score: {llm_score:.2f}."

    # Commit entry to structured audit log
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audit_log 
            (content_id, creator_id, timestamp, text_preview, attribution, confidence, llm_score, heur_score, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (content_id, creator_id, timestamp, text[:50], temp_attribution, llm_score, llm_score, 0.0, "classified"))
        conn.commit()

    return jsonify({
        "content_id": content_id,
        "attribution": temp_attribution,
        "confidence": round(llm_score, 4),
        "label": temp_label
    }), 200

@app.route("/log", methods=["GET"])
def get_log():
    """Returns all recorded attribution decisions for grading and monitoring visibility."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_log ORDER BY timestamp DESC")
        rows = cursor.fetchall()
        
    entries = [dict(row) for row in rows]
    return jsonify({"entries": entries}), 200

if __name__ == "__main__":
    app.run(debug=True, port=5000)