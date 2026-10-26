-- Company-scoped report email. No financial tables or calculations change.
-- Password is write-only through settings_get; backups contain the stored secret.
CREATE TABLE IF NOT EXISTS report_email_settings (
    id              integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    sender_email    text        NOT NULL,
    sender_name     text        NOT NULL DEFAULT 'Financee Reports',
    app_password    text,
    smtp_host       text        NOT NULL DEFAULT 'smtp.gmail.com',
    smtp_port       integer     NOT NULL DEFAULT 587 CHECK (smtp_port BETWEEN 1 AND 65535),
    use_tls         boolean     NOT NULL DEFAULT true,
    send_hour       smallint    NOT NULL DEFAULT 0  CHECK (send_hour BETWEEN 0 AND 23),
    send_minute     smallint    NOT NULL DEFAULT 0  CHECK (send_minute BETWEEN 0 AND 59),
    -- The business day the report is *about* is decided in this zone, not in
    -- the server's. A sale dated Monday belongs to Monday where the business
    -- is, whatever UTC says at the moment the mail goes out.
    timezone        text        NOT NULL DEFAULT 'Asia/Karachi',
    is_enabled      boolean     NOT NULL DEFAULT true,
    authorized_user_id bigint,
    updated_by      text,
    updated_at      timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS report_email_recipients (
    recipient_id bigserial PRIMARY KEY,
    email        text        NOT NULL,
    label        text,
    is_active    boolean     NOT NULL DEFAULT true,
    created_by   text,
    created_at   timestamptz NOT NULL DEFAULT clock_timestamp()
);

-- Case-insensitive, because a mailbox is: adding the same address twice in
-- different case would silently double every delivery.
CREATE UNIQUE INDEX IF NOT EXISTS report_email_recipients_email_key
    ON report_email_recipients (lower(email));

-- 19.3 Settings -------------------------------------------------------------

-- Deliberately does not select app_password. The browser never needs it, and a
-- read path that cannot leak it is worth more than one that remembers not to.
CREATE OR REPLACE FUNCTION report_email_settings_get()
    RETURNS json
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN (
        SELECT COALESCE(
            (SELECT json_build_object(
                'configured',     true,
                'authorized_user_id', s.authorized_user_id,
                'sender_email',   s.sender_email,
                'sender_name',    s.sender_name,
                'has_password',   (s.app_password IS NOT NULL AND s.app_password <> ''),
                'smtp_host',      s.smtp_host,
                'smtp_port',      s.smtp_port,
                'use_tls',        s.use_tls,
                'send_hour',      s.send_hour,
                'send_minute',    s.send_minute,
                'timezone',       s.timezone,
                'is_enabled',     s.is_enabled,
                'updated_by',     s.updated_by,
                'updated_at',     s.updated_at
             )
             FROM report_email_settings s WHERE s.id = 1),
            json_build_object('configured', false, 'is_enabled', false,
                              'smtp_host', 'smtp.gmail.com', 'smtp_port', 587,
                              'use_tls', true, 'send_hour', 0, 'send_minute', 0,
                              'timezone', 'Asia/Karachi', 'has_password', false)
        )
    );
END;
$$;

-- Every message here is written for the person typing into the form; they
-- reach the browser verbatim through financee.db_errors.user_db_error.
--
-- p_payload.app_password is optional on an update: an absent key leaves the
-- stored password alone, so the settings can be edited without retyping it.
-- An explicit empty string clears it.
CREATE OR REPLACE FUNCTION save_report_email_settings_from_json(p_payload jsonb)
    RETURNS json
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_sender    text := btrim(COALESCE(p_payload->>'sender_email', ''));
    v_name      text := btrim(COALESCE(p_payload->>'sender_name', ''));
    -- Blank or absent means Gmail, which is what this is for. A host is not
    -- something the person filling in the form should have to know.
    v_host      text := COALESCE(NULLIF(btrim(COALESCE(p_payload->>'smtp_host', '')), ''),
                                 'smtp.gmail.com');
    v_port      integer;
    v_hour      integer;
    v_minute    integer;
    v_timezone  text := btrim(COALESCE(p_payload->>'timezone', ''));
    v_actor     text := NULLIF(btrim(COALESCE(p_payload->>'actor', '')), '');
    v_existing  text;
    v_password  text;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(current_schema() || ':report_email', 0));
    IF v_sender = '' THEN
        RAISE EXCEPTION 'A sending email address is required.';
    END IF;
    IF v_sender !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' THEN
        RAISE EXCEPTION 'Sending address "%" is not a valid email address.', v_sender;
    END IF;
    IF length(v_sender) > 254 OR length(v_name) > 150 OR v_name ~ '[\r\n]' THEN
        RAISE EXCEPTION 'Invalid sender name or address length.';
    END IF;
    IF v_host ~ '[[:space:]]' THEN
        RAISE EXCEPTION 'SMTP server "%" is not a valid host name.', v_host;
    END IF;

    BEGIN
        v_port := COALESCE((p_payload->>'smtp_port')::integer, 587);
    EXCEPTION WHEN others THEN
        RAISE EXCEPTION 'SMTP port "%" is not a whole number.', p_payload->>'smtp_port';
    END;
    IF v_port < 1 OR v_port > 65535 THEN
        RAISE EXCEPTION 'SMTP port must be between 1 and 65535; % was given.', v_port;
    END IF;

    BEGIN
        v_hour := COALESCE((p_payload->>'send_hour')::integer, 0);
        v_minute := COALESCE((p_payload->>'send_minute')::integer, 0);
    EXCEPTION WHEN others THEN
        RAISE EXCEPTION 'The send time must be given as an hour and a minute.';
    END;
    IF v_hour < 0 OR v_hour > 23 THEN
        RAISE EXCEPTION 'The send hour must be between 0 and 23; % was given.', v_hour;
    END IF;
    IF v_minute < 0 OR v_minute > 59 THEN
        RAISE EXCEPTION 'The send minute must be between 0 and 59; % was given.', v_minute;
    END IF;

    IF v_timezone = '' THEN
        v_timezone := 'Asia/Karachi';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_timezone_names WHERE name = v_timezone) THEN
        RAISE EXCEPTION 'Time zone "%" is not recognised. Use a name like Asia/Karachi.', v_timezone;
    END IF;

    IF NOT ((v_port = 587 AND COALESCE((p_payload->>'use_tls')::boolean, true))
        OR (v_port = 465 AND NOT COALESCE((p_payload->>'use_tls')::boolean, true))) THEN
        RAISE EXCEPTION 'Use port 587 with TLS, or port 465 with implicit TLS.';
    END IF;

    SELECT app_password INTO v_existing FROM report_email_settings WHERE id = 1;

    IF p_payload ? 'app_password' THEN
        v_password := NULLIF(p_payload->>'app_password', '');
    ELSE
        v_password := v_existing;   -- absent key: leave what is stored alone
    END IF;

    INSERT INTO report_email_settings AS s (
        id, authorized_user_id, sender_email, sender_name, app_password, smtp_host, smtp_port,
        use_tls, send_hour, send_minute, timezone, is_enabled, updated_by, updated_at
    ) VALUES (
        1, (p_payload->>'authorized_user_id')::bigint, v_sender, COALESCE(NULLIF(v_name, ''), 'Financee Reports'), v_password,
        v_host, v_port,
        COALESCE((p_payload->>'use_tls')::boolean, true),
        v_hour, v_minute, v_timezone,
        COALESCE((p_payload->>'is_enabled')::boolean, true),
        v_actor, clock_timestamp()
    )
    ON CONFLICT (id) DO UPDATE SET
        authorized_user_id = EXCLUDED.authorized_user_id,
        sender_email = EXCLUDED.sender_email,
        sender_name  = EXCLUDED.sender_name,
        app_password = v_password,
        smtp_host    = EXCLUDED.smtp_host,
        smtp_port    = EXCLUDED.smtp_port,
        use_tls      = EXCLUDED.use_tls,
        send_hour    = EXCLUDED.send_hour,
        send_minute  = EXCLUDED.send_minute,
        timezone     = EXCLUDED.timezone,
        is_enabled   = EXCLUDED.is_enabled,
        updated_by   = EXCLUDED.updated_by,
        updated_at   = clock_timestamp();

    RETURN report_email_settings_get();
