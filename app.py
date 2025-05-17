from flask import Flask, request, jsonify, render_template, send_from_directory
import os
import sys
import json
import traceback
from datetime import datetime

# Import the modified orii_demo functions
from orii_demo import process_query, get_logs_path

app = Flask(__name__)

# Dictionary to store conversation contexts by session ID
conversation_contexts = {}


@app.route("/")
def index():
    """Render the main chat interface"""
    return render_template("index.html")


@app.route("/admin")
def admin():
    """Render the admin interface with logs access"""
    return render_template("admin.html")


@app.route("/api/query", methods=["POST"])
def api_query():
    """API endpoint to process a query"""
    data = request.json
    query = data.get("query", "")
    session_id = data.get("session_id", "default")

    # Get or create conversation context for this session
    if session_id not in conversation_contexts:
        conversation_contexts[session_id] = {
            "last_intent": None,
            "last_response": None,
            "last_time_info": None,
            "last_date": None,
            "chat_history": [],
        }

    try:
        # Process the query using our modified function
        response, updated_context = process_query(
            query, conversation_contexts[session_id]
        )

        # Update the conversation context
        conversation_contexts[session_id] = updated_context

        return jsonify(
            {
                "status": "success",
                "response": response,
                "timestamp": datetime.now().isoformat(),
            }
        )
    except Exception as e:
        traceback.print_exc()
        return (
            jsonify(
                {
                    "status": "error",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            ),
            500,
        )


@app.route("/api/logs")
def get_logs():
    """API endpoint to get logs (admin only)"""
    log_path = get_logs_path()
    try:
        with open(log_path, "r") as f:
            logs = f.readlines()
        return jsonify(
            {"status": "success", "logs": logs, "timestamp": datetime.now().isoformat()}
        )
    except Exception as e:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            ),
            500,
        )


@app.route("/api/clear_logs")
def clear_logs():
    """API endpoint to clear logs (admin only)"""
    log_path = get_logs_path()
    try:
        with open(log_path, "w") as f:
            f.write(f"Logs cleared at {datetime.now().isoformat()}\n")
        return jsonify(
            {
                "status": "success",
                "message": "Logs cleared",
                "timestamp": datetime.now().isoformat(),
            }
        )
    except Exception as e:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            ),
            500,
        )


if __name__ == "__main__":
    # Create templates directory if it doesn't exist
    os.makedirs("templates", exist_ok=True)

    # Create static directory if it doesn't exist
    os.makedirs("static", exist_ok=True)

    app.run(debug=True, port=5000)
