import datetime
import os
import time

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/ai_shorts_db",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


class VideoTask(Base):
    __tablename__ = "video_tasks"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True)
    youtube_url = Column(String, nullable=False)
    status = Column(String, default="pending", nullable=False)
    progress = Column(Integer, default=0, nullable=False)
    current_step = Column(String, default="pending", nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=False, index=True)
    audio_path = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    words_json = Column(Text, nullable=False)
    language = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class ShortFragment(Base):
    __tablename__ = "short_fragments"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=False, index=True)
    title = Column(String, nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    duration = Column(Float, nullable=False)
    reasoning = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    
    # Поля Спринта 2 (Александр Беляев / US 2, US 3, US 7)
    virality_score = Column(Integer, default=0, nullable=False)
    hook_reason = Column(Text, nullable=True)
    internal_criticism = Column(Text, nullable=True)
    first_words = Column(String, nullable=True)
    last_words = Column(String, nullable=True)
    adjusted_start_time = Column(Float, nullable=True)
    adjusted_end_time = Column(Float, nullable=True)
    video_path = Column(String, nullable=True)
    status = Column(String, default="ready", nullable=False)

    created_at = Column(DateTime, default=_utcnow)


def init_db(retries: int = 10, delay: int = 2):
    """Initialize database tables with automatic retries while DB container boots."""
    for attempt in range(1, retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            # Automatic safe migration for new Sprint 2 columns if tables already existed
            with engine.connect() as conn:
                task_columns = [
                    ("progress", "INTEGER DEFAULT 0"),
                    ("current_step", "VARCHAR DEFAULT 'pending'"),
                    ("error_message", "TEXT"),
                    ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
                ]
                for col_name, col_type in task_columns:
                    try:
                        if engine.dialect.name == "sqlite":
                            res = conn.exec_driver_sql("PRAGMA table_info(video_tasks)").fetchall()
                            existing_cols = [r[1] for r in res]
                            if col_name not in existing_cols:
                                conn.exec_driver_sql(f"ALTER TABLE video_tasks ADD COLUMN {col_name} {col_type}")
                        else:
                            conn.exec_driver_sql(f"ALTER TABLE video_tasks ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                    except Exception:
                        try:
                            conn.rollback()
                        except Exception:
                            pass

                new_columns = [
                    ("virality_score", "INTEGER DEFAULT 0"),
                    ("hook_reason", "TEXT"),
                    ("internal_criticism", "TEXT"),
                    ("first_words", "VARCHAR"),
                    ("last_words", "VARCHAR"),
                    ("adjusted_start_time", "FLOAT"),
                    ("adjusted_end_time", "FLOAT"),
                    ("video_path", "VARCHAR"),
                    ("status", "VARCHAR DEFAULT 'ready'"),
                ]
                for col_name, col_type in new_columns:
                    try:
                        if engine.dialect.name == "sqlite":
                            res = conn.exec_driver_sql("PRAGMA table_info(short_fragments)").fetchall()
                            existing_cols = [r[1] for r in res]
                            if col_name not in existing_cols:
                                conn.exec_driver_sql(f"ALTER TABLE short_fragments ADD COLUMN {col_name} {col_type}")
                        else:
                            conn.exec_driver_sql(f"ALTER TABLE short_fragments ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                    except Exception:
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                conn.commit()
            return
        except Exception as exc:
            if attempt < retries:
                time.sleep(delay)
            else:
                raise exc


