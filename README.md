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

## Docker Deployment

See `docker/README.Docker.md` for Docker deployment instructions.
