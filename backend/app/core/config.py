# backend/app/core/config.py

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Environment settings
    ENV: str = "development"
    HOST: str = "localhost"
    PORT: int = 8000
    DEV_MODE: str = "true"
    # Google OAuth
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    REDIRECT_URI: str = "http://localhost:8000/api/oauth/callback"

    # API Keys
    OPENAI_API_KEY: str

    # Database settings
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_NAME: str
    DATABASE_URL: str  # Main database for real users
    TEST_DATABASE_URL: str  # Test database for running tests

    # Authentication
    JWT_SECRET: str  # For user sessions with ORII
    SECRET_KEY: str  # For initial Google Calendar auth

    # Monitoring - Add these fields
    REDIS_URL: str = "redis://localhost:6379"
    PROMETHEUS_PORT: str = "9090"

    class Config:
        env_file = ".env"
        case_sensitive = True

    def get_database_url(self, testing: bool = False) -> str:
        """
        Get the appropriate database URL based on context
        Args:
            testing: If True, returns test database URL
        """
        return self.TEST_DATABASE_URL if testing else self.DATABASE_URL


@lru_cache()
def get_settings() -> Settings:
    """Returns cached settings instance"""
    return Settings()
