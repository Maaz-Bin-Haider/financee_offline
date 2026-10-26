CREATE TABLE IF NOT EXISTS document_attachments (
    attachment_id BIGSERIAL PRIMARY KEY,
    document_type TEXT NOT NULL,
    document_id BIGINT NOT NULL,
    file_kind TEXT NOT NULL,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    content_type TEXT NOT NULL,
    file_size BIGINT NOT NULL,
    uploaded_by INTEGER NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT document_attachments_document_type_check CHECK (
        document_type IN ('sale', 'purchase', 'sale_return', 'purchase_return', 'payment', 'receipt', 'contra')
    ),
    CONSTRAINT document_attachments_file_kind_check CHECK (file_kind IN ('image', 'pdf')),
    CONSTRAINT document_attachments_file_size_check CHECK (file_size > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS document_attachments_one_per_kind
    ON document_attachments (document_type, document_id, file_kind);

CREATE INDEX IF NOT EXISTS document_attachments_document_idx
    ON document_attachments (document_type, document_id);
