# Phase 8 manual upgrade development

The owner authorized moving forward and pushing on 2026-11-02. Phase 7 source
checkpoint 9eb706f is pushed. Phase 8 development is in progress; stop before
Phase 9 and do not publish installers or upgrade the review business.

This first policy targets 0.8.0-phase8, schema 2, from 0.5.0-phase5 or
0.7.0-phase7 schema 2. PostgreSQL/cache/proxy identities remain unchanged.
Pending Django migrations, changes to financial SQL, altered business rows,
users, permissions, settings, history, sequences or media are refused. Sessions
expire deliberately. A future schema-changing release requires its own reviewed
migration and preservation policy; running an old image is never a downgrade.

The new installer offers an explicit Manual Upgrade window, verifies the target
payload, retains immutable old/target program snapshots and a protected ZIP,
restores a separate database/media candidate, checks it with the target engine,
runs the declared repeatable migration/check sequence and verifies runtime health.
The old generation, rescue ZIP and cached images remain retained. A durable host
journal supports interrupted-host recovery and validates mixed old/new container
ownership before stopping anything. Normal startup and setup repair refuse
pending upgrade transactions. New-engine web requests remain gated until commit.

The Mac app has a new versioned name/preferences namespace for side-by-side
installation. Keep the old app for recovery; use the new app after commit. Close
old maintenance before applying. Disable optional sign-in startup in the previous
app first; enable it in the new app after verification. Neither installer opts the
user into OS startup. Foreign desktop shortcuts remain preserved. Windows source
has the same upgrade window and a separate development install identity/path;
actual Windows building and native update/reboot/repair acceptance remain pending.

118 host checks pass. Populated real PostgreSQL upgrade, interrupted checkpoints,
native GUI checks and the packaged review artifact are being verified. Results
will be recorded at the Phase 8 handoff; no success is claimed before those runs.
