"""
initial Flask web interface for future development
"""

from flask import Flask, request, jsonify, render_template, send_from_directory  # type: ignore
from flask_cors import CORS  # type: ignore
import os
import sys
import json
import traceback
from datetime import datetime, timedelta

# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    load_dotenv()
    print("✅ Environment variables loaded from .env file")
except ImportError:
    print("⚠️  python-dotenv not available, using system environment variables")
except Exception as e:
    print(f"⚠️  Error loading .env file: {e}")

# Import the modified orii_demo functions
try:
    from orii_demo import process_query, get_logs_path

    ORII_DEMO_AVAILABLE = True
    print("✅ orii_demo module imported successfully")
except ImportError as e:
    print(f"⚠️  orii_demo not available: {e}")
    ORII_DEMO_AVAILABLE = False

    # Fallback functions
    def process_query(query, context):
        return "🚧 ORII Demo module not available. Please check deployment.", {}

    def get_logs_path():
        return "/tmp/fallback.log"


app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# **ENHANCED CONTEXT STORAGE** - Multiple backend support
try:
    from backend.app.utils.context_storage import create_context_storage

    # Configuration - you can change these
    CONTEXT_BACKEND = os.getenv(
        "CONTEXT_BACKEND", "file"
    )  # "file", "redis", "database"
    MAX_QUERIES_PER_SESSION = int(os.getenv("MAX_QUERIES_PER_SESSION", "10"))

    # Create context storage instance
    context_storage = create_context_storage(
        backend=CONTEXT_BACKEND, max_queries=MAX_QUERIES_PER_SESSION
    )

    print(
        f"✅ Context storage initialized: {CONTEXT_BACKEND} backend, max {MAX_QUERIES_PER_SESSION} queries per session"
    )
    ENHANCED_STORAGE_AVAILABLE = True

except ImportError as e:
    print(f"⚠️  Enhanced context storage not available, using basic storage: {e}")
    ENHANCED_STORAGE_AVAILABLE = False
    # Fallback to basic in-memory storage
    conversation_contexts = {}


def get_conversation_context(session_id: str) -> dict:
    """Get conversation context for a session"""
    if ENHANCED_STORAGE_AVAILABLE:
        try:
            context = context_storage.get_context(session_id)

            # Convert new format to legacy format for compatibility
            legacy_context = {
                "last_intent": context.get("last_intent"),
                "last_response": context.get("last_response"),
                "last_time_direction": None,  # Will be populated dynamically
                "last_search_type": None,  # Will be populated dynamically
                "last_events_found": [],  # Will be populated dynamically
                "chat_history": [],
            }

            # Convert queries to chat_history format
            for query_entry in context.get("queries", []):
                legacy_context["chat_history"].extend(
                    [
                        {"role": "user", "content": query_entry["query"]},
                        {"role": "assistant", "content": query_entry["response"]},
                    ]
                )

            return legacy_context

        except Exception as e:
            print(f"Error accessing enhanced storage: {e}")
            # Fallback to basic storage
            return conversation_contexts.get(
                session_id,
                {
                    "last_intent": None,
                    "last_response": None,
                    "last_time_direction": None,
                    "last_search_type": None,
                    "last_events_found": [],
                    "chat_history": [],
                },
            )
    else:
        # Basic in-memory storage
        if session_id not in conversation_contexts:
            conversation_contexts[session_id] = {
                "last_intent": None,
                "last_response": None,
                "last_time_direction": None,
                "last_search_type": None,
                "last_events_found": [],
                "chat_history": [],
            }
        return conversation_contexts[session_id]


def save_conversation_context(
    session_id: str, context: dict, query: str, response: str
):
    """Save conversation context for a session"""
    if ENHANCED_STORAGE_AVAILABLE:
        try:
            # Use the new storage system with query limiting
            context_storage.add_query_to_context(
                session_id=session_id,
                query=query,
                response=response,
                intent=context.get("last_intent"),
            )
        except Exception as e:
            print(f"Error saving to enhanced storage: {e}")
            # Fallback to basic storage
            conversation_contexts[session_id] = context
    else:
        # Basic in-memory storage
        conversation_contexts[session_id] = context


@app.route("/")
def index():
    """Render the main chat interface"""
    try:
        return render_template("index.html")
    except Exception as e:
        return f"""
        <h1>🚀 ORII Calendar Assistant</h1>
        <p>✅ Server is running successfully!</p>
        <p>⚠️ Template error: {str(e)}</p>
        <p>🔗 Try: <a href="/health">/health</a> | <a href="/install">/install</a></p>
        """


@app.route("/admin")
def admin():
    """Render the admin interface with logs access"""
    return render_template("admin.html")


