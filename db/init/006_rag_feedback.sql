CREATE TABLE IF NOT EXISTS ai.rag_requests (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    retrieved_count INTEGER NOT NULL CHECK (retrieved_count >= 0),
    top1_score DOUBLE PRECISION,
    experiment VARCHAR(32),
    variant VARCHAR(8),
    effective_min_score DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai.rag_feedback (
    request_id UUID PRIMARY KEY REFERENCES ai.rag_requests(id) ON DELETE CASCADE,
    rating VARCHAR(16) NOT NULL CHECK (rating IN ('helpful', 'unhelpful')),
    question TEXT CHECK (question IS NULL OR length(question) <= 4000),
    comment TEXT CHECK (comment IS NULL OR length(comment) <= 1000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE ai.rag_requests ADD COLUMN IF NOT EXISTS experiment VARCHAR(32);
ALTER TABLE ai.rag_requests ADD COLUMN IF NOT EXISTS variant VARCHAR(8);
ALTER TABLE ai.rag_requests ADD COLUMN IF NOT EXISTS effective_min_score DOUBLE PRECISION NOT NULL DEFAULT 0.5;
