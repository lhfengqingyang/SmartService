from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai.knowledge import (
    DocumentPage,
    ImportedDocument,
    KnowledgeDocument,
    KnowledgeImportError,
    parse_allowed_roles,
    validate_and_decode_document,
)
from app.config import UploadSettings
from app.main import app

client = TestClient(app)
FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"
TEST_SETTINGS = UploadSettings(max_size_bytes=100, allowed_extensions=frozenset({".md", ".txt"}))


def test_upload_document_returns_processed_result(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import knowledge

    def fake_import_document(**kwargs) -> ImportedDocument:
        assert kwargs["acl"].tenant_id == "tenant-a"
        assert kwargs["acl"].owner_user_id == "user-1"
        assert kwargs["acl"].allowed_roles == ("support", "admin")
        return ImportedDocument(
            document_id="00000000-0000-0000-0000-000000000001",
            filename=kwargs["filename"],
            chunk_count=3,
        )

    monkeypatch.setattr(knowledge, "import_document", fake_import_document)
    content = (FIXTURES / "refund_policy.md").read_bytes()
    response = client.post(
        "/api/v1/knowledge/upload",
        files={"file": ("refund_policy.md", content, "text/markdown")},
        data={
            "tenant_id": "tenant-a",
            "owner_user_id": "user-1",
            "visibility": "private",
            "allowed_roles": "support,admin,support",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "document_id": "00000000-0000-0000-0000-000000000001",
        "filename": "refund_policy.md",
        "chunk_count": 3,
        "status": "processed",
    }


def test_validate_document_rejects_path_traversal() -> None:
    with pytest.raises(KnowledgeImportError, match="filename is invalid") as exc_info:
        validate_and_decode_document("../policy.md", b"content", TEST_SETTINGS)

    assert exc_info.value.error_code == "INVALID_FILENAME"


def test_validate_document_rejects_unsupported_extension() -> None:
    with pytest.raises(KnowledgeImportError, match="only Markdown and TXT") as exc_info:
        validate_and_decode_document("policy.pdf", b"content", TEST_SETTINGS)

    assert exc_info.value.status_code == 415
    assert exc_info.value.error_code == "UNSUPPORTED_FILE_TYPE"


def test_validate_document_rejects_oversized_file() -> None:
    with pytest.raises(KnowledgeImportError) as exc_info:
        validate_and_decode_document("policy.txt", b"x" * 101, TEST_SETTINGS)

    assert exc_info.value.status_code == 413
    assert exc_info.value.error_code == "FILE_TOO_LARGE"


def test_validate_document_rejects_non_utf8_file() -> None:
    with pytest.raises(KnowledgeImportError) as exc_info:
        validate_and_decode_document("policy.txt", b"\xff\xfe", TEST_SETTINGS)

    assert exc_info.value.error_code == "INVALID_ENCODING"


def test_parse_allowed_roles_deduplicates_and_validates() -> None:
    assert parse_allowed_roles("support, admin, support") == ("support", "admin")

    with pytest.raises(KnowledgeImportError) as exc_info:
        parse_allowed_roles("support,not allowed")
    assert exc_info.value.error_code == "INVALID_ACL"


def test_list_documents_returns_acl_visible_page(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import knowledge

    captured = {}

    def fake_list(acl, *, page, page_size):
        captured.update(acl=acl, page=page, page_size=page_size)
        return DocumentPage(
            items=(
                KnowledgeDocument(
                    document_id="00000000-0000-0000-0000-000000000001",
                    filename="policy.md",
                    chunk_count=2,
                    visibility="private",
                    created_at=datetime(2026, 10, 26, tzinfo=UTC),
                ),
            ),
            total=1,
            page=2,
            page_size=10,
        )

    monkeypatch.setattr(knowledge, "list_documents", fake_list)
    response = client.get(
        "/api/v1/knowledge/documents",
        params={
            "tenant_id": "tenant-a",
            "user_id": "user-1",
            "roles": "support,admin",
            "page": 2,
            "page_size": 10,
        },
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["filename"] == "policy.md"
    assert response.json()["total"] == 1
    assert captured["acl"].allowed_roles == ("support", "admin")
    assert (captured["page"], captured["page_size"]) == (2, 10)


def test_delete_document_passes_owner_context(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import knowledge

    calls = []
    monkeypatch.setattr(
        knowledge,
        "delete_document",
        lambda document_id, tenant_id, user_id: calls.append((document_id, tenant_id, user_id)),
    )
    document_id = "00000000-0000-0000-0000-000000000001"
    response = client.delete(
        f"/api/v1/knowledge/documents/{document_id}",
        params={"tenant_id": "tenant-a", "user_id": "user-1"},
    )

    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert calls == [(document_id, "tenant-a", "user-1")]
