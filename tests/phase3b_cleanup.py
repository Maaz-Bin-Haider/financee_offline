"""Transactional 3B tests; run only in the disposable cleanup fixture."""
import io
import json
import os
from pathlib import Path
import sys
import time
import subprocess
from datetime import datetime, timezone
from unittest.mock import patch

if os.environ.get("PHASE3B_TEST_DISPOSABLE") != "1":
    raise SystemExit("Disposable cleanup gate only; never production")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")
import django
django.setup()
import psycopg2
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, transaction
from django.test.utils import CaptureQueriesContext
from tenancy.management.commands import serial_only_phase3_cleanup as cleanup
from tenancy.management.commands import serial_only_phase4_audit as phase4_audit
from tenancy.management.commands.serial_only_phase0_audit import _schema_structure
from tenancy.models import Company

RESULTS = []


def _discovery_refused():
    """True when the audit refuses an estate matching no recognised state."""
    try:
        phase4_audit.inspect()
    except Exception:
        return True
    return False


def check(name, ok):
    RESULTS.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}: {name}", flush=True)


def _state_refused(state):
    """True when the audit fails closed asserting `state` against the estate."""
    try:
        phase4_audit.inspect(state)
    except Exception:
        return True
    return False


def sql(text, params=None):
    with connection.cursor() as c:
        c.execute(text, params)
        return c.fetchall() if c.description else None


def snapshot():
    with connection.cursor() as c:
        data = []
        for table in ("tenancy_company", "auth_permission", "auth_user_user_permissions", "auth_group_permissions",
                      "tenancy_membership", "auth_user", "auth_group", "django_content_type"):
            c.execute(f"SELECT to_jsonb(t) FROM public.{table} t ORDER BY to_jsonb(t)::text")
            data.append([cleanup.decode(r[0]) for r in c.fetchall()])
        return cleanup.digest(data)


def inspect_inside():
    # Existing outer transactions used for fault fixtures are already read-write;
    # inspect the same state directly there, without weakening the CLI's read-only
    # transaction contract. Normal inspection below uses operate('inspect').
    with connection.cursor() as c:
        return cleanup.summary(cleanup.state(c)[0])


