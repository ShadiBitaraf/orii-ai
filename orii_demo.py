#!/usr/bin/env python3
"""
ORII Calendar Assistant Demo
----------------------------
This file demonstrates the ORII calendar assistant by providing a chat interface
that connects all functionality from the repository.
"""

import os
import sys
import signal
from datetime import datetime
import json
from termcolor import colored
import time
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML
import traceback

# from dateutil import parser
from datetime import timedelta


# Fix for BrokenPipeError
# When Python tries to flush its buffer on interpreter shutdown, it can cause
# a BrokenPipeError if stdout or stderr is already closed.
# This fix ensures these errors are properly handled.
def _handle_broken_pipe(exc_type, exc_value, exc_traceback):
    """Handle BrokenPipeError by simply suppressing it."""
    if exc_type == BrokenPipeError:
        # Silently close the stdout/stderr if a BrokenPipeError occurred
        for fd in (sys.stdout, sys.stderr):
            try:
                fd.close()
            except:
                pass
        return True  # Suppress the exception

    # For all other exceptions, use the default excepthook
    return sys.__excepthook__(exc_type, exc_value, exc_traceback)


# Install our custom exception handler
sys.excepthook = _handle_broken_pipe

# Handle SIGPIPE gracefully (prevents broken pipe errors)
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

# Add both the current directory and the backend directory to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Create logs directory if it doesn't exist
logs_dir = os.path.join(current_dir, "app", "logs")
os.makedirs(logs_dir, exist_ok=True)
log_file = os.path.join(logs_dir, "orii_demo.log")

# Import the Loguru logger
try:
    from backend.app.utils.logger import get_logger

    # Create a logger specific to this module with no console output
    logger = get_logger(name="orii_demo", module="orii_demo")
    logger.info("Starting ORII Calendar Assistant")
except ImportError as e:
    # Fallback to basic configuration if our advanced logger is not available
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        filename=log_file,
        filemode="a",
    )
    logger = logging.getLogger("orii_demo")
    logger.error(f"Could not import logger module: {e}")

    # Define a get_logger function to maintain compatibility
    def get_logger(name=None, module=None):
        return logging.getLogger(name or "orii_demo")


# Import LLM client
try:
    from backend.app.utils.llm_client import get_llm_client
except ImportError as e:
    logger.error(
        "Could not import LLM client. Conversational responses may be limited."
    )
    get_llm_client = None

# Define the models we need to import
required_modules = {
    "intent_detection": "backend.app.cli.intent_detection",
    "intent_processor": "backend.app.cli.intent_processor",
    "time_manager": "backend.app.cli.time_manager",
    "smart_date_parser": "backend.app.utils.smart_date_parser",
}

# Import required modules with fallbacks
modules = {}
for module_name, module_path in required_modules.items():
    try:
        modules[module_name] = __import__(module_path, fromlist=["*"])
        logger.info(f"Successfully imported {module_path}")
    except ImportError as e:
        error_str = (
            f"Failed to import {module_path}: {str(e)}\n{traceback.format_exc()}"
        )
        logger.error(f"Failed to import {module_path}: {str(e)}")
        logger.error(traceback.format_exc())
        # Comment out console output for UI version
        # print(
        #     colored(
        #         f"Error importing {module_path}. The demo may not function correctly.",
        #         "red",
        #     )
        # )
        modules[module_name] = None

# Extract the functions we need
determine_query_intent = getattr(
    modules["intent_detection"], "determine_query_intent", None
)
process_intent = getattr(modules["intent_processor"], "process_intent", None)
format_datetime_range = getattr(modules["time_manager"], "format_datetime_range", None)
parse_natural_language_datetime = getattr(
    modules["time_manager"], "parse_natural_language_datetime", None
)
get_smart_date_parser = getattr(
    modules["smart_date_parser"], "get_smart_date_parser", None
)

# Create a styled prompt session
style = Style.from_dict(
    {
        "prompt": "bold #0000FF",  # Bold blue
    }
)

# Store conversation history
conversation_history = []


def safe_print(*args, **kwargs):
    """Print function that safely handles BrokenPipeError."""
    try:
        print(*args, **kwargs)
    except BrokenPipeError:
        # Our custom excepthook will handle this
        raise


