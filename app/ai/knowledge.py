import hashlib
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.ai.chunking import TextChunk, chunk_document
from app.ai.embedding import EmbeddingError, embed_texts
from app.config import UploadSettings, get_upload_settings
from app.db.connection import get_engine
from app.db.vector import to_vector_literal

Visibility = Literal["private", "tenant", "public"]
EmbeddingFunction = Callable[[Sequence[str]], list[list[float]]]

_ACL_VALUE_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_EMBEDDING_BATCH_SIZE = 64


class KnowledgeImportError(RuntimeError):
    def __init__(self, status_code: int, error_code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class KnowledgeManagementError(RuntimeError):
    def __init__(self, status_code: int, error_code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


@dataclass(frozen=True)
class DocumentAcl:
    tenant_id: str
    owner_user_id: str
    visibility: Visibility
    allowed_roles: tuple[str, ...]


@dataclass(frozen=True)
class ImportedDocument:
    document_id: str
    filename: str
    chunk_count: int
    status: str = "processed"


@dataclass(frozen=True)
class KnowledgeDocument:
    document_id: str
    filename: str
    chunk_count: int
    visibility: str
    created_at: datetime


@dataclass(frozen=True)
class DocumentPage:
    items: tuple[KnowledgeDocument, ...]
    total: int
    page: int
    page_size: int


def parse_allowed_roles(value: str) -> tuple[str, ...]:
    roles = tuple(dict.fromkeys(role.strip() for role in value.split(",") if role.strip()))
    if len(roles) > 20 or any(not _ACL_VALUE_PATTERN.fullmatch(role) for role in roles):
        raise KnowledgeImportError(422, "INVALID_ACL", "allowed_roles contains invalid values")
    return roles


def validate_acl(acl: DocumentAcl) -> None:
    if not _ACL_VALUE_PATTERN.fullmatch(acl.tenant_id):
        raise KnowledgeImportError(422, "INVALID_ACL", "tenant_id is invalid")
    if not _ACL_VALUE_PATTERN.fullmatch(acl.owner_user_id):
        raise KnowledgeImportError(422, "INVALID_ACL", "owner_user_id is invalid")
    if acl.visibility not in {"private", "tenant", "public"}:
        raise KnowledgeImportError(422, "INVALID_ACL", "visibility is invalid")


def validate_and_decode_document(
    filename: str,
    content: bytes,
    settings: UploadSettings | None = None,
) -> tuple[str, str]:
    settings = settings or get_upload_settings()
    if not filename or Path(filename).name != filename or "/" in filename or "\\" in filename:
        raise KnowledgeImportError(400, "INVALID_FILENAME", "filename is invalid")

    file_type = Path(filename).suffix.lower()
    if file_type not in settings.allowed_extensions:
        raise KnowledgeImportError(415, "UNSUPPORTED_FILE_TYPE", "only Markdown and TXT files are supported")
    if len(content) > settings.max_size_bytes:
        raise KnowledgeImportError(413, "FILE_TOO_LARGE", "file exceeds the configured size limit")

    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise KnowledgeImportError(400, "INVALID_ENCODING", "file must be valid UTF-8 text") from exc
    if not decoded.strip():
        raise KnowledgeImportError(400, "EMPTY_DOCUMENT", "file does not contain text")
    return file_type, decoded


def import_document(
    *,
    filename: str,
    content: bytes,
    acl: DocumentAcl,
    embedder: EmbeddingFunction = embed_texts,
    engine: Engine | None = None,
    upload_settings: UploadSettings | None = None,
) -> ImportedDocument:
    validate_acl(acl)
    file_type, decoded = validate_and_decode_document(filename, content, upload_settings)
    chunks = chunk_document(decoded, file_type)
    if not chunks:
        raise KnowledgeImportError(400, "EMPTY_DOCUMENT", "file does not produce any text chunks")

    try:
        vectors = _embed_chunks(chunks, embedder)
    except EmbeddingError as exc:
        raise KnowledgeImportError(502, "EMBEDDING_UNAVAILABLE", "failed to generate document embeddings") from exc

    engine = engine or get_engine()
    document_hash = hashlib.sha256(content).hexdigest()
    try:
        with engine.begin() as connection:
            document_id = connection.execute(
                text(
                    """
                    INSERT INTO ai.documents (
                        filename, file_type, chunk_count, content_sha256, size_bytes,
                        tenant_id, owner_user_id, visibility, allowed_roles
                    ) VALUES (
                        :filename, :file_type, :chunk_count, :content_sha256, :size_bytes,
                        :tenant_id, :owner_user_id, :visibility, :allowed_roles
                    )
                    RETURNING id
                    """
                ),
                {
                    "filename": filename,
                    "file_type": file_type,
                    "chunk_count": len(chunks),
                    "content_sha256": document_hash,
                    "size_bytes": len(content),
                    "tenant_id": acl.tenant_id,
                    "owner_user_id": acl.owner_user_id,
                    "visibility": acl.visibility,
                    "allowed_roles": list(acl.allowed_roles),
                },
            ).scalar_one()

            for chunk, vector in zip(chunks, vectors, strict=True):
                connection.execute(
                    text(
                        """
                        INSERT INTO ai.document_chunks (
                            document_id, chunk_index, heading, chunk_text, content_sha256, embedding
                        ) VALUES (
                            :document_id, :chunk_index, :heading, :chunk_text, :content_sha256,
                            CAST(:embedding AS vector)
                        )
                        """
                    ),
                    {
                        "document_id": document_id,
                        "chunk_index": chunk.index,
                        "heading": chunk.heading,
                        "chunk_text": chunk.text,
                        "content_sha256": hashlib.sha256(chunk.text.encode("utf-8")).hexdigest(),
                        "embedding": to_vector_literal(vector),
                    },
                )
    except SQLAlchemyError as exc:
        raise KnowledgeImportError(503, "DATABASE_UNAVAILABLE", "failed to store the document") from exc

    return ImportedDocument(document_id=str(document_id), filename=filename, chunk_count=len(chunks))


def list_documents(
    acl: DocumentAcl,
    *,
    page: int = 1,
    page_size: int = 20,
    engine: Engine | None = None,
) -> DocumentPage:
    validate_acl(acl)
    if page < 1 or not 1 <= page_size <= 100:
        raise KnowledgeManagementError(422, "INVALID_REQUEST", "invalid pagination parameters")

    engine = engine or get_engine()
    acl_sql = """
        d.visibility = 'public'
        OR (
            d.tenant_id = :tenant_id
            AND (
                d.visibility = 'tenant'
                OR (
                    d.visibility = 'private'
                    AND (
                        d.owner_user_id = :user_id
                        OR d.allowed_roles && CAST(:roles AS text[])
                    )
                )
            )
        )
    """
    parameters = {
        "tenant_id": acl.tenant_id,
        "user_id": acl.owner_user_id,
        "roles": list(acl.allowed_roles),
    }
    try:
        with engine.connect() as connection:
            total = connection.execute(
                text(f"SELECT COUNT(*) FROM ai.documents AS d WHERE ({acl_sql})"),
                parameters,
            ).scalar_one()
            rows = connection.execute(
                text(
                    f"""
                    SELECT d.id, d.filename, d.chunk_count, d.visibility, d.created_at
                    FROM ai.documents AS d
                    WHERE ({acl_sql})
                    ORDER BY d.created_at DESC, d.id DESC
                    LIMIT :page_size OFFSET :offset
                    """
                ),
                {**parameters, "page_size": page_size, "offset": (page - 1) * page_size},
            ).mappings().all()
    except SQLAlchemyError as exc:
        raise KnowledgeManagementError(503, "DATABASE_UNAVAILABLE", "failed to list documents") from exc

    return DocumentPage(
        items=tuple(
            KnowledgeDocument(
                document_id=str(row["id"]),
                filename=row["filename"],
                chunk_count=row["chunk_count"],
                visibility=row["visibility"],
                created_at=row["created_at"],
            )
            for row in rows
        ),
        total=int(total),
        page=page,
        page_size=page_size,
    )


def delete_document(
    document_id: str,
    tenant_id: str,
    owner_user_id: str,
    *,
    engine: Engine | None = None,
) -> None:
    validate_acl(DocumentAcl(tenant_id, owner_user_id, "private", ()))
    try:
        parsed_id = str(UUID(document_id))
    except ValueError as exc:
        raise KnowledgeManagementError(404, "DOCUMENT_NOT_FOUND", "document was not found") from exc

    engine = engine or get_engine()
    try:
        with engine.begin() as connection:
            deleted_id = connection.execute(
                text(
                    """
                    DELETE FROM ai.documents
                    WHERE id = CAST(:document_id AS uuid)
                      AND tenant_id = :tenant_id
                      AND owner_user_id = :owner_user_id
                    RETURNING id
                    """
                ),
                {
                    "document_id": parsed_id,
                    "tenant_id": tenant_id,
                    "owner_user_id": owner_user_id,
                },
            ).scalar_one_or_none()
    except SQLAlchemyError as exc:
        raise KnowledgeManagementError(503, "DATABASE_UNAVAILABLE", "failed to delete document") from exc
    if deleted_id is None:
        raise KnowledgeManagementError(404, "DOCUMENT_NOT_FOUND", "document was not found")


def _embed_chunks(chunks: Sequence[TextChunk], embedder: EmbeddingFunction) -> list[list[float]]:
    vectors: list[list[float]] = []
    texts = [chunk.text for chunk in chunks]
    for start in range(0, len(texts), _EMBEDDING_BATCH_SIZE):
        batch = texts[start : start + _EMBEDDING_BATCH_SIZE]
        batch_vectors = embedder(batch)
        if len(batch_vectors) != len(batch):
            raise EmbeddingError("Embedding response count does not match chunk count")
        vectors.extend(batch_vectors)
    return vectors
