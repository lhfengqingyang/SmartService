from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.ai.knowledge import (
    DocumentAcl,
    KnowledgeImportError,
    KnowledgeManagementError,
    delete_document,
    import_document,
    list_documents,
    parse_allowed_roles,
)
from app.api.schemas import (
    KnowledgeDeleteResponse,
    KnowledgeDocumentPageResponse,
    KnowledgeUploadResponse,
    error_responses,
)
from app.config import get_upload_settings

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


def _management_error_response(exc: KnowledgeManagementError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc), "error_code": exc.error_code},
    )


@router.post(
    "/upload",
    response_model=KnowledgeUploadResponse,
    responses=error_responses(400, 413, 415, 502, 503),
)
async def upload_document(
    file: Annotated[UploadFile, File(description="UTF-8 Markdown or TXT document")],
    tenant_id: Annotated[str, Form(min_length=1, max_length=64)],
    owner_user_id: Annotated[str, Form(min_length=1, max_length=64)],
    visibility: Annotated[Literal["private", "tenant", "public"], Form()] = "private",
    allowed_roles: Annotated[str, Form(description="Comma-separated role names")] = "",
):
    settings = get_upload_settings()
    content = await file.read(settings.max_size_bytes + 1)
    try:
        acl = DocumentAcl(
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            visibility=visibility,
            allowed_roles=parse_allowed_roles(allowed_roles),
        )
        result = await run_in_threadpool(
            import_document,
            filename=file.filename or "",
            content=content,
            acl=acl,
            upload_settings=settings,
        )
    except KnowledgeImportError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": str(exc), "error_code": exc.error_code},
        )
    return {
        "document_id": result.document_id,
        "filename": result.filename,
        "chunk_count": result.chunk_count,
        "status": result.status,
    }


@router.get("/documents", response_model=KnowledgeDocumentPageResponse, responses=error_responses(503))
async def query_documents(
    tenant_id: Annotated[str, Query(min_length=1, max_length=64)],
    user_id: Annotated[str, Query(min_length=1, max_length=64)],
    roles: Annotated[str, Query(description="Comma-separated role names")] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    try:
        acl = DocumentAcl(tenant_id, user_id, "private", parse_allowed_roles(roles))
        result = await run_in_threadpool(
            list_documents,
            acl,
            page=page,
            page_size=page_size,
        )
    except KnowledgeImportError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": str(exc), "error_code": exc.error_code},
        )
    except KnowledgeManagementError as exc:
        return _management_error_response(exc)
    return {
        "items": [
            {
                "document_id": item.document_id,
                "filename": item.filename,
                "chunk_count": item.chunk_count,
                "visibility": item.visibility,
                "created_at": item.created_at,
            }
            for item in result.items
        ],
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
    }


@router.delete(
    "/documents/{document_id}",
    response_model=KnowledgeDeleteResponse,
    responses=error_responses(400, 403, 404, 503),
)
async def remove_document(
    document_id: str,
    tenant_id: Annotated[str, Query(min_length=1, max_length=64)],
    user_id: Annotated[str, Query(min_length=1, max_length=64)],
):
    try:
        await run_in_threadpool(delete_document, document_id, tenant_id, user_id)
    except KnowledgeImportError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": str(exc), "error_code": exc.error_code},
        )
    except KnowledgeManagementError as exc:
        return _management_error_response(exc)
    return {"deleted": True}
