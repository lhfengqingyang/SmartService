from fastapi.testclient import TestClient

from app.main import app


def test_openapi_contains_current_demo_routes_and_feedback_schema() -> None:
    schema = TestClient(app).get("/openapi.json").json()
    paths = schema["paths"]
    for path in (
        "/health",
        "/health/db",
        "/api/v1/knowledge/upload",
        "/api/v1/knowledge/documents",
        "/api/v1/chat",
        "/api/v1/chat/feedback",
        "/api/v1/agent/chat",
        "/api/v1/orders/{order_id}",
        "/api/v1/refunds/check-eligibility",
    ):
        assert path in paths
    feedback_schema = schema["components"]["schemas"]["FeedbackRequest"]
    assert {"request_id", "tenant_id", "user_id", "rating"} <= set(feedback_schema["required"])

    for route, method in (
        ("/health", "get"),
        ("/health/db", "get"),
        ("/api/v1/knowledge/upload", "post"),
        ("/api/v1/knowledge/documents", "get"),
        ("/api/v1/knowledge/documents/{document_id}", "delete"),
        ("/api/v1/chat", "post"),
        ("/api/v1/chat/feedback", "post"),
        ("/api/v1/agent/chat", "post"),
        ("/api/v1/orders/{order_id}", "get"),
        ("/api/v1/refunds/check-eligibility", "post"),
        ("/api/v1/refunds/apply", "post"),
        ("/api/v1/refunds/{refund_id}", "get"),
    ):
        success = paths[route][method]["responses"]["200"]
        assert "$ref" in success["content"]["application/json"]["schema"]
