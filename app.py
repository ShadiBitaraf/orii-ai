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

except Exception as e:
    print(f"⚠️  Error importing orii_demo: {e}")
    ORII_DEMO_AVAILABLE = False

    # Fallback functions
    def process_query(query, context):
        return f"🚧 ORII Demo error: {str(e)}", {}

    def get_logs_path():
        return "/tmp/fallback.log"


app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# **ENHANCED CONTEXT STORAGE** - Multiple backend support
try:
    from backend.app.utils.context_storage import create_context_storage

    # Configuration - you can change these
    CONTEXT_BACKEND = os.getenv(
        "CONTEXT_BACKEND", "redis"  # Default to redis since it's available on Railway
    )  # "file", "redis", "database"
    MAX_QUERIES_PER_SESSION = int(os.getenv("MAX_QUERIES_PER_SESSION", "10"))

    print(f"🔍 DEBUG: Attempting to initialize {CONTEXT_BACKEND} backend...")

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
    CONTEXT_BACKEND = "memory"
    # Fallback to basic in-memory storage
    conversation_contexts = {}
except Exception as e:
    print(f"⚠️  Error initializing {CONTEXT_BACKEND} storage, using basic storage: {e}")
    ENHANCED_STORAGE_AVAILABLE = False
    CONTEXT_BACKEND = "memory"
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


@app.route("/health")
def health_check():
    """Health check endpoint for Railway"""
    # Check file system
    templates_exist = os.path.exists("templates")
    static_exist = os.path.exists("static")
    install_template_exist = os.path.exists("templates/install.html")

    files_info = {
        "templates_dir": templates_exist,
        "static_dir": static_exist,
        "install_template": install_template_exist,
    }

    if templates_exist:
        try:
            files_info["template_files"] = os.listdir("templates")
        except:
            files_info["template_files"] = "error_reading"

    if static_exist:
        try:
            files_info["static_files"] = os.listdir("static")
        except:
            files_info["static_files"] = "error_reading"

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
            "files": files_info,
        }
    )


# Debug checkpoint - this should print during startup
print("🔍 DEBUG: About to register install routes...")
print(f"🔍 DEBUG: ENHANCED_STORAGE_AVAILABLE = {ENHANCED_STORAGE_AVAILABLE}")
print(f"🔍 DEBUG: ORII_DEMO_AVAILABLE = {ORII_DEMO_AVAILABLE}")
print(f"🔍 DEBUG: CONTEXT_BACKEND = {CONTEXT_BACKEND}")

