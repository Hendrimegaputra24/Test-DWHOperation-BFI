-- Raw layer: data mendarat apa adanya (append-only), tanpa logika bisnis.
-- Idempotency: pemuatan ulang file/crawl yang sama tidak membuat duplikat
-- karena ada unique key (platform, source_url, crawl_date, payload_hash)
-- dan loader memakai INSERT ... ON CONFLICT DO NOTHING.
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.crawl_product_price (
    raw_id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- metadata ingestion (diminta soal)
    platform            text        NOT NULL,
    source_url          text        NOT NULL,
    crawled_at          timestamptz NOT NULL,
    crawl_date          date GENERATED ALWAYS AS ((crawled_at AT TIME ZONE 'Asia/Jakarta')::date) STORED,
    crawler_version     text        NOT NULL,
    payload_hash        char(64)    NOT NULL,
    data_source         text        NOT NULL CHECK (data_source IN ('live', 'synthetic')),
    source_file         text,
    ingested_at         timestamptz NOT NULL DEFAULT now(),

    -- hasil crawl, sengaja tetap bertipe teks (belum dibersihkan)
    product_name        text,
    price_text          text,
    original_price_text text,
    discount_text       text,
    detail              text,
    breadcrumb          text,

    -- payload lengkap sebagaimana diterima
    raw_payload         jsonb       NOT NULL,

    CONSTRAINT uq_raw_crawl_idempotent
        UNIQUE (platform, source_url, crawl_date, payload_hash)
);

CREATE INDEX IF NOT EXISTS ix_raw_crawl_crawled_at ON raw.crawl_product_price (crawled_at);
CREATE INDEX IF NOT EXISTS ix_raw_crawl_platform   ON raw.crawl_product_price (platform, crawl_date);

COMMENT ON TABLE  raw.crawl_product_price IS 'Raw landing, append-only. Jangan diubah; pembersihan dilakukan di silver (dbt).';
COMMENT ON COLUMN raw.crawl_product_price.data_source IS 'live = hasil crawl asli, synthetic = dataset sampel buatan';
COMMENT ON COLUMN raw.crawl_product_price.payload_hash IS 'SHA-256 dari field hasil crawl (tanpa crawled_at), dasar idempotency';