def print_welcome():
    """Print welcome message"""
    safe_print("\n" + "=" * 80)
    safe_print(colored("🗓️  ORII Calendar Assistant Demo", "cyan", attrs=["bold"]))
    safe_print("=" * 80)
    safe_print(colored("Ask me anything about your calendar or scheduling!", "green"))
    safe_print("Examples:")
    safe_print("  - What's on my calendar today?")
    safe_print("  - Schedule a meeting with John tomorrow at 2pm")
    safe_print("  - When was my last dentist appointment?")
    safe_print("  - Show me my meetings for next week")
    safe_print("  - What's happening this weekend?")
    safe_print("Type 'exit' or 'quit' to end the conversation.")
    safe_print("=" * 80 + "\n")


def format_chatbot_response(response):
    """Format the response for display"""
    if isinstance(response, dict):
        if "status" in response and response["status"] == "error":
            return f"Error: {response.get('message', 'Unknown error')}"

        if "message" in response:
            result = [response["message"]]

            # Format events if present
            if "events" in response and response["events"]:
                # Filter out None values that might be in the events list
                filtered_events = [
                    event for event in response["events"] if event is not None
                ]

                # If we have no events after filtering, don't try to format them
                if not filtered_events:
                    return "\n".join(result)

                # Get the LLM to create a conversational summary
                try:
                    llm_client = get_llm_client()
                    events_text = "\n".join([f"- {event}" for event in filtered_events])

                    # Add context about whether this was a specific date query
                    context_instructions = ""

                    if response.get("specific_date_query", False):
                        context_instructions = "The user asked about a specific date, so make sure to ONLY include events for that exact date in your response."

                    if response.get("is_occurrence_query", False):
                        if response.get("search_terms"):
                            context_instructions = (
                                "The user asked about occurrences of specific events. "
                                f"They were searching for '{response.get('search_terms')}'. "
                                "Phrase your response as finding occurrences of this type of event, "
                                "rather than just listing events on specific dates."
                            )

                    prompt = f"""
                    I need to present the following calendar events to a user in a conversational, helpful way.
                    Make it sound natural and friendly, but be concise.
                    
                    {context_instructions}
                    
                    Date: {response.get("date", "Unknown date")}
                    Days range: {response.get("days_range", 0)}
                    
                    Events:
                    {events_text}
                    
                    Give a friendly response listing these events in a clear, organized way.
                    If there's a specific date mentioned, focus only on events for that exact date.
                    If this is a "last occurrence" query, mention when the last occurrence was.
                    If this is a "next occurrence" query, mention when the next occurrence is.
                    Limit your response to 3-4 sentences maximum.
                    """

                    logger.debug(f"LLM prompt for conversation summary: {prompt}")
                    conversational_summary = llm_client.get_completion(prompt)
                    logger.debug(f"LLM summary response: {conversational_summary}")
                    result = [conversational_summary]
                except Exception as e:
                    logger.error(f"Error generating conversational response: {e}")
                    logger.exception("Exception details:")
                    # Fallback to regular format
                    result.append("\nHere are the events I found:")
                    for i, event in enumerate(filtered_events, 1):
                        result.append(f"\n{i}. {event}")

            return "\n".join(result)

        # If it's a dict but doesn't have standard fields, pretty print it
        return json.dumps(response, indent=2)

    # If it's a string or other type, just return it
    return str(response)


