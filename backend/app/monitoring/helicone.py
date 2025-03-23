"""
Helicone integration configuration for ORII.
Handles LLM request tracking and analytics.
"""

import os
from openai import OpenAI
from typing import Dict, Any, Optional


def get_helicone_client(api_key: Optional[str] = None) -> OpenAI:
    """
    Get an OpenAI client configured with Helicone

    Args:
        api_key: Optional OpenAI API key. If not provided, will use environment variable.

    Returns:
        OpenAI client configured with Helicone
    """
    return OpenAI(
        api_key=api_key or os.getenv("OPENAI_API_KEY"),
        base_url="https://oai.hconeai.com/v1",
        default_headers={
            "Helicone-Auth": f"Bearer {os.getenv('HELICONE_API_KEY')}",
            "Helicone-Cache-Enabled": "true",
        },
    )


def create_helicone_headers(
    user_id: str, query_type: str, custom_properties: Optional[Dict[str, Any]] = None
) -> Dict[str, str]:
    """
    Create headers for Helicone request tracking

    Args:
        user_id: Unique identifier for the user
        query_type: Type of query being made
        custom_properties: Additional properties to track

    Returns:
        Dictionary of Helicone headers
    """
    headers = {
        "Helicone-User-Id": user_id,
        "Helicone-Property-Query-Type": query_type,
    }

    if custom_properties:
        for key, value in custom_properties.items():
            headers[f"Helicone-Property-{key}"] = str(value)

    return headers


class HeliconeTracker:
    """Helper class for tracking LLM usage with Helicone"""

    def __init__(self, client: Optional[OpenAI] = None):
        """
        Initialize the tracker

        Args:
            client: Optional pre-configured OpenAI client
        """
        self.client = client or get_helicone_client()

    def track_completion(
        self,
        messages: list,
        user_id: str,
        query_type: str,
        custom_properties: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Any:
        """
        Track a completion request with Helicone

        Args:
            messages: List of messages for the completion
            user_id: Unique identifier for the user
            query_type: Type of query being made
            custom_properties: Additional properties to track
            **kwargs: Additional arguments for completion

        Returns:
            OpenAI completion response
        """
        headers = create_helicone_headers(user_id, query_type, custom_properties)

        return self.client.chat.completions.create(
            messages=messages, headers=headers, **kwargs
        )
