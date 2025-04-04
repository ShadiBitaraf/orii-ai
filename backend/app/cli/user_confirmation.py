"""
User confirmation utilities for the calendar assistant.

This module provides functions for getting confirmation from users before
performing actions.
"""

import logging
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)


def get_user_confirmation(message: str, default: bool = False) -> bool:
    """
    Get confirmation from the user.

    Args:
        message: The message to display
        default: The default response if the user just presses enter

    Returns:
        True if the user confirmed, False otherwise
    """
    valid_responses = {
        "yes": True,
        "y": True,
        "ye": True,
        "no": False,
        "n": False,
    }

    if default:
        prompt = f"{message} [Y/n] "
    else:
        prompt = f"{message} [y/N] "

    while True:
        try:
            response = input(prompt).lower().strip()

            if not response:  # User just pressed enter
                return default

            if response in valid_responses:
                return valid_responses[response]

            print("Please respond with 'yes' or 'no' (or 'y' or 'n').")
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
            return False
        except Exception as e:
            logger.error(f"Error getting user confirmation: {e}")
            return False


def get_user_selection(
    options: List[str], prompt: str, allow_cancel: bool = True
) -> Optional[int]:
    """
    Get a selection from the user.

    Args:
        options: List of options to choose from
        prompt: The prompt to display
        allow_cancel: Whether to allow the user to cancel the selection

    Returns:
        The index of the selected option, or None if the user cancelled
    """
    if not options:
        return None

    # Print options
    print(prompt)
    for i, option in enumerate(options):
        print(f"  {i+1}. {option}")

    if allow_cancel:
        print("  0. Cancel")

    # Get user selection
    while True:
        try:
            selection = input("Enter your selection: ").strip()

            if not selection and allow_cancel:
                return None

            try:
                selection_num = int(selection)
                if selection_num == 0 and allow_cancel:
                    return None

                if 1 <= selection_num <= len(options):
                    return selection_num - 1  # Convert to 0-based index

                print(f"Please enter a number between 1 and {len(options)}")
            except ValueError:
                print("Please enter a valid number.")
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
            return None
        except Exception as e:
            logger.error(f"Error getting user selection: {e}")
            return None


def get_user_input(prompt: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get text input from the user.

    Args:
        prompt: The prompt to display
        default: The default value if the user just presses enter

    Returns:
        The user's input, or None if the user cancelled
    """
    if default:
        full_prompt = f"{prompt} [{default}]: "
    else:
        full_prompt = f"{prompt}: "

    try:
        response = input(full_prompt).strip()

        if not response and default:
            return default

        return response
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        return None
    except Exception as e:
        logger.error(f"Error getting user input: {e}")
        return None


def get_user_date_time_input(prompt: str) -> Tuple[Optional[str], Optional[str], bool]:
    """
    Get date and time input from the user.

    Args:
        prompt: The prompt to display

    Returns:
        Tuple of (date_str, time_str, is_all_day)
    """
    print(prompt)

    # Get date
    date_str = get_user_input("Enter date (YYYY-MM-DD)")
    if not date_str:
        return None, None, False

    # Check if it's an all-day event
    is_all_day = get_user_confirmation("Is this an all-day event?", default=False)

    # Get time if not all-day
    time_str = None
    if not is_all_day:
        time_str = get_user_input("Enter time (HH:MM)")

    return date_str, time_str, is_all_day
