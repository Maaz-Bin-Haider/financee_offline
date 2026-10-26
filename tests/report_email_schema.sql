-- Run with psql ON_ERROR_STOP in a disposable tenant after add_report_email.sql.
BEGIN;
DO $$
DECLARE settings json; attempt bigint;
BEGIN
    settings := save_report_email_settings_from_json('{"sender_email":"a@example.test","app_password":"test-secret","authorized_user_id":1}');
    IF settings::text LIKE '%test-secret%' THEN RAISE EXCEPTION 'Secret exposed'; END IF;
    PERFORM add_report_recipient_from_json('{"email":"owner@example.test"}');
    IF NOT report_email_due('2026-01-01') THEN RAISE EXCEPTION 'Configured day not due'; END IF;
    attempt := report_email_claim('2026-01-01','schedule','tester');
    IF attempt IS NULL OR report_email_claim('2026-01-01','schedule','tester') IS NOT NULL THEN
        RAISE EXCEPTION 'Duplicate reservation';
    END IF;
    PERFORM report_email_finish(attempt,'{"status":"sending"}');
    PERFORM report_email_recover();
    IF report_email_due('2026-01-01') THEN RAISE EXCEPTION 'Uncertain delivery retried'; END IF;
    IF NOT EXISTS(SELECT 1 FROM report_email_log WHERE log_id=attempt AND status='unknown') THEN
        RAISE EXCEPTION 'Crash evidence lost';
    END IF;
    PERFORM rearm_report_email_day('2026-01-01','tester');
    IF NOT report_email_due('2026-01-01') THEN RAISE EXCEPTION 'Rearm not due'; END IF;
    attempt := report_email_claim('2026-01-01','schedule','tester');
    PERFORM report_email_finish(attempt,'{"status":"failed"}');
    IF report_email_due('2026-01-01') THEN RAISE EXCEPTION 'Retry gap absent'; END IF;
    IF NOT EXISTS(SELECT 1 FROM report_email_log WHERE superseded AND status='unknown') THEN
        RAISE EXCEPTION 'Historical evidence lost';
    END IF;
    RAISE NOTICE 'PASS: secrets, durable claims, crash recovery, retry spacing, rearm and preserved evidence';
END $$;
ROLLBACK;
