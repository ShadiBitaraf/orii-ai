#!/bin/bash
# Run the ORII Calendar Assistant Demo

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Show a message with color
message() {
  echo -e "${GREEN}[ORII]${NC} $1" 2>/dev/null || true
}

warning() {
  echo -e "${YELLOW}[WARNING]${NC} $1" 2>/dev/null || true
}

error() {
  echo -e "${RED}[ERROR]${NC} $1" 2>/dev/null || true
}

# Handle SIGPIPE - prevent "Broken pipe" errors
trap '' PIPE

# Create logs directory if it doesn't exist
mkdir -p app/logs

# Check Python installation
if ! command -v python3 &> /dev/null; then
    error "Python 3 is not installed. Please install Python 3 and try again."
    exit 1
fi

# Activate virtual environment or create if it doesn't exist
if [ -d "venv" ]; then
    # message "Activating virtual environment..."
    source venv/bin/activate
else
    warning "Virtual environment not found. Creating a new one..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        error "Failed to create virtual environment. Please install venv package and try again."
        exit 1
    fi
    # message "Virtual environment created successfully."
    source venv/bin/activate
fi

# Check for required dependencies
pip -q list 2>/dev/null | grep -q "prompt_toolkit" 
if [ $? -ne 0 ]; then
    # warning "Installing required dependencies..."
    pip install prompt_toolkit termcolor >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        error "Failed to install dependencies. Please check your internet connection and try again."
        exit 1
    fi
    # message "Dependencies installed successfully."
fi

# Check for Loguru
pip -q list 2>/dev/null | grep -q "loguru" 
if [ $? -ne 0 ]; then
    # warning "Installing Loguru logging library..."
    pip install loguru >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        error "Failed to install Loguru. Falling back to standard logging."
    # else
    #     message "Loguru installed successfully."
    fi
fi

# Install all requirements if they're not already installed
pip -q list 2>/dev/null | grep -q "fastapi" 
if [ $? -ne 0 ]; then
    # warning "Installing project requirements..."
    pip install -q -r requirements.txt
    if [ $? -ne 0 ]; then
        error "Failed to install all requirements. Some features may not work correctly."
        warning "Continuing with basic functionality only..."
    # else
        # message "Project requirements installed successfully."
    fi
fi

# Set environment variables
export PYTHONPATH=$(pwd):$PYTHONPATH

# Check for command-line arguments
if [ "$1" == "--logs" ] || [ "$1" == "-l" ]; then
    message "Starting log monitor..."
    # Enable console output for log monitor
    export ORII_DEV_MODE=true
    python log_monitor.py
    exit 0
fi

if [ "$1" == "--debug" ] || [ "$1" == "-d" ]; then
    message "Starting ORII Calendar Assistant in debug mode..."
    # Enable console output for debugging
    export ORII_DEV_MODE=true
    export ORII_LOG_LEVEL=DEBUG
    python -u orii_demo.py
    exit 0
fi

if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
    message "ORII Calendar Assistant"
    echo "Usage: ./run_orii_demo.sh [options]"
    echo "Options:"
    echo "  --logs, -l    Start the log monitor"
    echo "  --debug, -d   Start with debug logging to console"
    echo "  --help, -h    Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./run_orii_demo.sh           # Start the ORII Calendar Assistant"
    echo "  ./run_orii_demo.sh --logs    # Start the log monitor"
    exit 0
fi

# Run the demo directly - disable console logging by default
export ORII_DEV_MODE=false
# message "Starting ORII Calendar Assistant..."
python -u orii_demo.py

# Check if the demo exited normally
STATUS=$?
# message "Demo finished with status code: $STATUS"

# Deactivate virtual environment when done
# message "Deactivating virtual environment..."
deactivate

message "Thank you for using ORII Calendar Assistant!" 