@app.route("/install")
def install_page():
    """Render the extension installation page"""
    try:
        return render_template("install.html")
    except Exception as e:
        return f"""
        <h1>📥 ORII Extension Installation</h1>
        <p>⚠️ Template error: {str(e)}</p>
        <p>🔗 Try: <a href="/health">/health</a> | <a href="/">/</a></p>
        <p>📦 Extension files should be available at: <a href="/static/orii-extension-v1.0.0.crx">Download CRX</a></p>
        """


@app.route("/health")
def health_check():
    """Health check endpoint for Railway"""
    return jsonify(
        {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "orii_demo_available": ORII_DEMO_AVAILABLE,
            "enhanced_storage_available": ENHANCED_STORAGE_AVAILABLE,
            "context_backend": (
                CONTEXT_BACKEND if ENHANCED_STORAGE_AVAILABLE else "memory"
            ),
            "port": os.getenv("PORT", "8080"),
            "environment": "production" if not os.getenv("DEBUG") else "development",
        }
    )


@app.route("/api/query", methods=["POST"])
def api_query():
    """API endpoint to process a query with enhanced context storage"""
    data = request.json
    query = data.get("query", "")
    session_id = data.get("session_id", "default")

    # Get conversation context (from enhanced storage or memory)
    conversation_context = get_conversation_context(session_id)

    try:
        # Process the query using our modified function
        response, updated_context = process_query(query, conversation_context)

        # Save the updated conversation context with the new system
        save_conversation_context(session_id, updated_context, query, response)

        return jsonify(
            {
                "status": "success",
                "response": response,
                "timestamp": datetime.now().isoformat(),
                "context_info": {
                    "backend": (
                        CONTEXT_BACKEND if ENHANCED_STORAGE_AVAILABLE else "memory"
                    ),
                    "max_queries": (
                        MAX_QUERIES_PER_SESSION
                        if ENHANCED_STORAGE_AVAILABLE
                        else "unlimited"
                    ),
                },
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


@app.route("/api/context/<session_id>", methods=["GET"])
def get_context_info(session_id: str):
    """API endpoint to get context information for debugging"""
    if ENHANCED_STORAGE_AVAILABLE:
        try:
            context = context_storage.get_context(session_id)
            summary = context_storage.get_recent_context_summary(session_id, last_n=3)

            return jsonify(
                {
                    "status": "success",
                    "session_id": session_id,
                    "backend": CONTEXT_BACKEND,
                    "query_count": len(context.get("queries", [])),
                    "max_queries": MAX_QUERIES_PER_SESSION,
                    "last_updated": context.get("updated_at"),
                    "recent_summary": summary,
                }
            )
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 500
    else:
        context = conversation_contexts.get(session_id, {})
        return jsonify(
            {
                "status": "success",
                "session_id": session_id,
                "backend": "memory",
                "query_count": len(context.get("chat_history", []))
                // 2,  # Divide by 2 since it's user+assistant pairs
                "max_queries": "unlimited",
            }
        )


@app.route("/api/cleanup", methods=["POST"])
def cleanup_old_contexts():
    """API endpoint to manually trigger context cleanup"""
    if ENHANCED_STORAGE_AVAILABLE:
        try:
            cleaned_count = context_storage.cleanup_old_contexts()
            return jsonify(
                {
                    "status": "success",
                    "cleaned_contexts": cleaned_count,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 500
    else:
        # For in-memory storage, clear old sessions (simple cleanup)
        now = datetime.now()
        cleaned = 0
        sessions_to_remove = []

        for session_id, context in conversation_contexts.items():
            # Remove sessions with no activity (this is basic)
            if not context.get("chat_history"):
                sessions_to_remove.append(session_id)

        for session_id in sessions_to_remove:
            del conversation_contexts[session_id]
            cleaned += 1

        return jsonify(
            {
                "status": "success",
                "cleaned_contexts": cleaned,
                "timestamp": datetime.now().isoformat(),
            }
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

    print(f"🚀 Starting ORII Calendar Assistant")
    print(
        f"📊 Context Backend: {CONTEXT_BACKEND if ENHANCED_STORAGE_AVAILABLE else 'memory'}"
    )
    print(
        f"🔢 Max Queries per Session: {MAX_QUERIES_PER_SESSION if ENHANCED_STORAGE_AVAILABLE else 'unlimited'}"
    )

    # Railway deployment configuration
    port = int(os.getenv("PORT", 8080))  # Railway typically uses 8080
    host = "0.0.0.0"  # Bind to all interfaces for Railway

    print(f"🌐 Server starting on {host}:{port}")
    print(f"🚀 ORII Calendar Assistant ready!")
    app.run(debug=False, host=host, port=port, threaded=True)
