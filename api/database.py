"""
Database models and connection management
"""
from sqlalchemy import create_engine, Column, String, Integer, DateTime, JSON, Float, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

# Get database URL from environment variable
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test_results.db")

# PostgreSQL URLs from Railway/Render use 'postgres://' but SQLAlchemy needs 'postgresql://'
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class TestRun(Base):
    """Stores test run metadata"""
    __tablename__ = "test_runs"

    id = Column(String, primary_key=True, index=True)
    business_name = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="pending")  # pending, running, completed, failed
    providers = Column(JSON)  # List of providers used
    total_queries = Column(Integer, default=0)
    business_mentions = Column(Integer, default=0)
    visibility_score = Column(Float, default=0.0)
    competitors_found = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    results = Column(JSON, nullable=True)  # Store detailed results as JSON


class Competitor(Base):
    """Stores competitor mentions"""
    __tablename__ = "competitors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    test_run_id = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    count = Column(Integer, default=0)
    provider = Column(String, nullable=False)  # Which AI mentioned this competitor


class Query(Base):
    """Stores individual queries and responses"""
    __tablename__ = "queries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    test_run_id = Column(String, index=True, nullable=False)
    provider = Column(String, nullable=False)
    query_text = Column(Text, nullable=False)
    response_text = Column(Text, nullable=False)
    business_mentioned = Column(String, default="False")  # Boolean as string
    competitors_mentioned = Column(String, nullable=True)  # Semicolon separated
    business_position = Column(String, nullable=True)  # Early, Middle, Late


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Initialize database on import
init_db()
