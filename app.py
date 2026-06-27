import os
import uuid
import sqlite3
import json
import re
from datetime import datetime
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from groq import Groq

# Load environment configurations
load_dotenv()

app = Flask(__name__)
DB_FILE = "provenance_guard.db"

# Initialize Production Rate Limiter with memory storage URI
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://"
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("CRITICAL: GROQ_API_KEY environment variable is missing.")
groq_client = Groq(api_key=GROQ_API_KEY)

def init_db():
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

init_db()

def get_llm_score(text: str) -> float:
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
            temperature=0.1
        )

        raw_content = response.choices[0].message.content
        result_json = json.loads(raw_content)
        score = float(result_json.get("ai_probability", 0.5))
        return max(0.0, min(1.0, score))
    except Exception as e:
        print(f"Error executing Groq API classification: {e}")
        return 0.5

def calculate_stylometric_score(text: str) -> float:
    tokens = re.findall(r'\b\w+\b', text.lower())
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    
    if not tokens or not sentences:
        return 0.5

    ttr = len(set(tokens)) / len(tokens)
    sentence_lengths = [len(re.findall(r'\b\w+\b', s)) for s in sentences]
    num_sentences = len(sentence_lengths)
    
    if num_sentences > 1:
        mean_len = sum(sentence_lengths) / num_sentences
        variance = sum((x - mean_len) ** 2 for x in sentence_lengths) / num_sentences
    else:
        variance = 0.0
    
    heur_variance_score = max(0.0, min(1.0, 1.0 - (variance / 50.0)))
    
    if 0.45 <= ttr <= 0.70:
        heur_ttr_score = 0.8
    else:
        heur_ttr_score = 0.2

    return (heur_variance_score + heur_ttr_score) / 2.0

@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute")
def submit():
    data = request.get_json() or {}
    text = data.get("text")
    creator_id = data.get("creator_id")

    if not text or not creator_id:
        return jsonify({"error": "Missing required fields: text and creator_id"}), 400

    content_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat() + "Z"

    llm_score = get_llm_score(text)
    heur_score = calculate_stylometric_score(text)
    combined_score = (0.65 * llm_score) + (0.35 * heur_score)

    # User-facing production labels mapped exactly to spec criteria
    if combined_score < 0.40:
        attribution = "likely_human"
        label = "Verified Human Attribution — This content aligns consistently with human writing patterns and structural variance."
    elif combined_score <= 0.75:
        attribution = "uncertain"
        label = "Attribution Unverifiable — This text contains a mixture of stylistic markers. Content context cannot be definitively automated."
    else:
        attribution = "likely_ai"
        label = "Automated Content Label — Our systems indicate a high probability that this text was generated using an AI model."

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audit_log 
            (content_id, creator_id, timestamp, text_preview, attribution, confidence, llm_score, heur_score, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (content_id, creator_id, timestamp, text[:50], attribution, combined_score, llm_score, heur_score, "classified"))
        conn.commit()

    return jsonify({
        "content_id": content_id,
        "attribution": attribution,
        "confidence": round(combined_score, 4),
        "label": label
    }), 200

@app.route("/appeal", methods=["POST"])
def appeal():
    data = request.get_json() or {}
    content_id = data.get("content_id")
    creator_reasoning = data.get("creator_reasoning")

    if not content_id or not creator_reasoning:
        return jsonify({"error": "Missing required fields: content_id and creator_reasoning"}), 400

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM audit_log WHERE content_id = ?", (content_id,))
        row = cursor.fetchone()
        
        if not row:
            return jsonify({"error": f"Submission context not found for ID: {content_id}"}), 404
            
        cursor.execute("""
            UPDATE audit_log 
            SET status = 'under_review', appeal_reasoning = ? 
            WHERE content_id = ?
        """, (creator_reasoning, content_id))
        conn.commit()

    return jsonify({
        "content_id": content_id,
        "status": "under_review",
        "message": "Appeal successfully registered. Your content attribution status is currently under internal review."
    }), 200

@app.route("/log", methods=["GET"])
def get_log():
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_log ORDER BY timestamp DESC")
        rows = cursor.fetchall()
        
    entries = [dict(row) for row in rows]
    return jsonify({"entries": entries}), 200

if __name__ == "__main__":
    app.run(debug=True, port=5000)