try:

    @app.route("/install")
    def install_page():
        """Professional extension installation page for end users"""
        return """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Install ORII Calendar Assistant</title>
            <style>
                body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; background: #f5f5f5; }
                .container { background: white; padding: 40px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                h1 { color: #1a73e8; text-align: center; margin-bottom: 10px; }
                .subtitle { text-align: center; color: #666; margin-bottom: 30px; font-size: 18px; }
                .step { background: #f8f9fa; padding: 20px; margin: 20px 0; border-radius: 8px; border-left: 4px solid #1a73e8; }
                .step h3 { margin-top: 0; color: #1a73e8; }
                .download-btn { display: inline-block; background: #1a73e8; color: white; padding: 15px 30px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 20px 0; text-align: center; }
                .download-btn:hover { background: #1557b0; }
                .warning { background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 6px; margin: 20px 0; }
                .success { background: #d4edda; border: 1px solid #c3e6cb; padding: 15px; border-radius: 6px; margin: 20px 0; }
                code { background: #f1f3f4; padding: 2px 6px; border-radius: 3px; font-family: monospace; }
                .feature { display: flex; align-items: center; margin: 10px 0; }
                .feature::before { content: "✨"; margin-right: 10px; font-size: 18px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🗓️ ORII Calendar Assistant</h1>
                <p class="subtitle">AI-powered calendar management directly in Google Calendar</p>
                
                <div class="success">
                    <strong>🎉 Ready to install!</strong> ORII will add an AI assistant to your Google Calendar sidebar.
                </div>

                <h2>✨ What ORII Does</h2>
                <div class="feature">Ask natural language questions like "What do I have tomorrow?"</div>
                <div class="feature">Find events semantically: "When was my last dentist appointment?"</div>
                <div class="feature">Create events easily: "Schedule lunch with John tomorrow at noon"</div>
                <div class="feature">Smart search across all your calendars</div>
                <div class="feature">Remembers conversation context for follow-up questions</div>

                <h2>📋 Installation Steps</h2>
                
                <div class="step">
                    <h3>Step 1: Download the Extension</h3>
                    <p>Click the button below to download the ORII extension file to your computer.</p>
                    <a href="/static/orii-extension-v1.0.0.crx" class="download-btn" download>📥 Download ORII Extension</a>
                </div>

                <div class="step">
                    <h3>Step 2: Open Chrome Extensions</h3>
                    <p>In Google Chrome, go to:</p>
                    <p><code>chrome://extensions/</code></p>
                    <p>Or click the three dots menu → More tools → Extensions</p>
                </div>

                <div class="step">
                    <h3>Step 3: Enable Developer Mode</h3>
                    <p>Toggle the <strong>"Developer mode"</strong> switch in the top-right corner of the Extensions page.</p>
                </div>

                <div class="step">
                    <h3>Step 4: Install the Extension</h3>
                    <p>Drag and drop the downloaded <code>orii-extension-v1.0.0.crx</code> file onto the Extensions page.</p>
                    <p><em>Alternative:</em> Click "Load unpacked" and select the extension file.</p>
                </div>

                <div class="step">
                    <h3>Step 5: Start Using ORII</h3>
                    <p>1. Go to <strong>calendar.google.com</strong></p>
                    <p>2. Look for the <strong>ORII</strong> button in the right sidebar</p>
                    <p>3. Click it to open the AI chat interface</p>
                    <p>4. Start asking questions about your calendar!</p>
                </div>

                <div class="warning">
                    <strong>⚠️ First Time Setup:</strong> ORII will ask for Google Calendar permissions when you first use it. This allows the AI to read and create events in your calendar.
                </div>

                <h2>💬 Example Questions to Try</h2>
                <ul>
                    <li>"What's on my calendar today?"</li>
                    <li>"Do I have any meetings tomorrow?"</li>
                    <li>"When is my next appointment with Dr. Smith?"</li>
                    <li>"Schedule a team meeting Friday at 2pm"</li>
                    <li>"Show me all my events this week"</li>
                    <li>"Find my last therapy session"</li>
                </ul>

                <h2>🆘 Need Help?</h2>
                <p>If you encounter any issues:</p>
                <ul>
                    <li>Make sure you're using Google Chrome browser</li>
                    <li>Ensure Developer mode is enabled in Extensions</li>
                    <li>Try refreshing calendar.google.com after installation</li>
                    <li>Check that the extension appears in your Chrome extensions list</li>
                </ul>

                <div class="success">
                    <strong>🚀 You're all set!</strong> ORII will make managing your calendar as easy as having a conversation.
                </div>
            </div>
        </body>
        </html>
        """

    @app.route("/install2")
    def install_test():
        """Test route to check if routing works"""
        return "<h1>✅ Install2 route works!</h1><p><a href='/health'>Health</a> | <a href='/install'>Install</a></p>"

    @app.route("/working")
    def working_test():
        """Test route to check if Railway is running latest code"""
        return f"""
        <h1>✅ NEW ROUTE WORKING! - {datetime.now().isoformat()}</h1>
        <p>🚀 This route was just added - if you see this, Railway is running the latest code!</p>
        <p>🔗 <a href="/health">Health</a> | <a href="/install">Install</a> | <a href="/install2">Install2</a></p>
        <p>📊 Backend: {CONTEXT_BACKEND} | Enhanced Storage: {ENHANCED_STORAGE_AVAILABLE}</p>
        """

    print("✅ DEBUG: Install routes registered successfully!")

except Exception as e:
    print(f"❌ DEBUG: Error registering install routes: {e}")
    import traceback

    traceback.print_exc()

    # Create fallback routes to ensure something works
    @app.route("/install")
    def install_page():
        return f"<h1>⚠️ Install route (fallback mode)</h1><p>Error: {str(e)}</p><p><a href='/health'>Health</a></p>"

    @app.route("/working")
    def working_test():
        return f"<h1>⚠️ Working route (fallback mode)</h1><p>Error: {str(e)}</p><p><a href='/health'>Health</a></p>"


print("🔍 DEBUG: Moving to other route registrations...")


@app.route("/debug/routes")
def debug_routes():
    """Debug endpoint to show all registered routes"""
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append(
            {
                "endpoint": rule.endpoint,
                "methods": list(rule.methods),
                "rule": str(rule),
            }
        )
    return jsonify({"status": "debug", "total_routes": len(routes), "routes": routes})


@app.route("/test")
def test_route():
    """Simple test route that doesn't need templates"""
    return "<h1>✅ Test route works!</h1><p><a href='/health'>Health</a> | <a href='/routes'>Routes</a> | <a href='/install'>Install</a></p>"


@app.route("/routes")
def simple_debug_routes():
    """Simple debug endpoint to show all registered routes"""
    try:
        routes = []
        for rule in app.url_map.iter_rules():
            routes.append(f"{rule.methods} {rule.rule} -> {rule.endpoint}")

        html = "<h1>🔍 Registered Routes</h1><ul>"
        for route in routes:
            html += f"<li>{route}</li>"
        html += "</ul>"
        html += "<p><a href='/health'>Health</a> | <a href='/test'>Test</a></p>"
        return html
    except Exception as e:
        return f"<h1>❌ Error listing routes</h1><p>{str(e)}</p>"


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