def get_intent_response(query, conversation_context=None):
    """Process the query and get a response"""
    try:
        logger.info(f"Processing query: {query}")

        # Check if we have the required functions
        if not determine_query_intent or not process_intent:
            logger.error("Required functions not loaded properly")
            return {
                "status": "error",
                "message": "The necessary modules couldn't be loaded. Please check your installation.",
            }

        # Check if this is a follow-up question
        is_follow_up = False
        follow_up_indicators = ["how about", "what about", "and", "how many", "which"]

        if conversation_context and any(
            query.lower().startswith(indicator) for indicator in follow_up_indicators
        ):
            is_follow_up = True
            logger.debug(f"Detected follow-up question: {query}")

            # If the previous question was about a date/time
            if conversation_context.get("last_intent") == "time_date":
                # If the current query is something like "how about tomorrow"
                if any(
                    term in query.lower()
                    for term in ["tomorrow", "next day", "day after"]
                ):
                    # Prepare a modified query that includes the full context
                    from datetime import datetime, timedelta

                    # Parse the date from the last response
                    try:
                        # Calculate tomorrow's date
                        current_date = datetime.now()
                        tomorrow = current_date + timedelta(days=1)
                        logger.info(
                            f"Expanding follow-up query to use tomorrow's date: {tomorrow.strftime('%Y-%m-%d')}"
                        )

                        # Create a query that asks for events on tomorrow's date - be explicit about events
                        query = f"what events do I have on {tomorrow.strftime('%A, %B %d, %Y')}"
                        logger.debug(f"Expanded query: {query}")

                        # Set the intent type to calendar_query to ensure we get events, not just the date
                        if conversation_context:
                            conversation_context["last_intent"] = "calendar_query"
                    except Exception as e:
                        logger.error(f"Error processing date follow-up: {e}")
                        logger.exception("Exception details:")

            # If previous question was about events on a particular date
            elif conversation_context.get("last_intent") in [
                "search_events",
                "calendar_query",
            ]:
                if "tomorrow" in query.lower() or "next day" in query.lower():
                    # Get the previous date if available
                    if conversation_context.get("last_date"):
                        try:
                            # Parse the previous date and add a day
                            from dateutil import parser
                            from datetime import timedelta

                            # Try to parse the date string
                            prev_date_str = conversation_context.get("last_date")
                            prev_date = parser.parse(prev_date_str)
                            next_date = prev_date + timedelta(days=1)

                            # Create a query for the next day - be explicit about events
                            query = f"what events do I have on {next_date.strftime('%A, %B %d, %Y')}"
                            logger.debug(f"Expanded follow-up query: {query}")

                            # Ensure we're keeping the right intent type
                            if conversation_context:
                                conversation_context["last_intent"] = "calendar_query"
                        except Exception as e:
                            logger.error(f"Error processing date follow-up: {e}")
                            logger.exception("Exception details:")

        # Determine the intent of the query - pass the conversation context to handle follow-ups
        logger.debug("Calling determine_query_intent")
        intent_data = determine_query_intent(query, conversation_context)
        logger.debug(f"Intent determined: {intent_data.get('intent_type')}")

        # Add additional context for follow-up questions
        if is_follow_up and conversation_context:
            intent_data["is_follow_up"] = True
            intent_data["previous_intent"] = conversation_context.get("last_intent")
            intent_data["previous_response"] = conversation_context.get("last_response")

        # Check if this is a greeting or non-calendar intent
        intent_type = intent_data.get("intent_type", "").lower()
        needs_calendar_data = intent_data.get("needs_calendar_data", True)

        # Handle greeting intents without accessing calendar
        if intent_type == "greeting" or (
            intent_type == "assistant_info" and not needs_calendar_data
        ):
            logger.info(f"Handling greeting intent: {intent_type}")
            return {
                "status": "success",
                "message": "Hello! I'm your calendar assistant. How can I help you with your schedule today?",
                "intent_type": intent_type,
            }

        # Default values if not provided by intent detection
        intent_data.setdefault("intent_type", "search_events")
        intent_data.setdefault("is_past", False)
        intent_data.setdefault("days_range", 7)
        intent_data.setdefault("reverse_chronological", False)
        intent_data.setdefault("specific_date", None)
        intent_data.setdefault("search_terms", [])
        intent_data.setdefault("time_info", {})
        intent_data.setdefault("specified_calendar", "primary")

        logger.debug(f"Processing intent with parameters: {intent_data}")

        # Process the intent
        logger.debug("Calling process_intent")
        response = process_intent(
            intent_type=intent_data.get("intent_type"),
            is_past=intent_data.get("is_past"),
            days_range=intent_data.get("days_range"),
            reverse_chronological=intent_data.get("reverse_chronological"),
            specific_date=intent_data.get("specific_date"),
            search_terms=intent_data.get("search_terms"),
            query=query,
            time_info=intent_data.get("time_info", {}),
            specified_calendar=intent_data.get("specified_calendar"),
            is_find_last_occurrence=intent_data.get("is_find_last_occurrence", False),
            is_find_next_occurrence=intent_data.get("is_find_next_occurrence", False),
        )
        logger.debug("Intent processing complete")

        # Add the original intent data and time info to the response
        response["intent_type"] = intent_data.get("intent_type")
        response["time_info"] = intent_data.get("time_info", {})

        # Log events count if available
        if "events" in response:
            events_count = len([e for e in response["events"] if e is not None])
            logger.info(f"Found {events_count} events for query: {query}")

        return response
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        logger.exception("Exception details:")
        return {
            "status": "error",
            "message": f"I encountered an error: {str(e)}",
        }


