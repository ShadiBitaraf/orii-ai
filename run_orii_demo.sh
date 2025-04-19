#!/bin/bash
# Run the ORII Calendar Assistant Demo

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Show a message with color
message() {
  echo -e "${GREEN}[ORII]${NC} $1"
}

warning() {
  echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

# Create logs directory if it doesn't exist
mkdir -p app/logs

# Check Python installation
if ! command -v python3 &> /dev/null; then
    error "Python 3 is not installed. Please install Python 3 and try again."
    exit 1
fi

# Activate virtual environment or create if it doesn't exist
if [ -d "venv" ]; then
    message "Activating virtual environment..."
    source venv/bin/activate
else
    warning "Virtual environment not found. Creating a new one..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        error "Failed to create virtual environment. Please install venv package and try again."
        exit 1
    fi
    message "Virtual environment created successfully."
    source venv/bin/activate
fi

# Check for required dependencies
message "Checking dependencies..."
python -c "import prompt_toolkit, termcolor" 2>/dev/null
if [ $? -ne 0 ]; then
    warning "Installing required dependencies..."
    pip install prompt_toolkit termcolor
    if [ $? -ne 0 ]; then
        error "Failed to install dependencies. Please check your internet connection and try again."
        exit 1
    fi
    message "Dependencies installed successfully."
fi

# Install all requirements if they're not already installed
pip list | grep -q "fastapi"
if [ $? -ne 0 ]; then
    warning "Installing project requirements..."
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        error "Failed to install all requirements. Some features may not work correctly."
        warning "Continuing with basic functionality only..."
    else
        message "Project requirements installed successfully."
    fi
fi

# Set environment variables
export PYTHONPATH=$(pwd):$PYTHONPATH

# Run the demo
message "Starting ORII Calendar Assistant Demo..."
python orii_demo.py

# Check if the demo exited with an error
if [ $? -ne 0 ]; then
    error "The demo exited with an error. Please check the logs for more information."
    exit 1
fi

# Deactivate virtual environment when done
message "Demo finished. Deactivating virtual environment..."
deactivate

message "Thank you for using ORII Calendar Assistant!" 