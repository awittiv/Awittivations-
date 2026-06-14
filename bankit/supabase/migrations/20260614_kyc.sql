-- KYC documents table: tracks uploaded documents per merchant
CREATE TABLE IF NOT EXISTS kyc_documents (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id   UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    doc_type      TEXT NOT NULL CHECK (doc_type IN ('aadhaar', 'pan', 'gst')),
    storage_path  TEXT NOT NULL,
    file_name     TEXT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (merchant_id, doc_type)
);

ALTER TABLE kyc_documents ENABLE ROW LEVEL SECURITY;

-- Merchants can read their own submitted docs
CREATE POLICY "kyc_docs_merchant_read" ON kyc_documents
    FOR SELECT TO authenticated
    USING (merchant_id IN (
        SELECT id FROM merchants WHERE user_id = auth.uid()
    ));

-- Merchants can insert their own docs (upsert via service role from backend)
CREATE POLICY "kyc_docs_merchant_insert" ON kyc_documents
    FOR INSERT TO authenticated
    WITH CHECK (merchant_id IN (
        SELECT id FROM merchants WHERE user_id = auth.uid()
    ));

-- ─── Storage bucket ──────────────────────────────────────────────────────────
-- Run as service role. Creates the private kyc-docs bucket if it doesn't exist.
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'kyc-docs',
    'kyc-docs',
    false,
    5242880,
    ARRAY['image/jpeg', 'image/png', 'image/webp', 'application/pdf']
)
ON CONFLICT (id) DO NOTHING;

-- Merchants can upload to their own subfolder: kyc-docs/{merchant_id}/...
CREATE POLICY "kyc_storage_merchant_upload" ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (
        bucket_id = 'kyc-docs' AND
        (storage.foldername(name))[1] IN (
            SELECT id::text FROM public.merchants WHERE user_id = auth.uid()
        )
    );

-- Merchants can read their own files
CREATE POLICY "kyc_storage_merchant_read" ON storage.objects
    FOR SELECT TO authenticated
    USING (
        bucket_id = 'kyc-docs' AND
        (storage.foldername(name))[1] IN (
            SELECT id::text FROM public.merchants WHERE user_id = auth.uid()
        )
    );

-- Merchants can replace (upsert) their own files
CREATE POLICY "kyc_storage_merchant_update" ON storage.objects
    FOR UPDATE TO authenticated
    USING (
        bucket_id = 'kyc-docs' AND
        (storage.foldername(name))[1] IN (
            SELECT id::text FROM public.merchants WHERE user_id = auth.uid()
        )
    );
