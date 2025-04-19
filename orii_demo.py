#!/usr/bin/env python3
"""
ORII Calendar Assistant Demo
----------------------------
This file demonstrates the ORII calendar assistant by providing a chat interface
that connects all functionality from the repository.
"""

import os
import sys
from datetime import datetime
import logging
import json
from termcolor import colored
import time
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML
import traceback
from dateutil import parser
from datetime import timedelta

# Add both the current directory and the backend directory to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Setup basic logging to file instead of console
log_file = os.path.join(current_dir, "orii_demo.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename=log_file,
    filemode="a",
)
logger = logging.getLogger("orii_demo")

# Disable other loggers that print to console
for name in logging.root.manager.loggerDict:
    logging.getLogger(name).setLevel(logging.WARNING)
    # Explicitly remove any console handlers
    for handler in logging.getLogger(name).handlers[:]:
        if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stdout:
            logging.getLogger(name).removeHandler(handler)

# Import LLM client
try:
    from backend.app.utils.llm_client import get_llm_client
except ImportError:
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
        logger.error(f"Failed to import {module_path}: {str(e)}")
        logger.error(traceback.format_exc())
        print(
            colored(
                f"Error importing {module_path}. The demo may not function correctly.",
                "red",
            )
        )
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

# Setup logging with the app's logger if available
try:
    from backend.app.utils.logger import setup_logger

    # Configure the app logger to write to file instead of console
    logger = setup_logger("orii_demo", console_output=False, log_file=log_file)
    logger.info("Using application logger")
except ImportError:
    logger.info("Using basic logger")

# Create a styled prompt session
style = Style.from_dict(
    {
        "prompt": "bold #0000FF",  # Bold blue
    }
)

# Store conversation history
conversation_history = []


def print_welcome():
    """Print welcome message"""
    print("\n" + "=" * 80)
    print(colored("🗓️  ORII Calendar Assistant Demo", "cyan", attrs=["bold"]))
    print("=" * 80)
    print(colored("Ask me anything about your calendar or scheduling!", "green"))
    print("Examples:")
    print("  - What's on my calendar today?")
    print("  - Schedule a meeting with John tomorrow at 2pm")
    print("  - When was my last dentist appointment?")
    print("  - Show me my meetings for next week")
    print("  - What's happening this weekend?")
    print("Type 'exit' or 'quit' to end the conversation.")
    print("=" * 80 + "\n")


def format_chatbot_response(response):
    """Format the response for display"""
    if isinstance(response, dict):
        if "status" in response and response["status"] == "error":
            return colored(f"Error: {response.get('message', 'Unknown error')}", "red")

        if "message" in response:
            result = [colored(response["message"], "green")]

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

                    conversational_summary = llm_client.get_completion(prompt)
                    result = [colored(conversational_summary, "green")]
                except Exception as e:
                    logger.error(f"Error generating conversational response: {e}")
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
        # Check if we have the required functions
        if not determine_query_intent or not process_intent:
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

        # Determine the intent of the query - pass the conversation context to handle follow-ups
        intent_data = determine_query_intent(query, conversation_context)

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

        # Process the intent
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

        # Add the original intent data and time info to the response
        response["intent_type"] = intent_data.get("intent_type")
        response["time_info"] = intent_data.get("time_info", {})

        return response
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "message": f"I encountered an error: {str(e)}",
        }


def simulate_typing(text):
    """Simulate typing effect for bot responses"""
    for char in text:
        print(char, end="", flush=True)
        # Random delay between 0.01 and 0.03 seconds
        time.sleep(0.01)
    print()


def run_chat():
    """Run the chat interface"""
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

            # Check for exit command
            if user_input.lower() in ["exit", "quit", "bye"]:
                print(colored("\nGoodbye! Have a great day! 👋", "cyan"))
                break

            # Skip empty inputs
            if not user_input.strip():
                continue

            # Store in history
            conversation_history.append({"role": "user", "content": user_input})
            conversation_context["chat_history"].append(
                {"role": "user", "content": user_input}
            )

            # Process the query
            print(colored("ORII: ", "green", attrs=["bold"]), end="")

            # Get response with conversation context
            response = get_intent_response(user_input, conversation_context)

            # Format and display response
            formatted_response = format_chatbot_response(response)
            simulate_typing(formatted_response)

            # Store in history
            conversation_history.append(
                {"role": "assistant", "content": formatted_response}
            )
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

            print()  # Add a blank line for readability

        except KeyboardInterrupt:
            print(colored("\nGoodbye! Have a great day! 👋", "cyan"))
            break
        except Exception as e:
            logger.error(f"Error in chat loop: {str(e)}")
            logger.error(traceback.format_exc())
            print(colored(f"Sorry, something went wrong: {str(e)}", "red"))


if __name__ == "__main__":
    run_chat()
