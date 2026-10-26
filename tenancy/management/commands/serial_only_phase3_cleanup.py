"""Explicit, reversible 3B maintenance; never called by app startup.

Inspect is database-enforced read-only. Apply/restore require an exact inspected
state digest, typed confirmation and recent managed backup reference. Production
transport must additionally verify that backup/restore and the deployed image.
No customer names or grant assignees are emitted. The archive stays in the
protected database and is never deleted by this command.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

PERMISSIONS = {
    "view_warehouse": "Can view quantity warehouses",
    "create_warehouse": "Can create quantity warehouses",
    "update_warehouse": "Can update quantity warehouses",
    "delete_warehouse": "Can delete unreferenced quantity warehouses",
    "view_warehouse_transfer": "Can view quantity warehouse transfers",
    "create_warehouse_transfer": "Can create quantity warehouse transfers",
    "update_warehouse_transfer": "Can update quantity warehouse transfers",
    "delete_warehouse_transfer": "Can reverse quantity warehouse transfers",
    "view_physical_count": "Can view quantity physical counts",
    "create_physical_count": "Can create quantity physical counts",
    "approve_inventory_adjustment": "Can approve and post inventory adjustments",
    "reverse_inventory_adjustment": "Can reverse posted inventory adjustments",
    "view_quantity_audit": "Can view quantity audit events",
    "manage_quantity_attachments": "Can manage quantity document attachments",
}
FEATURES = frozenset({"purchase_reports", "quantity_controls", "quantity_controls.warehouses",
                      "quantity_controls.transfers", "quantity_controls.counts",
                      "quantity_controls.tax", "quantity_controls.audit"})
ARCHIVE = "public.tenancy_phase3b_retirement_archive"
MARKER = "financee-serial-only-phase3b-archive-v1"
KEY = "serial-only-phase3b-v1"
CONFIRMATIONS = {"apply": "APPLY-PHASE3B-REVIEWED-METADATA", "restore": "RESTORE-PHASE3B-ARCHIVED-METADATA"}


def require(ok, message):
    if not ok:
        raise CommandError("3B blocked: " + message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def rows(cursor, query, params=None):
    cursor.execute(query, params)
    names = [col[0] for col in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def decode(value):
    return json.loads(value) if isinstance(value, str) else value


def archive(cursor):
    cursor.execute("SELECT to_regclass(%s)", [ARCHIVE])
    if cursor.fetchone()[0] is None:
        return None
    cursor.execute("SELECT obj_description(%s::regclass, 'pg_class')", [ARCHIVE])
    require(cursor.fetchone()[0] == MARKER, "archive name collision or unknown format")
    cursor.execute("""SELECT attname, format_type(atttypid, atttypmod), attnotnull
        FROM pg_attribute WHERE attrelid=%s::regclass AND attnum>0 AND NOT attisdropped ORDER BY attnum""", [ARCHIVE])
    require(cursor.fetchall() == [("operation_key", "text", True), ("payload", "jsonb", True),
                                  ("payload_sha256", "text", True), ("state", "text", True),
                                  ("created_at", "timestamp with time zone", True)], "unexpected archive columns")
    data = rows(cursor, f"SELECT operation_key, payload, payload_sha256, state FROM {ARCHIVE}")
    require(len(data) == 1, "archive must have exactly one retained operation")
    value = data[0]
    value["payload"] = decode(value["payload"])
    require(value["operation_key"] == KEY and value["state"] in ("applied", "restored")
            and value["payload"].get("version") == 1
            and digest(value["payload"]) == value["payload_sha256"], "archive checksum/state mismatch")
    return value


def column_contract(cursor):
    data = rows(cursor, """SELECT a.attnum, format_type(a.atttypid,a.atttypmod) AS type,
        a.attnotnull, a.attidentity, a.attgenerated, a.attinhcount, a.attislocal,
        a.attcollation = t.typcollation AS default_collation, d.oid AS default_oid,
        pg_get_expr(d.adbin,d.adrelid) AS default_value
        FROM pg_attribute a JOIN pg_type t ON t.oid=a.atttypid
        LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
        WHERE a.attrelid='public.tenancy_company'::regclass AND a.attname='inventory_mode' AND NOT a.attisdropped""")
    if not data:
        cursor.execute("""SELECT count(*) FROM pg_constraint WHERE conrelid='public.tenancy_company'::regclass
                          AND conname='tenancy_company_valid_inventory_mode'""")
        require(cursor.fetchone()[0] == 0, "mode constraint survives an absent column")
        return None
    col = data[0]
    require(col["type"] == "character varying(16)" and col["attnotnull"]
            and col["default_value"] == "'serial'::character varying" and col["default_oid"]
            and col["attidentity"] == "" and col["attgenerated"] == "" and col["attinhcount"] == 0
            and col["attislocal"] and col["default_collation"], "unexpected inventory-mode column contract")
    cursor.execute("""SELECT oid, contype, convalidated, connoinherit, pg_get_expr(conbin, conrelid)
        FROM pg_constraint WHERE conrelid='public.tenancy_company'::regclass
        AND conname='tenancy_company_valid_inventory_mode'""")
    constraint = cursor.fetchone()
    require(constraint and constraint[1:4] == ("c", True, False), "validated exact serial constraint required")
    expression = "".join(constraint[4].replace("(", "").replace(")", "").split())
    require(expression == "inventory_mode::text='serial'::text", "unexpected serial constraint expression")
    cursor.execute("""SELECT d.classid::regclass::text, d.objid, d.objsubid, d.deptype
        FROM pg_depend d WHERE d.refclassid='pg_class'::regclass
        AND d.refobjid='public.tenancy_company'::regclass AND d.refobjsubid=%s""", [col["attnum"]])
    actual = cursor.fetchall()
    expected = {("pg_attrdef", col["default_oid"], 0, "a"),
                ("pg_constraint", constraint[0], 0, "a"), ("pg_constraint", constraint[0], 0, "n")}
    require(len(actual) == 3 and set(actual) == expected, "unexpected inventory-mode dependency")
    cursor.execute("""SELECT EXISTS (SELECT 1 FROM pg_inherits
        WHERE inhrelid='public.tenancy_company'::regclass OR inhparent='public.tenancy_company'::regclass)""")
    require(not cursor.fetchone()[0], "company table inheritance is not supported")
    return {"column": col, "constraint_oid": constraint[0]}


def permission_dependencies(cursor):
    # Archive/restore serializes these exact Django fields. Unknown columns,
    # types, inheritance or custom checks cannot be silently discarded or run.
    contracts = {
        "public.auth_permission": {"id": "integer", "name": "character varying(255)",
                                   "content_type_id": "integer", "codename": "character varying(100)"},
        "public.auth_user_user_permissions": {"id": "bigint", "user_id": "integer", "permission_id": "integer"},
        "public.auth_group_permissions": {"id": "bigint", "group_id": "integer", "permission_id": "integer"},
    }
    for table, expected in contracts.items():
        cursor.execute("""SELECT attname,format_type(atttypid,atttypmod),attnotnull FROM pg_attribute
            WHERE attrelid=%s::regclass AND attnum>0 AND NOT attisdropped""", [table])
        columns = cursor.fetchall()
        require({name: kind for name, kind, _ in columns} == expected and all(required for _, _, required in columns),
                "unexpected permission/assignment table columns")
    cursor.execute("""SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid=ANY(%s::regclass[])
        AND contype NOT IN ('p','u','f')) OR EXISTS (SELECT 1 FROM pg_inherits
        WHERE inhrelid=ANY(%s::regclass[]) OR inhparent=ANY(%s::regclass[]))""", [list(contracts)] * 3)
    require(not cursor.fetchone()[0], "unexpected permission/assignment check or inheritance")
    cursor.execute("""SELECT c.conrelid::regclass::text,
        ARRAY(SELECT a.attname::text FROM unnest(c.conkey) WITH ORDINALITY x(n,i)
              JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=x.n ORDER BY x.i),
        ARRAY(SELECT a.attname::text FROM unnest(c.confkey) WITH ORDINALITY x(n,i)
              JOIN pg_attribute a ON a.attrelid=c.confrelid AND a.attnum=x.n ORDER BY x.i)
        FROM pg_constraint c WHERE c.contype='f' AND c.confrelid='public.auth_permission'::regclass""")
    dependencies = cursor.fetchall()
    require(len(dependencies) == 2 and {(t, tuple(a), tuple(b)) for t, a, b in dependencies} == {
        ("auth_user_user_permissions", ("permission_id",), ("id",)),
        ("auth_group_permissions", ("permission_id",), ("id",)),
    }, "unexpected permission foreign-key dependency")


def registry(cursor, has_column):
    mode = "inventory_mode" if has_column else "'serial'::text AS inventory_mode"
    values = rows(cursor, f"SELECT id, schema_name, provisioning_state, disabled_features, {mode} FROM public.tenancy_company ORDER BY id")
    require(values, "empty registry requires separate review")
    schemas = set()
    for value in values:
        schema = value.pop("schema_name")
        require(schema == f"tenant_company_{value['id']}" and value.pop("provisioning_state") == "ready"
                and value["inventory_mode"] == "serial", "registry is not canonical ready serial-only")
        schemas.add(schema)
        value["disabled_features"] = decode(value["disabled_features"])
        features = value["disabled_features"]
        require(isinstance(features, list) and all(isinstance(k, str) for k in features), "invalid feature list")
        require(not any(k.startswith(("quantity", "purchase_reports.")) and k not in FEATURES for k in features),
                "unclassified legacy feature key")
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=%s AND table_type='BASE TABLE'", [schema])
        tables = {r[0] for r in cursor.fetchall()}
        require("tenant_schema_version" in tables and "tenant_schema_metadata" not in tables, "non-serial tenant structure")
        cursor.execute(f"SELECT version FROM {connection.ops.quote_name(schema)}.tenant_schema_version WHERE id=true")
        require(cursor.fetchone() == (6,), "tenant is not serial version 6")
    cursor.execute("SELECT nspname FROM pg_namespace WHERE nspname ~ '^tenant_company_'")
    require({r[0] for r in cursor.fetchall()} == schemas, "orphan or unexpected tenant schema; no schema deletion allowed")
    return values


def state(cursor):
    stored = archive(cursor)
    # Custom triggers/rules/RLS could hide rows or cause side effects beyond the
    # reviewed SQL. Do not silently execute through such an extension.
    tables = ["public.tenancy_company", "public.auth_permission", "public.auth_user_user_permissions",
              "public.auth_group_permissions"] + ([ARCHIVE] if stored else [])
    cursor.execute("SELECT bool_and(relkind='r' AND NOT relrowsecurity) FROM pg_class WHERE oid=ANY(%s::regclass[])", [tables])
    require(cursor.fetchone()[0] is True, "unexpected table kind or row security")
    cursor.execute("SELECT count(*) FROM pg_trigger WHERE tgrelid=ANY(%s::regclass[]) AND NOT tgisinternal", [tables])
    require(cursor.fetchone()[0] == 0, "unreviewed metadata trigger")
    cursor.execute("SELECT count(*) FROM pg_rewrite WHERE ev_class=ANY(%s::regclass[])", [tables])
    require(cursor.fetchone()[0] == 0, "unreviewed metadata rule")
    # Internal FK triggers are not custom triggers. Reject unreviewed incoming
    # references that could cascade assignment deletion or archive-state changes.
    cursor.execute("""SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE contype='f'
        AND confrelid=ANY(%s::regclass[]))""", [tables[2:]])
    require(not cursor.fetchone()[0], "unexpected assignment/archive foreign-key dependency")
    cursor.execute("""SELECT EXISTS (SELECT 1 FROM pg_constraint c JOIN pg_attribute a
        ON a.attrelid=c.confrelid AND a.attnum=ANY(c.confkey)
        WHERE c.contype='f' AND c.confrelid='public.tenancy_company'::regclass
        AND a.attname='disabled_features' AND NOT a.attisdropped)""")
    require(not cursor.fetchone()[0], "unexpected feature-list foreign-key dependency")
    col = column_contract(cursor)
    permission_dependencies(cursor)
    companies = registry(cursor, col is not None)
    permissions = rows(cursor, """SELECT p.id, p.content_type_id, p.codename, p.name FROM public.auth_permission p
        JOIN public.django_content_type ct ON ct.id=p.content_type_id
        WHERE ct.app_label='auth' AND ct.model='user' AND p.codename=ANY(%s) ORDER BY p.id""", [list(PERMISSIONS)])
    require(all(p["name"] == PERMISSIONS[p["codename"]] for p in permissions), "customized permission label")
    ids = [p["id"] for p in permissions]
    direct = rows(cursor, "SELECT id,user_id,permission_id FROM public.auth_user_user_permissions WHERE permission_id=ANY(%s) ORDER BY id", [ids])
    groups = rows(cursor, "SELECT id,group_id,permission_id FROM public.auth_group_permissions WHERE permission_id=ANY(%s) ORDER BY id", [ids])
    targets = {"permissions": permissions, "direct_grants": direct, "group_grants": groups, "companies": companies}
    require(len(json.dumps(targets)) <= 1024 * 1024, "metadata exceeds reviewed bounded archive size")
    applied = stored and stored["state"] == "applied"
    if applied:
        require(col is None and not permissions and not any(set(c["disabled_features"]) & FEATURES for c in companies),
                "applied cleanup state has drifted")
    else:
        require(col is not None and {p["codename"] for p in permissions} == set(PERMISSIONS)
                and len(permissions) == 14, "expected complete legacy metadata before cleanup")
    value = {"targets": targets, "column": col,
             "archive": None if not stored else {"sha256": stored["payload_sha256"], "state": stored["state"]}}
    return value, stored


def summary(value):
    targets = value["targets"]
    return {"state_sha256": digest(value), "authorizes_cleanup": False,
            "archive_state": (value["archive"] or {}).get("state", "absent"),
            "column_present": value["column"] is not None, "company_count": len(targets["companies"]),
            "permissions": [{"id": p["id"], "codename": p["codename"]} for p in targets["permissions"]],
            "direct_grant_count": len(targets["direct_grants"]), "group_grant_count": len(targets["group_grants"]),
            "retired_feature_occurrences": sum(k in FEATURES for c in targets["companies"] for k in c["disabled_features"])}


def preserved(cursor):
    data = {}
    # Exclude only the reviewed legacy field/features. Shared company fields,
    # unrelated permissions/grants and all account/membership records stay exact.
    cursor.execute("SELECT to_jsonb(c)-'inventory_mode'-'disabled_features' FROM public.tenancy_company c ORDER BY id")
    data["companies"] = [decode(r[0]) for r in cursor.fetchall()]
    cursor.execute("SELECT id,disabled_features FROM public.tenancy_company ORDER BY id")
    data["preserved_features"] = [(pk, [k for k in decode(features) if k not in FEATURES]) for pk, features in cursor.fetchall()]
    cursor.execute("""SELECT p.id FROM public.auth_permission p JOIN public.django_content_type ct ON ct.id=p.content_type_id
        WHERE ct.app_label='auth' AND ct.model='user' AND p.codename=ANY(%s)""", [list(PERMISSIONS)])
    ids = [r[0] for r in cursor.fetchall()]
    for table, predicate in (("auth_permission", "id"), ("auth_user_user_permissions", "permission_id"),
                             ("auth_group_permissions", "permission_id")):
        cursor.execute(f"SELECT to_jsonb(t) FROM public.{table} t WHERE NOT ({predicate}=ANY(%s)) ORDER BY id", [ids])
        data[table] = [decode(r[0]) for r in cursor.fetchall()]
    for table in ("tenancy_currency", "tenancy_membership", "auth_user", "auth_group", "django_content_type"):
        cursor.execute(f"SELECT to_jsonb(t) FROM public.{table} t ORDER BY to_jsonb(t)::text")
        data[table] = [decode(r[0]) for r in cursor.fetchall()]
    return digest(data)


def make_archive(cursor, payload):
    cursor.execute(f"""CREATE TABLE {ARCHIVE} (
        operation_key text PRIMARY KEY, payload jsonb NOT NULL, payload_sha256 text NOT NULL,
        state text NOT NULL CHECK (state IN ('applied','restored')),
        created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute(f"COMMENT ON TABLE {ARCHIVE} IS %s", [MARKER])
    cursor.execute(f"REVOKE ALL ON TABLE {ARCHIVE} FROM PUBLIC")
    cursor.execute(f"INSERT INTO {ARCHIVE} (operation_key,payload,payload_sha256,state) VALUES (%s,%s::jsonb,%s,'applied')",
                   [KEY, json.dumps(payload), digest(payload)])


def apply(cursor, value, stored, backup_release):
    if stored and stored["state"] == "applied":
        return
    targets = value["targets"]
    if stored:
        require(stored["payload"]["targets"] == targets, "restored metadata changed; archive cannot be overwritten")
        cursor.execute(f"UPDATE {ARCHIVE} SET state='applied' WHERE operation_key=%s", [KEY])
    else:
        make_archive(cursor, {"version": 1, "targets": targets, "backup_release": backup_release})
    # Round-trip the archive from PostgreSQL and verify it before any deletion.
    require(archive(cursor)["payload"]["targets"] == targets, "archive round-trip mismatch")
    ids = [p["id"] for p in targets["permissions"]]
    for table in ("auth_user_user_permissions", "auth_group_permissions"):
        cursor.execute(f"DELETE FROM public.{table} WHERE permission_id=ANY(%s)", [ids])
    cursor.execute("DELETE FROM public.auth_permission WHERE id=ANY(%s)", [ids])
    for company in targets["companies"]:
        original = company["disabled_features"]
        after = [k for k in original if k not in FEATURES]
        if original != after:
            cursor.execute("UPDATE public.tenancy_company SET disabled_features=%s::jsonb WHERE id=%s", [json.dumps(after), company["id"]])
    cursor.execute("ALTER TABLE public.tenancy_company DROP COLUMN inventory_mode RESTRICT")


def restore(cursor, value, stored):
    require(stored is not None, "no archive to restore")
    if stored["state"] == "restored":
        return
    targets = stored["payload"]["targets"]
    current = {c["id"]: c for c in value["targets"]["companies"]}
    for company in targets["companies"]:
        original = company["disabled_features"]
        after = [k for k in original if k not in FEATURES]
        if original != after:
            require(company["id"] in current and current[company["id"]]["disabled_features"] == after,
                    "changed/missing feature row would be overwritten by restore")
    # Explicit archived IDs are restored. FK/PK/unique conflicts abort the whole
    # transaction; never recreate a deleted user/group or replace another row.
    for p in targets["permissions"]:
        cursor.execute("SELECT app_label,model FROM public.django_content_type WHERE id=%s", [p["content_type_id"]])
        require(cursor.fetchone() == ("auth", "user"), "archived content type no longer matches")
        cursor.execute("INSERT INTO public.auth_permission (id,content_type_id,codename,name) VALUES (%s,%s,%s,%s)",
                       [p["id"], p["content_type_id"], p["codename"], p["name"]])
    for name, field in (("direct_grants", "user_id"), ("group_grants", "group_id")):
        table = "auth_user_user_permissions" if name == "direct_grants" else "auth_group_permissions"
        for grant in targets[name]:
            cursor.execute(f"INSERT INTO public.{table} (id,{field},permission_id) VALUES (%s,%s,%s)",
                           [grant["id"], grant[field], grant["permission_id"]])
    cursor.execute("ALTER TABLE public.tenancy_company ADD COLUMN inventory_mode varchar(16) NOT NULL DEFAULT 'serial'")
    cursor.execute("ALTER TABLE public.tenancy_company ADD CONSTRAINT tenancy_company_valid_inventory_mode CHECK (inventory_mode='serial')")
    for company in targets["companies"]:
        original = company["disabled_features"]
        if any(k in FEATURES for k in original):
            cursor.execute("UPDATE public.tenancy_company SET disabled_features=%s::jsonb WHERE id=%s", [json.dumps(original), company["id"]])
    cursor.execute(f"UPDATE {ARCHIVE} SET state='restored' WHERE operation_key=%s", [KEY])


def operate(action="inspect", expected="", confirmation="", backup_release=""):
    require(action in ("inspect", "apply", "restore"), "unsupported action")
    if action != "inspect":
        require(confirmation == CONFIRMATIONS[action] and re.fullmatch(r"[0-9a-f]{64}", expected),
                "typed confirmation and exact inspected-state SHA-256 required")
        require(re.fullmatch(r"db-backup-[0-9]{8}T[0-9]{6}Z", backup_release), "managed backup reference required")
        created = datetime.strptime(backup_release[10:], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        require(0 <= (datetime.now(timezone.utc)-created).total_seconds() <= 1800, "backup reference is not within 30 minutes")
    with transaction.atomic():
        with connection.cursor() as cursor:
            if action == "inspect":
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SET LOCAL lock_timeout='2s'")
            cursor.execute("SET LOCAL statement_timeout='30s'")
            cursor.execute("SET LOCAL search_path TO public")
            if action != "inspect":
                cursor.execute("SELECT pg_try_advisory_xact_lock(731303, 3)")
                require(cursor.fetchone()[0], "another cleanup operation holds the lock")
                cursor.execute("LOCK TABLE public.tenancy_company IN ACCESS EXCLUSIVE MODE")
                cursor.execute("""LOCK TABLE public.auth_permission, public.auth_user_user_permissions,
                    public.auth_group_permissions, public.auth_user, public.auth_group,
                    public.django_content_type, public.tenancy_membership, public.tenancy_currency
                    IN SHARE ROW EXCLUSIVE MODE""")
                cursor.execute("SELECT to_regclass(%s)", [ARCHIVE])
                if cursor.fetchone()[0] is not None:
                    cursor.execute(f"LOCK TABLE {ARCHIVE} IN EXCLUSIVE MODE")
            value, stored = state(cursor)
            if action == "inspect":
                return {"action": action, "mode": "database-enforced-read-only", **summary(value)}
            require(digest(value) == expected, "inspected metadata changed; re-inspect and obtain new approval")
            before = preserved(cursor)
            if action == "apply":
                apply(cursor, value, stored, backup_release)
            else:
                restore(cursor, value, stored)
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            after, _ = state(cursor)
            require(preserved(cursor) == before, "unrelated metadata changed; rolling back")
            return {"action": action, "result": "PASS", "unrelated_metadata_preserved": True, **summary(after)}


class Command(BaseCommand):
    help = "Explicit inspected-state Phase 3B cleanup/restore; inspect is read-only and never authorizes a change."

    def add_arguments(self, parser):
        parser.add_argument("--action", choices=("inspect", "apply", "restore"), default="inspect")
        # The existing read-only SSH wrapper passes --strict. This command is
        # always strict; accepting it preserves that proven transport unchanged.
        parser.add_argument("--strict", action="store_true")
        parser.add_argument("--expected-state-sha256", default="")
        parser.add_argument("--confirmation", default="")
        parser.add_argument("--backup-release", default="")

    def handle(self, *args, **options):
        result = operate(options["action"], options["expected_state_sha256"], options["confirmation"], options["backup_release"])
        self.stdout.write(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    import os
    import sys
    import django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")
    django.setup()
    Command().run_from_argv(["manage.py", "serial_only_phase3_cleanup", *sys.argv[1:]])
