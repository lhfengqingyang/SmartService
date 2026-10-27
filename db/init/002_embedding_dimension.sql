ALTER TABLE ai.document_chunks
    ALTER COLUMN embedding TYPE vector(1024)
    USING embedding::vector(1024);
