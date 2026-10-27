from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import get_database_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(
        get_database_url(),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )


def check_database() -> None:
    with get_engine().connect() as connection:
        ready = connection.execute(
            text(
                """
                SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')
                   AND to_regclass('ai.documents') IS NOT NULL
                   AND to_regclass('ai.document_chunks') IS NOT NULL
                   AND to_regclass('ai.rag_requests') IS NOT NULL
                   AND to_regclass('ai.rag_feedback') IS NOT NULL
                   AND to_regclass('ai.feedback_review_queue') IS NOT NULL
                   AND to_regclass('biz.orders') IS NOT NULL
                   AND to_regclass('biz.order_items') IS NOT NULL
                   AND to_regclass('biz.refund_applications') IS NOT NULL
                """
            )
        ).scalar_one()
    if not ready:
        raise RuntimeError("Database schema is incomplete")
