import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

APP_VERSION = "0.1.0"


@dataclass(frozen=True)
class EmbeddingSettings:
    api_key: str
    base_url: str
    model: str
    dimensions: int


@dataclass(frozen=True)
class ChunkingSettings:
    target_size: int
    max_size: int
    overlap_size: int


@dataclass(frozen=True)
class UploadSettings:
    max_size_bytes: int
    allowed_extensions: frozenset[str]


@dataclass(frozen=True)
class LlmSettings:
    api_key: str
    base_url: str
    model: str


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return database_url


def get_embedding_settings() -> EmbeddingSettings:
    api_key = os.getenv("EMBEDDING_API_KEY", "").strip()
    if not api_key or api_key.lower().startswith("your_"):
        raise RuntimeError("EMBEDDING_API_KEY is not configured")

    try:
        dimensions = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))
    except ValueError as exc:
        raise RuntimeError("EMBEDDING_DIMENSIONS must be an integer") from exc

    if not 256 <= dimensions <= 2048:
        raise RuntimeError("EMBEDDING_DIMENSIONS must be between 256 and 2048")

    return EmbeddingSettings(
        api_key=api_key,
        base_url=os.getenv("EMBEDDING_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").rstrip("/"),
        model=os.getenv("EMBEDDING_MODEL", "embedding-3"),
        dimensions=dimensions,
    )


def get_chunking_settings() -> ChunkingSettings:
    try:
        target_size = int(os.getenv("CHUNK_TARGET_SIZE", "800"))
        max_size = int(os.getenv("CHUNK_MAX_SIZE", "1200"))
        overlap_size = int(os.getenv("CHUNK_OVERLAP_SIZE", "120"))
    except ValueError as exc:
        raise RuntimeError("Chunk sizes must be integers") from exc

    if not 0 <= overlap_size < target_size <= max_size:
        raise RuntimeError("Chunk sizes must satisfy 0 <= overlap < target <= max")

    return ChunkingSettings(
        target_size=target_size,
        max_size=max_size,
        overlap_size=overlap_size,
    )


def get_upload_settings() -> UploadSettings:
    try:
        max_size_mb = int(os.getenv("UPLOAD_MAX_SIZE_MB", "10"))
    except ValueError as exc:
        raise RuntimeError("UPLOAD_MAX_SIZE_MB must be an integer") from exc
    if max_size_mb <= 0:
        raise RuntimeError("UPLOAD_MAX_SIZE_MB must be positive")

    extensions = frozenset(
        extension.strip().lower()
        for extension in os.getenv("UPLOAD_ALLOWED_EXTENSIONS", ".md,.txt").split(",")
        if extension.strip()
    )
    if not extensions:
        raise RuntimeError("UPLOAD_ALLOWED_EXTENSIONS must not be empty")

    return UploadSettings(max_size_bytes=max_size_mb * 1024 * 1024, allowed_extensions=extensions)


def get_llm_settings() -> LlmSettings:
    provider = os.getenv("LLM_PROVIDER", "zhipu").strip().lower()
    if provider == "qianwen":
        prefix = "QIANWEN"
        default_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        default_model = "qwen3.7-flash"
    elif provider == "zhipu":
        prefix = "ZHIPU"
        default_base_url = "https://open.bigmodel.cn/api/paas/v4"
        default_model = "glm-4.7-flash"
    else:
        raise RuntimeError("LLM_PROVIDER must be qianwen or zhipu")

    api_key = os.getenv(f"{prefix}_API_KEY", "").strip()
    if not api_key or api_key.lower().startswith("your_"):
        raise RuntimeError(f"{prefix}_API_KEY is not configured")
    return LlmSettings(
        api_key=api_key,
        base_url=os.getenv(f"{prefix}_BASE_URL", default_base_url).rstrip("/"),
        model=os.getenv(f"{prefix}_MODEL", default_model),
    )