def mutate(action="apply", expected=None):
    return cleanup.operate(action, expected or inspect_inside()["state_sha256"], cleanup.CONFIRMATIONS[action],
                           "db-backup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))


def main():
    company = Company.objects.order_by("pk").first()
    user = get_user_model().objects.create_user(username="private-phase3b-user")
    group = Group.objects.create(name="private-phase3b-group")
    permission = Permission.objects.get(codename="view_warehouse", content_type__app_label="auth", content_type__model="user")
    user.user_permissions.add(permission)
    group.permissions.add(permission)
    ct = ContentType.objects.create(app_label="phase3b_test", model="fixture")
    other = Permission.objects.create(content_type=ct, codename="view_warehouse", name="Unrelated permission")
    user.user_permissions.add(other)
    company.disabled_features = ["stock_reports", "quantity_controls", "purchase_reports", "quantity_controls", "sales_reports.trend"]
    company.save(update_fields=["disabled_features"])
    baseline = snapshot()
    first = cleanup.operate()
    check("read-only inspection changes nothing and reveals no assignees", snapshot() == baseline
          and first["mode"] == "database-enforced-read-only" and not first["authorizes_cleanup"]
          and "private-phase3b" not in json.dumps(first) and "user_id" not in json.dumps(first))
    check("inspection selects 14 exact permissions and direct/group records", len(first["permissions"]) == 14
          and first["direct_grant_count"] == 1 and first["group_grant_count"] == 1
          and first["retired_feature_occurrences"] == 3)
    standalone = subprocess.run([sys.executable, "-", "--strict"], input=Path(cleanup.__file__).read_text(),
                                capture_output=True, text=True,
                                env={**os.environ, "PGOPTIONS": "-c default_transaction_read_only=on"})
    check("standalone source supports the unchanged strict read-only SSH transport",
          standalone.returncode == 0 and json.loads(standalone.stdout) == first)
    with transaction.atomic():
        sql("UPDATE public.tenancy_company SET disabled_features='[]'::jsonb")
        with CaptureQueriesContext(connection) as queries:
            mutate()
        check("production-like empty feature lists cause no company JSON rewrite",
              not any("UPDATE public.tenancy_company" in q["sql"] for q in queries.captured_queries))
        transaction.set_rollback(True)

    for args in (("apply", "", "", ""), ("apply", first["state_sha256"], "yes", ""),
                 ("apply", first["state_sha256"], cleanup.CONFIRMATIONS["apply"], "db-backup-20200101T000000Z")):
        blocked = False
        try:
            cleanup.operate(*args)
        except CommandError:
            blocked = True
        check("missing authorization or stale recovery reference stops before mutation", blocked and snapshot() == baseline)
    with patch.object(cleanup, "state", side_effect=lambda c: (c.execute("UPDATE public.tenancy_company SET is_active=is_active"), None)):
        blocked = False
        try:
            cleanup.operate()
        except DatabaseError as exc:
            blocked = getattr(exc.__cause__, "pgcode", None) == "25006"
        check("PostgreSQL rejects an injected write during inspect", blocked and snapshot() == baseline)

    with transaction.atomic():
        sql("INSERT INTO public.auth_user_user_permissions (user_id,permission_id) VALUES (%s,%s)",
            [user.pk, next(p["id"] for p in first["permissions"] if p["id"] != permission.pk)])
        blocked = False
        try:
            mutate(expected=first["state_sha256"])
        except CommandError:
            blocked = True
        check("a grant changed since inspection invalidates approval", blocked)
        transaction.set_rollback(True)

    negatives = {
        "custom permission label": "UPDATE public.auth_permission SET name='changed' WHERE codename='view_warehouse' AND content_type_id=" + str(permission.content_type_id),
        "wrong default": "ALTER TABLE public.tenancy_company ALTER COLUMN inventory_mode SET DEFAULT 'quantity'",
        "nullable mode": "ALTER TABLE public.tenancy_company ALTER COLUMN inventory_mode DROP NOT NULL",
        "wrong mode type": "ALTER TABLE public.tenancy_company ALTER COLUMN inventory_mode TYPE varchar(32)",
        "missing serial constraint": "ALTER TABLE public.tenancy_company DROP CONSTRAINT tenancy_company_valid_inventory_mode",
        "wrong constraint kind": "ALTER TABLE public.tenancy_company DROP CONSTRAINT tenancy_company_valid_inventory_mode; ALTER TABLE public.tenancy_company ADD CONSTRAINT tenancy_company_valid_inventory_mode UNIQUE (id)",
        "weakened serial constraint": "ALTER TABLE public.tenancy_company DROP CONSTRAINT tenancy_company_valid_inventory_mode; ALTER TABLE public.tenancy_company ADD CONSTRAINT tenancy_company_valid_inventory_mode CHECK (inventory_mode IN ('serial','quantity'))",
        "unvalidated serial constraint": "ALTER TABLE public.tenancy_company DROP CONSTRAINT tenancy_company_valid_inventory_mode; ALTER TABLE public.tenancy_company ADD CONSTRAINT tenancy_company_valid_inventory_mode CHECK (inventory_mode='serial') NOT VALID",
        "unknown view dependency": "CREATE VIEW public.phase3b_dependency AS SELECT inventory_mode FROM public.tenancy_company",
        "unknown permission FK": "CREATE TABLE public.phase3b_fk (id int REFERENCES public.auth_permission(id))",
        "unarchived permission extension": "ALTER TABLE public.auth_permission ADD COLUMN private_extension text DEFAULT 'must-not-be-lost'",
        "unreviewed permission check": "ALTER TABLE public.auth_permission ADD CONSTRAINT phase3b_extra_check CHECK(id>0)",
        "inherited permission table": "CREATE TABLE public.phase3b_permission_child () INHERITS(public.auth_permission)",
        "direct grant cascade dependency": "CREATE TABLE public.phase3b_direct_fk (id int REFERENCES public.auth_user_user_permissions(id) ON DELETE CASCADE)",
        "group grant cascade dependency": "CREATE TABLE public.phase3b_group_fk (id int REFERENCES public.auth_group_permissions(id) ON DELETE CASCADE)",
        "feature update cascade dependency": "ALTER TABLE public.tenancy_company ADD CONSTRAINT phase3b_feature_key UNIQUE(id,disabled_features); CREATE TABLE public.phase3b_feature_fk (company_id bigint,features jsonb,FOREIGN KEY(company_id,features) REFERENCES public.tenancy_company(id,disabled_features) ON UPDATE CASCADE)",
        "unknown quantity feature": "UPDATE public.tenancy_company SET disabled_features='[\"quantity_custom\"]'::jsonb",
        "archive table collision": "CREATE TABLE public.tenancy_phase3b_retirement_archive (id int)",
        "orphan schema": "CREATE SCHEMA tenant_company_987654321",
        "unexpected row security": "ALTER TABLE public.auth_permission ENABLE ROW LEVEL SECURITY",
        "unexpected trigger": "CREATE FUNCTION public.phase3b_trigger() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$; CREATE TRIGGER phase3b_unexpected BEFORE UPDATE ON public.tenancy_company FOR EACH ROW EXECUTE FUNCTION public.phase3b_trigger()",
    }
    for name, statement in negatives.items():
        with transaction.atomic():
            sql(statement)
            blocked = False
            try:
                mutate(expected=first["state_sha256"])
            except CommandError:
                blocked = True
            check("fail closed: " + name, blocked)
            transaction.set_rollback(True)
        check("failed case leaves original metadata intact: " + name, snapshot() == baseline)

    blocker = psycopg2.connect(**connection.get_connection_params())
    try:
        with blocker.cursor() as c:
            c.execute("LOCK TABLE public.tenancy_company IN ACCESS SHARE MODE")
        started = time.monotonic()
        blocked = False
        try:
            mutate(expected=first["state_sha256"])
        except DatabaseError as exc:
            blocked = getattr(exc.__cause__, "pgcode", None) == "55P03"
        check("contended company lock times out safely", blocked and 1.5 <= time.monotonic()-started < 8)
    finally:
        blocker.rollback()
        blocker.close()

    with connection.cursor() as c:
        structures = {co.schema_name: _schema_structure(c, co.schema_name) for co in Company.objects.all()}
    with transaction.atomic():
        saved_apply = cleanup.apply
        def fail_after_writes(*args):
            saved_apply(*args)
            raise CommandError("injected failure after DDL")
        blocked = False
        try:
            with patch.object(cleanup, "apply", side_effect=fail_after_writes):
                mutate(expected=first["state_sha256"])
        except CommandError:
            blocked = True
        check("failure after archive/delete/DDL rolls back the whole operation", blocked and snapshot() == baseline
              and sql("SELECT to_regclass(%s)", [cleanup.ARCHIVE]) == [(None,)])

    applied = mutate(expected=first["state_sha256"])
    check("cleanup commits physical contraction and exact retirement", applied["result"] == "PASS"
          and not applied["column_present"] and applied["archive_state"] == "applied"
          and not applied["permissions"] and applied["retired_feature_occurrences"] == 0)
    company.refresh_from_db()
    check("serial feature order and unrelated same-code permission/grant survive",
          company.disabled_features == ["stock_reports", "sales_reports.trend"]
          and Permission.objects.filter(pk=other.pk).exists() and user.user_permissions.filter(pk=other.pk).exists())
    with connection.cursor() as c:
        check("all serial schema structures are byte-equivalent", all(_schema_structure(c, n) == v for n, v in structures.items()))
        stored = cleanup.archive(c)
    check("archive round-trips original grant IDs and metadata", stored["payload"]["targets"]["direct_grants"][0]["user_id"] == user.pk
          and stored["payload"]["targets"]["group_grants"][0]["group_id"] == group.pk)
    check("archive grants no PUBLIC privileges", sql("""SELECT EXISTS (SELECT 1 FROM pg_class c,
          aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a
          WHERE c.oid=%s::regclass AND a.grantee=0)""", [cleanup.ARCHIVE]) == [(False,)])
    with transaction.atomic():
        sql("ALTER TABLE public.tenancy_phase3b_retirement_archive ADD CONSTRAINT phase3b_archive_key UNIQUE(operation_key,state)")
        sql("CREATE TABLE public.phase3b_archive_fk (operation_key text,state text,FOREIGN KEY(operation_key,state) REFERENCES public.tenancy_phase3b_retirement_archive(operation_key,state) ON UPDATE CASCADE)")
        before_attempt = snapshot()
        blocked = False
        try:
            mutate("restore", expected=applied["state_sha256"])
        except CommandError:
            blocked = True
        check("archive-state cascade dependency blocks restore without mutation", blocked and snapshot() == before_attempt)
        transaction.set_rollback(True)
    with transaction.atomic():
        sql("UPDATE public.tenancy_phase3b_retirement_archive SET payload_sha256=%s", ["0" * 64])
        blocked = False
        try:
            mutate("restore", expected=applied["state_sha256"])
        except CommandError:
            blocked = True
        check("tampered archive cannot be restored", blocked)
        transaction.set_rollback(True)
    with transaction.atomic():
        sql("UPDATE public.tenancy_company SET disabled_features='[\"stock_reports\"]'::jsonb WHERE id=%s", [company.pk])
        blocked = False
        try:
            mutate("restore")
        except CommandError:
            blocked = True
        check("restore refuses to overwrite subsequently edited features", blocked)
        transaction.set_rollback(True)
    for scenario in ("reused permission ID", "missing assignee"):
        with transaction.atomic():
            if scenario == "reused permission ID":
                sql("INSERT INTO public.auth_permission (id,content_type_id,codename,name) VALUES (%s,%s,'conflict','Unrelated conflict')",
                    [max(p["id"] for p in first["permissions"]), ct.pk])
            else:
                get_user_model().objects.filter(pk=user.pk).delete()
            before_attempt = snapshot()
            blocked = False
            try:
                mutate("restore")
            except DatabaseError as exc:
                blocked = getattr(exc.__cause__, "pgcode", None) == ("23505" if scenario == "reused permission ID" else "23503")
            check("restore rolls back without overwriting/resurrecting: " + scenario,
                  blocked and snapshot() == before_attempt)
            transaction.set_rollback(True)
    restored = mutate("restore")
    check("restore returns exact original public rows and keeps archive", snapshot() == baseline and restored["archive_state"] == "restored"
          and restored["column_present"])
    check("restore re-establishes the 3A default and serial constraint", sql("SELECT column_default FROM information_schema.columns WHERE table_schema='public' AND table_name='tenancy_company' AND column_name='inventory_mode'") == [("'serial'::character varying",)])
    reapplied = mutate()
    check("reapply reuses the immutable archive and retires exact records again", reapplied["archive_state"] == "applied")
    current = snapshot()
    check("apply is idempotent with a freshly inspected state", mutate()["archive_state"] == "applied" and snapshot() == current)
    check("strict serial continuity still passes after contraction", json.loads(capture_audit())["ready_for_phase_1"])
    phase4_entry = phase4_audit.inspect()
    check("Phase 4 entry audit accepts exact post-cleanup migration and serial state",
          phase4_entry["mode"] == "database-enforced-read-only"
          and not phase4_entry["authorizes_migration_replacement"]
          and phase4_entry["tenancy_leaf"] == "0009_inventory_mode_compatibility"
          and phase4_entry["authentication_leaf"] == "0025_add_quantity_platform_permissions"
          and phase4_entry["archive_state"] == "applied"
          and not phase4_entry["inventory_mode_column_present"]
          and phase4_entry["retired_permission_count"] == 0
          and phase4_entry["retired_feature_occurrences"] == 0)
    check("the audit discovers the pre-4A history without being told",
          phase4_entry["history_state"] == "pre-4A"
          and not phase4_entry["replacements_recorded"])
    check("asserting a different state against this estate fails closed",
          _state_refused("post-4A") and _state_refused("pruned"))

    # Checkpoint 4B precondition. Django records every replaced migration when a
    # replacement is applied and check_replacements() then records the
    # replacement itself, so a post-4A database carries both. Reproduce exactly
    # those two rows in this disposable fixture and prove the transition stage
    # accepts them while the entry stage now correctly refuses.
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO django_migrations (app, name, applied)
               VALUES ('tenancy', '0001_serial_only', now()),
                      ('authentication', '0001_serial_only', now())"""
        )
    phase4_transition = phase4_audit.inspect()
    check("the audit discovers the post-4A history without being told",
          phase4_transition["mode"] == "database-enforced-read-only"
          and phase4_transition["history_state"] == "post-4A"
          and phase4_transition["replacements_recorded"]
          and phase4_transition["replaced_rows_retained"]
          and not phase4_transition["authorizes_replaced_file_removal"]
          and phase4_transition["archive_state"] == "applied"
          and not phase4_transition["inventory_mode_column_present"]
          and phase4_transition["retired_permission_count"] == 0)
    check("asserting the superseded state now fails closed",
          _state_refused("pre-4A"))
    check("the two histories produce distinct state digests",
          phase4_transition["state_sha256"] != phase4_entry["state_sha256"])

    # The remaining states are simulated by editing django_migrations directly.
    # The audit opens its own read-only transaction, so these cannot be nested
    # inside a rolled-back block; the rows are captured first and restored in a
    # finally, and the restoration is then verified. Everything after this point
    # depends on the history being intact.
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT app, name, applied FROM django_migrations
                WHERE app IN ('tenancy','authentication') ORDER BY id"""
        )
        saved_history = cursor.fetchall()

    def restore_history():
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM django_migrations WHERE app IN ('tenancy','authentication')"
            )
            cursor.executemany(
                "INSERT INTO django_migrations (app, name, applied) VALUES (%s,%s,%s)",
                saved_history,
            )

    try:
        # Third recognised state: after a separately approved per-app prune only
        # the replacement records remain.
        with connection.cursor() as cursor:
            cursor.execute(
                """DELETE FROM django_migrations
                    WHERE app IN ('tenancy','authentication')
                      AND name <> '0001_serial_only'"""
            )
        phase4_pruned = phase4_audit.inspect()
        check("the audit discovers the pruned history without being told",
              phase4_pruned["history_state"] == "pruned"
              and phase4_pruned["replacements_recorded"]
              and not phase4_pruned["replaced_rows_retained"])
        check("all three recognised histories produce distinct digests",
              len({phase4_entry["state_sha256"], phase4_transition["state_sha256"],
                   phase4_pruned["state_sha256"]}) == 3)

        # Anything outside the three recognised shapes is drift and must fail.
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM django_migrations WHERE app='tenancy' AND name='0001_serial_only'"
            )
        check("an unrecognised migration history fails closed", _discovery_refused())
    finally:
        restore_history()
    restored = phase4_audit.inspect()
    check("the simulated states left the real migration history intact",
          restored["history_state"] == "post-4A"
          and restored["state_sha256"] == phase4_transition["state_sha256"])

    print(f"{sum(RESULTS)}/{len(RESULTS)} Phase 3B cleanup checks passed", flush=True)
    return 0 if all(RESULTS) else 1


def capture_audit():
    output = io.StringIO()
    call_command("serial_only_phase0_audit", include_continuity=True, strict_serial=True, stdout=output)
    return output.getvalue()


if __name__ == "__main__":
    raise SystemExit(main())