END;
$$;

-- 19.4 Recipients -----------------------------------------------------------

CREATE OR REPLACE FUNCTION report_email_recipients_list()
    RETURNS json
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN (
        SELECT COALESCE(json_agg(row_to_json(r) ORDER BY r.is_active DESC, lower(r.email)), '[]'::json)
        FROM (
            SELECT recipient_id, email, label, is_active, created_by, created_at
            FROM report_email_recipients
        ) r
    );
END;
$$;

CREATE OR REPLACE FUNCTION add_report_recipient_from_json(p_payload jsonb)
    RETURNS json
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_email text := btrim(COALESCE(p_payload->>'email', ''));
    v_label text := NULLIF(btrim(COALESCE(p_payload->>'label', '')), '');
    v_actor text := NULLIF(btrim(COALESCE(p_payload->>'actor', '')), '');
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(current_schema() || ':report_email', 0));
    IF v_email = '' THEN
        RAISE EXCEPTION 'A recipient email address is required.';
    END IF;
    IF v_email !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' THEN
        RAISE EXCEPTION '"%" is not a valid email address.', v_email;
    END IF;
    IF EXISTS (SELECT 1 FROM report_email_recipients WHERE lower(email) = lower(v_email)) THEN
        RAISE EXCEPTION '"%" is already on the recipient list.', v_email;
    END IF;

    IF (SELECT count(*) FROM report_email_recipients) >= 50 THEN
        RAISE EXCEPTION 'At most 50 recipients can be configured.';
    END IF;
    INSERT INTO report_email_recipients (email, label, created_by)
    VALUES (v_email, v_label, v_actor);

    RETURN report_email_recipients_list();
