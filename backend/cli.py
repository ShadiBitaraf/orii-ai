#!/usr/bin/env python3
"""
ORII Calendar Assistant CLI runner script
"""

import sys
import os

# Add the current directory to sys.path to make imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the CLI command group
from app.cli.cli import cli

if __name__ == "__main__":
    # Set CLI mode environment variable
    os.environ["CLI_MODE"] = "true"
    cli()
