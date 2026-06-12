"""Project configuration and path helpers."""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger = logging.getLogger("aliyun_oss_rag")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name if name.startswith("aliyun_oss_rag") else f"aliyun_oss_rag.{name}")


def load_env_file(path: Path | None = None) -> None:
    """Load simple KEY=VALUE pairs from .env without overriding real env vars."""
    env_path = path or PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str
    model: str
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    chunks_path: Path = PROCESSED_DIR / "chunks.jsonl"
    vector_index_path: Path = PROCESSED_DIR / "vector_index.json"
    index_path: Path = PROCESSED_DIR / "retrieval_index.json"
    documents_index_path: Path = PROCESSED_DIR / "documents_index.json"
    topics_path: Path = PROCESSED_DIR / "topics_manifest.json"
    documents_path: Path = RAW_DIR / "aliyun_oss_docs.json"

    @property
    def embedding_configured(self) -> bool:
        return bool(self.embedding_base_url and self.embedding_api_key and self.embedding_model)


def get_settings() -> Settings:
    load_env_file()
    return Settings(
        base_url=os.getenv("BASE_URL", "").strip().rstrip("/"),
        api_key=os.getenv("API_KEY", "").strip(),
        model=os.getenv("MODEL", "").strip(),
        embedding_base_url=os.getenv("EMBEDDING_BASE_URL", "").strip().rstrip("/"),
        embedding_api_key=os.getenv("EMBEDDING_API_KEY", "").strip(),
        embedding_model=os.getenv("EMBEDDING_MODEL", "").strip(),
    )
