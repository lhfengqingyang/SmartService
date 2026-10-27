ALTER TABLE biz.orders
    ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ;

ALTER TABLE biz.refund_applications
    ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(128);

UPDATE biz.refund_applications
SET idempotency_key = 'legacy-' || id::text
WHERE idempotency_key IS NULL;

ALTER TABLE biz.refund_applications
    ALTER COLUMN idempotency_key SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_refund_applications_order
    ON biz.refund_applications (order_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_refund_applications_idempotency
    ON biz.refund_applications (user_id, idempotency_key);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_orders_delivered_status'
    ) THEN
        ALTER TABLE biz.orders
            ADD CONSTRAINT ck_orders_delivered_status
            CHECK (delivered_at IS NULL OR status = 'completed');
    END IF;
END $$;
