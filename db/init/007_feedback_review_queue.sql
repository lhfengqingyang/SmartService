CREATE TABLE IF NOT EXISTS ai.feedback_review_queue (
    request_id UUID PRIMARY KEY REFERENCES ai.rag_feedback(request_id) ON DELETE CASCADE,
    status VARCHAR(16) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    enqueued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_feedback_review_queue_status
    ON ai.feedback_review_queue (status, enqueued_at);
