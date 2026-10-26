-- Company activity is separate from public auth and the optional platform log.
-- Additive, repeatable, version 6 compatible. Backfill is an explicit command.
CREATE TABLE IF NOT EXISTS activity_events (
    event_id bigserial PRIMARY KEY,
    at timestamptz NOT NULL DEFAULT clock_timestamp(),
    user_id integer,
    username text NOT NULL DEFAULT '',
    action text NOT NULL CHECK (action IN ('create','update','delete','convert','cancel','release','run','export','sign_in','sign_out','sign_in_failed')),
    kind text NOT NULL CHECK (kind IN ('sale','purchase','sale_return','purchase_return','payment','receipt','contra','draft','draft_return','party','item','opening_stock','opening_cash','owner_equity','month_close','report','session')),
    record_id bigint,
    label text NOT NULL DEFAULT '',
    source text NOT NULL DEFAULT 'live' CHECK (source IN ('live','browser','backfill')),
    ip inet,
    dedupe_key text,
    document_date date,
    CHECK (length(username) <= 150 AND length(label) <= 200),
    CHECK (record_id IS NULL OR record_id > 0)
);
CREATE INDEX IF NOT EXISTS activity_events_user_at_idx ON activity_events(user_id,at);
CREATE INDEX IF NOT EXISTS activity_events_at_idx ON activity_events(at);
CREATE INDEX IF NOT EXISTS activity_events_record_idx ON activity_events(kind,record_id);
CREATE INDEX IF NOT EXISTS activity_events_sign_in_idx ON activity_events(user_id,at) WHERE action='sign_in';
CREATE INDEX IF NOT EXISTS activity_events_dedupe_idx ON activity_events(user_id,dedupe_key,at) WHERE dedupe_key IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS activity_events_backfill_key ON activity_events(dedupe_key) WHERE source='backfill';
CREATE OR REPLACE FUNCTION activity_events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'activity_events is append-only: % refused', TG_OP;
END;
$$;
CREATE OR REPLACE TRIGGER activity_events_no_change BEFORE UPDATE OR DELETE ON activity_events
FOR EACH ROW EXECUTE FUNCTION activity_events_append_only();
CREATE OR REPLACE TRIGGER activity_events_no_truncate BEFORE TRUNCATE ON activity_events
FOR EACH STATEMENT EXECUTE FUNCTION activity_events_append_only();
