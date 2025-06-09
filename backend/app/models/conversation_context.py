from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone

Base = declarative_base()


class ConversationContext(Base):
    """Model for storing conversation context between queries"""

    __tablename__ = "conversation_contexts"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(255), index=True, nullable=False)
    user_id = Column(
        String(255), index=True, nullable=True
    )  # Optional user association

    # Conversation state
    last_intent = Column(String(100), nullable=True)
    last_query = Column(Text, nullable=True)
    last_response = Column(Text, nullable=True)

    # Context for follow-ups
    last_time_direction = Column(String(50), nullable=True)  # past, present, future
    last_search_type = Column(String(50), nullable=True)  # semantic, time-based
    last_events_found = Column(Text, nullable=True)  # JSON string of last found events

    # Chat history (JSON string)
    chat_history = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    expires_at = Column(DateTime, nullable=True)  # Optional expiration for cleanup

    # Flags
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<ConversationContext(session_id='{self.session_id}', last_intent='{self.last_intent}')>"
