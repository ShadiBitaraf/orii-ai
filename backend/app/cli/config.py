"""
Configuration settings for the CLI application.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Google Calendar API scopes
SCOPES = [
    "https://www.googleapis.com/auth/calendar",  # Full access for testing all operations
    "https://www.googleapis.com/auth/calendar.events",
]

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Cache configuration
CACHE_TTL = 300  # 5 minutes for development, adjust as needed
LLM_CACHE_SIZE = 100  # Number of LLM responses to cache in memory

# Prometheus metrics
PROM_PORT = int(os.getenv("PROMETHEUS_PORT", "9090"))

# Development mode configuration
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"
if DEV_MODE:
    # Reduce API calls in development
    CACHE_TTL = 3600  # 1 hour cache in dev mode
