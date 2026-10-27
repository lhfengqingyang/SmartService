CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS ai;
CREATE SCHEMA IF NOT EXISTS biz;

CREATE TABLE IF NOT EXISTS ai.documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK (file_type IN ('.md', '.txt')),
    chunk_count INTEGER NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
    content_sha256 CHAR(64) NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    tenant_id VARCHAR(64) NOT NULL,
    owner_user_id VARCHAR(64) NOT NULL,
    visibility VARCHAR(16) NOT NULL DEFAULT 'private'
        CHECK (visibility IN ('private', 'tenant', 'public')),
    allowed_roles TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_documents_acl
    ON ai.documents (tenant_id, visibility, owner_user_id);

CREATE TABLE IF NOT EXISTS ai.document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES ai.documents (id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    heading TEXT,
    chunk_text TEXT NOT NULL CHECK (length(btrim(chunk_text)) > 0),
    content_sha256 CHAR(64) NOT NULL,
    embedding vector(1024) NOT NULL,
    UNIQUE (document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS biz.orders (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('pending', 'paid', 'shipped', 'completed', 'cancelled')),
    total_amount NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ,
    CHECK (delivered_at IS NULL OR status = 'completed')
);

CREATE TABLE IF NOT EXISTS biz.order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id VARCHAR(64) NOT NULL REFERENCES biz.orders (id) ON DELETE CASCADE,
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0)
);

CREATE TABLE IF NOT EXISTS biz.refund_applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id VARCHAR(64) NOT NULL REFERENCES biz.orders (id),
    user_id VARCHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
    reason TEXT NOT NULL CHECK (length(btrim(reason)) > 0),
    idempotency_key VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_refund_applications_order
    ON biz.refund_applications (order_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_refund_applications_idempotency
    ON biz.refund_applications (user_id, idempotency_key);
