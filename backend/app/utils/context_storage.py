"""
Enhanced Context Storage with Multiple Backend Options
"""

import json
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class ContextStorage(ABC):
    """Abstract base class for context storage backends"""

    @abstractmethod
    def save_context(self, session_id: str, context: Dict[str, Any]) -> bool:
        """Save conversation context"""
        pass

    @abstractmethod
    def get_context(self, session_id: str) -> Dict[str, Any]:
        """Get conversation context"""
        pass

    @abstractmethod
    def cleanup_old_contexts(self) -> int:
        """Clean up old contexts, return number of cleaned up"""
        pass


class QueryLimitedContextStorage(ContextStorage):
    """Context storage that keeps only the last N queries per session"""

    def __init__(self, max_queries: int = 10, backend: str = "file"):
        self.max_queries = max_queries
        self.backend_type = backend

        if backend == "redis":
            self._init_redis()
        elif backend == "database":
            self._init_database()
        else:  # file backend
            self._init_file()

    def _init_redis(self):
        """Initialize Redis backend"""
        try:
            import redis

            self.redis_client = redis.Redis(host="localhost", port=6379, db=0)
            self.redis_client.ping()  # Test connection
            logger.info("Redis backend initialized for context storage")
        except Exception as e:
            logger.warning(f"Redis not available, falling back to file storage: {e}")
            self._init_file()

    def _init_database(self):
        """Initialize database backend"""
        try:
            from ..models.conversation_context import ConversationContext
            from ..database import get_db

            self.db_model = ConversationContext
            self.get_db = get_db
            logger.info("Database backend initialized for context storage")
        except Exception as e:
            logger.warning(f"Database not available, falling back to file storage: {e}")
            self._init_file()

    def _init_file(self):
        """Initialize file backend"""
        self.context_dir = "context_cache"
        os.makedirs(self.context_dir, exist_ok=True)
        logger.info("File backend initialized for context storage")

    def add_query_to_context(
        self, session_id: str, query: str, response: str, intent: str = None
    ) -> Dict[str, Any]:
        """Add a new query to the context and maintain query limit"""
        context = self.get_context(session_id)

        # Initialize queries list if not exists
        if "queries" not in context:
            context["queries"] = []

        # Add new query
        query_entry = {
            "query": query,
            "response": response,
            "intent": intent,
            "timestamp": datetime.now().isoformat(),
        }

        context["queries"].append(query_entry)

        # Keep only last N queries
        context["queries"] = context["queries"][-self.max_queries :]

        # Update metadata
        context["last_query"] = query
        context["last_response"] = response
        context["last_intent"] = intent
        context["updated_at"] = datetime.now().isoformat()

        # Save updated context
        self.save_context(session_id, context)

        logger.info(
            f"Added query to context for session {session_id}. "
            f"Context now has {len(context['queries'])} queries."
        )

        return context

    def save_context(self, session_id: str, context: Dict[str, Any]) -> bool:
        """Save context using configured backend"""
        try:
            if hasattr(self, "redis_client"):
                return self._save_to_redis(session_id, context)
            elif hasattr(self, "db_model"):
                return self._save_to_database(session_id, context)
            else:
                return self._save_to_file(session_id, context)
        except Exception as e:
            logger.error(f"Error saving context for session {session_id}: {e}")
            return False

    def get_context(self, session_id: str) -> Dict[str, Any]:
        """Get context using configured backend"""
        try:
            if hasattr(self, "redis_client"):
                return self._get_from_redis(session_id)
            elif hasattr(self, "db_model"):
                return self._get_from_database(session_id)
            else:
                return self._get_from_file(session_id)
        except Exception as e:
            logger.error(f"Error getting context for session {session_id}: {e}")
            return self._empty_context()

    def _save_to_redis(self, session_id: str, context: Dict[str, Any]) -> bool:
        """Save to Redis with TTL"""
        try:
            self.redis_client.setex(
                f"context:{session_id}",
                86400,  # 24 hours TTL
                json.dumps(context, default=str),
            )
            return True
        except Exception as e:
            logger.error(f"Redis save error: {e}")
            return False

    def _get_from_redis(self, session_id: str) -> Dict[str, Any]:
        """Get from Redis"""
        try:
            data = self.redis_client.get(f"context:{session_id}")
            return json.loads(data) if data else self._empty_context()
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return self._empty_context()

    def _save_to_database(self, session_id: str, context: Dict[str, Any]) -> bool:
        """Save to database"""
        try:
            db = next(self.get_db())

            # Find existing record
            record = (
                db.query(self.db_model)
                .filter(
                    self.db_model.session_id == session_id,
                    self.db_model.is_active == True,
                )
                .first()
            )

            if record:
                # Update existing
                record.last_query = context.get("last_query")
                record.last_response = context.get("last_response")
                record.last_intent = context.get("last_intent")
                record.chat_history = json.dumps(context.get("queries", []))
                record.updated_at = datetime.now()
            else:
                # Create new
                record = self.db_model(
                    session_id=session_id,
                    last_query=context.get("last_query"),
                    last_response=context.get("last_response"),
                    last_intent=context.get("last_intent"),
                    chat_history=json.dumps(context.get("queries", [])),
                    expires_at=datetime.now()
                    + timedelta(days=1),  # 1 day for fresh context only
                )
                db.add(record)

            db.commit()
            return True
        except Exception as e:
            logger.error(f"Database save error: {e}")
            return False

    def _get_from_database(self, session_id: str) -> Dict[str, Any]:
        """Get from database"""
        try:
            db = next(self.get_db())
            record = (
                db.query(self.db_model)
                .filter(
                    self.db_model.session_id == session_id,
                    self.db_model.is_active == True,
                )
                .first()
            )

            if record:
                queries = json.loads(record.chat_history) if record.chat_history else []
                return {
                    "queries": queries,
                    "last_query": record.last_query,
                    "last_response": record.last_response,
                    "last_intent": record.last_intent,
                    "updated_at": (
                        record.updated_at.isoformat() if record.updated_at else None
                    ),
                }
            else:
                return self._empty_context()
        except Exception as e:
            logger.error(f"Database get error: {e}")
            return self._empty_context()

    def _save_to_file(self, session_id: str, context: Dict[str, Any]) -> bool:
        """Save to file"""
        try:
            file_path = os.path.join(self.context_dir, f"{session_id}.json")
            with open(file_path, "w") as f:
                json.dump(context, f, default=str, indent=2)
            return True
        except Exception as e:
            logger.error(f"File save error: {e}")
            return False

    def _get_from_file(self, session_id: str) -> Dict[str, Any]:
        """Get from file"""
        try:
            file_path = os.path.join(self.context_dir, f"{session_id}.json")
            if os.path.exists(file_path):
                with open(file_path, "r") as f:
                    return json.load(f)
            else:
                return self._empty_context()
        except Exception as e:
            logger.error(f"File get error: {e}")
            return self._empty_context()

    def _empty_context(self) -> Dict[str, Any]:
        """Return empty context structure"""
        return {
            "queries": [],
            "last_query": None,
            "last_response": None,
            "last_intent": None,
            "updated_at": datetime.now().isoformat(),
        }

    def cleanup_old_contexts(self) -> int:
        """Clean up old contexts based on backend"""
        try:
            if hasattr(self, "redis_client"):
                return self._cleanup_redis()
            elif hasattr(self, "db_model"):
                return self._cleanup_database()
            else:
                return self._cleanup_files()
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            return 0

    def _cleanup_redis(self) -> int:
        """Redis handles TTL automatically"""
        return 0  # Redis auto-expires

    def _cleanup_database(self) -> int:
        """Clean up expired database records"""
        try:
            db = next(self.get_db())
            expired_records = (
                db.query(self.db_model)
                .filter(self.db_model.expires_at < datetime.now())
                .all()
            )

            count = len(expired_records)
            for record in expired_records:
                db.delete(record)

            db.commit()
            logger.info(f"Cleaned up {count} expired context records")
            return count
        except Exception as e:
            logger.error(f"Database cleanup error: {e}")
            return 0

    def _cleanup_files(self) -> int:
        """Clean up old files (older than 1 day)"""
        try:
            cutoff_time = time.time() - (1 * 24 * 60 * 60)  # 1 day
            count = 0

            for filename in os.listdir(self.context_dir):
                if filename.endswith(".json"):
                    file_path = os.path.join(self.context_dir, filename)
                    if os.path.getctime(file_path) < cutoff_time:
                        os.remove(file_path)
                        count += 1

            logger.info(f"Cleaned up {count} old context files")
            return count
        except Exception as e:
            logger.error(f"File cleanup error: {e}")
            return 0

    def get_recent_context_summary(self, session_id: str, last_n: int = 3) -> str:
        """Get a summary of recent conversation for context"""
        context = self.get_context(session_id)
        queries = context.get("queries", [])

        if not queries:
            return ""

        recent = queries[-last_n:]
        summary_parts = []

        for q in recent:
            summary_parts.append(f"User: {q['query']}")
            if q["response"]:
                # Truncate long responses
                response = (
                    q["response"][:100] + "..."
                    if len(q["response"]) > 100
                    else q["response"]
                )
                summary_parts.append(f"Assistant: {response}")

        return "\n".join(summary_parts)


# Factory function to create storage instance
def create_context_storage(
    backend: str = "file", max_queries: int = 10
) -> ContextStorage:
    """Factory to create context storage with specified backend"""
    return QueryLimitedContextStorage(max_queries=max_queries, backend=backend)
