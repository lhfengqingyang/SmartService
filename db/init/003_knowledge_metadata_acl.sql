ALTER TABLE ai.documents
    ADD COLUMN IF NOT EXISTS content_sha256 CHAR(64),
    ADD COLUMN IF NOT EXISTS size_bytes BIGINT,
    ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS owner_user_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS visibility VARCHAR(16),
    ADD COLUMN IF NOT EXISTS allowed_roles TEXT[];

UPDATE ai.documents
SET content_sha256 = COALESCE(content_sha256, repeat('0', 64)),
    size_bytes = COALESCE(size_bytes, 0),
    tenant_id = COALESCE(tenant_id, 'legacy'),
    owner_user_id = COALESCE(owner_user_id, 'system'),
    visibility = COALESCE(visibility, 'private'),
    allowed_roles = COALESCE(allowed_roles, '{}');

ALTER TABLE ai.documents
    ALTER COLUMN content_sha256 SET NOT NULL,
    ALTER COLUMN size_bytes SET NOT NULL,
    ALTER COLUMN tenant_id SET NOT NULL,
    ALTER COLUMN owner_user_id SET NOT NULL,
    ALTER COLUMN visibility SET NOT NULL,
    ALTER COLUMN visibility SET DEFAULT 'private',
    ALTER COLUMN allowed_roles SET NOT NULL,
    ALTER COLUMN allowed_roles SET DEFAULT '{}';

ALTER TABLE ai.documents
    DROP CONSTRAINT IF EXISTS documents_visibility_check;

ALTER TABLE ai.documents
    ADD CONSTRAINT documents_visibility_check
    CHECK (visibility IN ('private', 'tenant', 'public'));

ALTER TABLE ai.documents
    DROP CONSTRAINT IF EXISTS documents_size_bytes_check;

ALTER TABLE ai.documents
    ADD CONSTRAINT documents_size_bytes_check CHECK (size_bytes >= 0);

CREATE INDEX IF NOT EXISTS ix_documents_acl
    ON ai.documents (tenant_id, visibility, owner_user_id);

ALTER TABLE ai.document_chunks
    ADD COLUMN IF NOT EXISTS heading TEXT,
    ADD COLUMN IF NOT EXISTS content_sha256 CHAR(64);

UPDATE ai.document_chunks
SET content_sha256 = COALESCE(content_sha256, repeat('0', 64));

ALTER TABLE ai.document_chunks
    ALTER COLUMN content_sha256 SET NOT NULL;
