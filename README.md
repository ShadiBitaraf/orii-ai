# ORII Calendar Assistant

A comprehensive calendar assistant integrating with Google Calendar.

## Setup Instructions

1. **Clone the Repository**

```
git clone <repository-url>
cd orii-ai
```

2. **Create and Activate Virtual Environment**

```
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install Dependencies**

```
pip install -r requirements.txt
```

Note: Some packages like `pydantic-core` require Rust and Cargo (Rust's package manager). Make sure you have them installed.

4. **Environment Setup**

Copy the example environment file:

```
cp backend/.env.example backend/.env
```

Then edit the `.env` file to add your:

- Google OAuth credentials
- OpenAI API key
- Database settings
- JWT secret key

5. **Database Setup**

For development, you can use SQLite:

```
export DATABASE_URL=sqlite:///test.db
```

For production, set up PostgreSQL and update the connection string in the `.env` file.

Run migrations:

```
cd backend
alembic upgrade head
```

6. **Run the Application**

Using the provided script (recommended):

```
./run_orii_demo.sh
```

Or manually:

```
cd backend
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.

## Project Structure

- `/backend` - FastAPI backend application
  - `/app` - Main application code
    - `/api` - API routes
    - `/models` - Database models
    - `/schemas` - Pydantic schemas
    - `/core` - Core functionality
    - `/utils` - Utility functions
    - `/logs` - Application logs
  - `/tests` - Unit and integration tests
  - `/alembic` - Database migrations
- `/app/logs` - Application log files
- `log_monitor.py` - Tool for monitoring logs in real-time
- `run_orii_demo.sh` - Script to run the application

## Development

For development:

1. Install the dev dependencies:

```
pip install pytest pytest-asyncio httpx pytest-cov black
```

2. Run tests:

```
pytest
```

3. Format code:

```
black .
```

## Running the Application

The `run_orii_demo.sh` script provides several options:

```
./run_orii_demo.sh           # Start the ORII Calendar Assistant
./run_orii_demo.sh --logs    # Start the log monitor
./run_orii_demo.sh --help    # Show usage information
```

## Logging System

ORII uses Loguru for advanced structured logging:

- JSON-formatted logs stored in `app/logs` directory
- Automatic log rotation (10MB per file with 5 backup files)
- Asynchronous logging for better performance
- Environment-based configuration

### Log Monitor

The log monitor tool allows you to view and filter logs in real-time:

```
python log_monitor.py --list          # List available log files
python log_monitor.py -f orii_demo.log # Monitor a specific log file
python log_monitor.py -l DEBUG        # Filter by log level
python log_monitor.py -m orii_demo    # Filter by module name
```

### Logging Configuration

The logging system can be configured using environment variables:

- `ORII_LOG_LEVEL`: Set the logging level (DEBUG, INFO, WARNING, ERROR)
- `ORII_DEV_MODE`: Enable developer mode with colored console logs (true/false)
- `ORII_LOG_RETENTION`: Number of log files to keep (default: 5)
- `ORII_LOG_ROTATION`: Size at which to rotate logs (default: "10 MB")
- `ORII_JSON_LOGS`: Use JSON format for logs (true/false)

Example:

```
export ORII_LOG_LEVEL=DEBUG
export ORII_DEV_MODE=true
./run_orii_demo.sh
```

## Docker Deployment

See `docker/README.Docker.md` for Docker deployment instructions.