# Enhanced processing using the new prompt strategy
def process_query(query, conversation_context=None):
    """Process a query using the enhanced prompt engineering strategy"""
    logger.debug(f"process_query called with query: {query}")

    if not conversation_context:
        conversation_context = {
            "last_intent": None,
            "last_response": None,
            "last_time_info": None,
            "last_date": None,
            "chat_history": [],
        }
        logger.debug("Created new conversation context")

    # Store in history
    conversation_context["chat_history"].append({"role": "user", "content": query})

    try:
        # Try the enhanced prompt strategy first
        from backend.app.utils.enhanced_prompts import EnhancedCalendarProcessor

        processor = EnhancedCalendarProcessor()
        user_context = {
            "current_datetime": datetime.now().isoformat(),
            "timezone": "America/New_York",  # Could be made configurable
            "chat_history": conversation_context.get("chat_history", []),
        }

        result = processor.process_calendar_query(query, user_context)

        # Use the enhanced response
        formatted_response = result.response

        # Store in history
        conversation_context["chat_history"].append(
            {"role": "assistant", "content": formatted_response}
        )

        # Update conversation context
        conversation_context["last_intent"] = result.intent
        conversation_context["last_response"] = {
            "intent_type": result.intent,
            "confidence": result.confidence,
            "needs_clarification": result.needs_clarification,
        }

        logger.info(
            f"Enhanced processing: {result.intent} (confidence: {result.confidence})"
        )

        return formatted_response, conversation_context

    except Exception as e:
        logger.warning(f"Enhanced processing failed, falling back to legacy: {e}")

        # Fallback to original processing method
        response = get_intent_response(query, conversation_context)
        formatted_response = format_chatbot_response(response)

        # Store in history
        conversation_context["chat_history"].append(
            {"role": "assistant", "content": formatted_response}
        )

        # Update conversation context
        conversation_context["last_intent"] = response.get("intent_type")
        conversation_context["last_response"] = response
        if "time_info" in response:
            conversation_context["last_time_info"] = response["time_info"]
        if "date" in response:
            conversation_context["last_date"] = response["date"]

        return formatted_response, conversation_context


def simulate_typing(text):
    """Simulate typing effect for bot responses"""
    try:
        for char in text:
            print(char, end="", flush=True)
            # Random delay between 0.01 and 0.03 seconds
            time.sleep(0.01)
        print()
    except BrokenPipeError:
        # Our custom excepthook will handle this
        raise


def run_chat():
    """Run the chat interface"""
    logger.info("Starting chat interface")
    print_welcome()

    # Create prompt session
    session = PromptSession(style=style)

    # Track conversation context for follow-up questions
    conversation_context = {
        "last_intent": None,
        "last_response": None,
        "last_time_info": None,
        "last_date": None,
        "chat_history": [],
    }

    while True:
        try:
            # Get user input
            user_input = session.prompt(HTML("<b><style fg='blue'>You: </style></b>"))
            logger.debug(f"User input: {user_input}")

            # Check for exit command
            if user_input.lower() in ["exit", "quit", "bye"]:
                logger.info("User exited the chat")
                print(colored("\nGoodbye! Have a great day! 👋", "cyan"))
                break

            # Skip empty inputs
            if not user_input.strip():
                continue

            # Process the query
            print(colored("ORII: ", "green", attrs=["bold"]), end="")

            # Get response via the new processor function that doesn't log to console
            formatted_response, conversation_context = process_query(
                user_input, conversation_context
            )

            # Display response with typing effect
            simulate_typing(formatted_response)
            print()  # Add a blank line for readability

        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt detected, exiting")
            print(colored("\nGoodbye! Have a great day! 👋", "cyan"))
            break
        except Exception as e:
            logger.error(f"Error in chat loop: {str(e)}")
            logger.exception("Exception details:")
            print(colored(f"Sorry, something went wrong: {str(e)}", "red"))


def get_logs_path():
    """Return the path to the log file"""
    return log_file


if __name__ == "__main__":
    try:
        logger.info("ORII Calendar Assistant starting")
        run_chat()
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        logger.info("KeyboardInterrupt detected in main thread, shutting down")
        safe_print(colored("\nGoodbye! Have a great day! 👋", "cyan"))
        sys.exit(0)