END;
$$;

CREATE OR REPLACE FUNCTION update_report_recipient_from_json(p_payload jsonb)
    RETURNS json
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_id    bigint;
    v_email text := btrim(COALESCE(p_payload->>'email', ''));
    v_label text := NULLIF(btrim(COALESCE(p_payload->>'label', '')), '');
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(current_schema() || ':report_email', 0));
    BEGIN
        v_id := (p_payload->>'recipient_id')::bigint;
    EXCEPTION WHEN others THEN
        RAISE EXCEPTION 'A recipient must be identified before it can be changed.';
    END;
    IF NOT EXISTS (SELECT 1 FROM report_email_recipients WHERE recipient_id = v_id) THEN
        RAISE EXCEPTION 'That recipient no longer exists. Refresh the page and try again.';
    END IF;

    IF v_email = '' THEN
        RAISE EXCEPTION 'A recipient email address is required.';
    END IF;
    IF v_email !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' THEN
        RAISE EXCEPTION '"%" is not a valid email address.', v_email;
    END IF;
    IF EXISTS (
        SELECT 1 FROM report_email_recipients
        WHERE lower(email) = lower(v_email) AND recipient_id <> v_id
    ) THEN
        RAISE EXCEPTION '"%" is already on the recipient list.', v_email;
    END IF;

    UPDATE report_email_recipients
    SET email = v_email,
        label = v_label,
        is_active = COALESCE((p_payload->>'is_active')::boolean, is_active)
    WHERE recipient_id = v_id;

    RETURN report_email_recipients_list();
END;
$$;

CREATE OR REPLACE FUNCTION delete_report_recipient(p_recipient_id bigint)
    RETURNS json
    LANGUAGE plpgsql
    AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(current_schema() || ':report_email', 0));
    IF NOT EXISTS (SELECT 1 FROM report_email_recipients WHERE recipient_id = p_recipient_id) THEN
        RAISE EXCEPTION 'That recipient no longer exists. Refresh the page and try again.';
    END IF;
    DELETE FROM report_email_recipients WHERE recipient_id = p_recipient_id;
    RETURN report_email_recipients_list();
END;
$$;

-- Durable reservations are made BEFORE SMTP. A session advisory lock remains
-- held across transport, so another worker cannot claim/re-arm during a send.
CREATE TABLE IF NOT EXISTS report_email_log (
    log_id bigserial PRIMARY KEY,
    report_date date NOT NULL,
    status text NOT NULL CHECK (status IN ('pending','sending','sent','failed','skipped','unknown')),
    trigger_source text NOT NULL CHECK (trigger_source IN ('schedule','manual','test','rearm')),
    recipients text[] NOT NULL DEFAULT '{}',
    subject text NOT NULL DEFAULT '',
    unit_count integer,
    total_sales numeric,
    total_profit numeric,
    currency_code text,
    error_message text NOT NULL DEFAULT '',
    triggered_by text,
    duration_ms integer,
    superseded boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS report_email_log_created_idx ON report_email_log(created_at DESC,log_id DESC);
CREATE UNIQUE INDEX IF NOT EXISTS report_email_one_live_day ON report_email_log(report_date)
    WHERE trigger_source='schedule' AND NOT superseded AND status IN ('pending','sending','sent','unknown');

CREATE OR REPLACE FUNCTION report_email_due(p_day date) RETURNS boolean
LANGUAGE sql STABLE AS $$
 SELECT EXISTS (SELECT 1 FROM report_email_settings WHERE id=1 AND is_enabled
                AND NULLIF(app_password,'') IS NOT NULL AND authorized_user_id IS NOT NULL)
    AND EXISTS (SELECT 1 FROM report_email_recipients WHERE is_active)
    AND NOT EXISTS (SELECT 1 FROM report_email_log WHERE report_date=p_day
                   AND trigger_source='schedule' AND NOT superseded
                   AND status IN ('pending','sending','sent','unknown'))
    AND (SELECT count(*) FROM report_email_log WHERE report_date=p_day
         AND trigger_source='schedule' AND NOT superseded AND status IN ('failed','skipped')) < 12
    AND NOT EXISTS (SELECT 1 FROM report_email_log WHERE report_date=p_day
                   AND trigger_source='schedule' AND NOT superseded AND status IN ('failed','skipped')
                   AND created_at > clock_timestamp()-interval '30 minutes');
$$;

CREATE OR REPLACE FUNCTION report_email_recover() RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(current_schema() || ':report_email',0));
    -- Called only after obtaining the tenant session lock: no live sender is
    -- running. Preparing cannot have sent mail; sending might have, so stop.
    UPDATE report_email_log SET status=CASE WHEN status='pending' THEN 'failed' ELSE 'unknown' END,
        error_message=CASE WHEN status='pending' THEN 'Preparation interrupted; retry allowed.'
                      ELSE 'Delivery interrupted; check the inbox before re-arming.' END,
        finished_at=clock_timestamp()
        WHERE status IN ('pending','sending');
END; $$;

CREATE OR REPLACE FUNCTION report_email_claim(p_day date,p_trigger text,p_actor text)
RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE v_id bigint;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(current_schema() || ':report_email',0));
    IF p_trigger NOT IN ('schedule','manual','test') THEN RAISE EXCEPTION 'Invalid delivery source.'; END IF;
    IF p_trigger='schedule' AND NOT report_email_due(p_day) THEN RETURN NULL; END IF;
    INSERT INTO report_email_log(report_date,status,trigger_source,triggered_by)
      VALUES(p_day,'pending',p_trigger,p_actor) RETURNING log_id INTO v_id;
    RETURN v_id;
END; $$;

CREATE OR REPLACE FUNCTION report_email_finish(p_id bigint,p_data jsonb)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    UPDATE report_email_log SET status=p_data->>'status',
      recipients=COALESCE(ARRAY(SELECT jsonb_array_elements_text(p_data->'recipients')),'{}'),
      subject=COALESCE(p_data->>'subject',''),
      unit_count=(p_data->>'unit_count')::integer,
      total_sales=(p_data->>'total_sales')::numeric,
      total_profit=(p_data->>'total_profit')::numeric,
      currency_code=p_data->>'currency_code',
      error_message=left(COALESCE(p_data->>'error_message',''),500),
      duration_ms=(p_data->>'duration_ms')::integer,
      finished_at=CASE WHEN p_data->>'status'='sending' THEN NULL ELSE clock_timestamp() END
      WHERE log_id=p_id AND status IN ('pending','sending');
END; $$;

CREATE OR REPLACE FUNCTION report_email_log_list(p_limit integer,p_offset integer)
RETURNS jsonb LANGUAGE sql STABLE AS $$
 SELECT jsonb_build_object('rows',COALESCE((SELECT jsonb_agg(to_jsonb(r)) FROM
   (SELECT * FROM report_email_log ORDER BY created_at DESC,log_id DESC
    LIMIT LEAST(100,GREATEST(1,p_limit)) OFFSET LEAST(100000,GREATEST(0,p_offset))) r),'[]'::jsonb),
   'total',(SELECT count(*) FROM report_email_log),
   'summary',(SELECT jsonb_build_object('sent',count(*) FILTER(WHERE status='sent'),
     'failed',count(*) FILTER(WHERE status='failed'),'skipped',count(*) FILTER(WHERE status='skipped'),
     'unknown',count(*) FILTER(WHERE status='unknown'),
     'last_sent_at',max(finished_at) FILTER(WHERE status='sent')) FROM report_email_log));
$$;

CREATE OR REPLACE FUNCTION rearm_report_email_day(p_day date,p_actor text)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE v_count integer;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(current_schema() || ':report_email',0));
    IF EXISTS (SELECT 1 FROM report_email_log WHERE report_date=p_day AND status IN ('pending','sending')) THEN
        RAISE EXCEPTION 'A delivery is in progress. Refresh before re-arming.';
    END IF;
    UPDATE report_email_log SET superseded=true WHERE report_date=p_day
        AND trigger_source='schedule' AND NOT superseded;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    IF v_count=0 THEN RAISE EXCEPTION 'Nothing to re-arm for this day.'; END IF;
    INSERT INTO report_email_log(report_date,status,trigger_source,triggered_by,subject,finished_at)
      VALUES(p_day,'skipped','rearm',p_actor,'Re-armed after inbox reconciliation',clock_timestamp());
    RETURN jsonb_build_object('superseded',v_count,'report_date',p_day,'due',report_email_due(p_day));
END; $$;
