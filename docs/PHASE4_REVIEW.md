# Phase 4 local review

Build **0.4.0-phase4**, schema **2**, backup format **1**. Implementation/image
commit `36e77f93bf024d1c85e8030a4f25f8985429ee68`.
Image `financee-offline:0.4.0-phase4`, Linux ARM64,
`sha256:49a9f3dc7e91ff12a07da8a8754b01706259019e857e9f277e087391edf5a75a`.
The following handoff commit adds results and the host verification driver; the
image label identifies its exact implementation. No push, remote or publication.

Open http://127.0.0.1:18766/admin/local-backups/ with the existing owner login.
Also reachable from General Settings → Local Backups. The dashboard remains at
http://127.0.0.1:18766/home/. AED and the existing company/login are preserved.
There is no new shared password. Your review business has not been restored/reset
or populated with test transactions.

## Available now

- Owner-only status, selected folder, last normal success, next-due explanation,
  actionable failures and **Backup Now**. The actual browser action was queued,
  completed by the worker, refreshed and independently ZIP-verified.
- One automatic normal recovery point per local business day while services run;
  a missed-day period causes one catch-up. A manual backup also satisfies today's
  automatic requirement. No backup is promised while the computer is off.
- A single ZIP contains `manifest.json`, PostgreSQL custom-format `database.dump`,
  uploaded `media/` files, portable `configuration.json`, complete table/sequence
  fingerprints in `integrity.json`, and member hashes/sizes in `checksums.json`.
  Empty media directories are reconstructed. ZIP64 is enabled. Runtime credentials
  and Docker configuration are not exported; destination credentials remain local.
- Requests, including session/activity writes and streamed attachment reads, are
  drained before copying the recovery point. SQL SHARE locks also block table
  writes during capture. The default capture limit is 120 seconds (configurable
  within 10–900); a busy drain fails after 30 seconds. Requests get a retryable
  maintenance response during capture and resume before compression/verification.
- A cross-process operation lock excludes manual/scheduled/restore collisions.
  ZIPs are staged on the backup filesystem, fully read/hash/CRC checked, fsynced,
  then atomically published. Owned interrupted staging is reclaimed on retry.
  Completed ZIPs survive a failed or killed job. Publication evidence recovers a
  lost status update so a restart does not create a duplicate daily job.
- Rotation runs only after success and keeps 30 verified normal ZIPs from this
  installation. Rescue copies, unknown/corrupt files, historical developer ZIPs
  and other installations' ZIPs are preserved. Cleanup errors report separately
  without misreporting a successfully saved recovery point.

Backups currently use the ignored customer folder:
`/Users/swisstech/Development/Financee_Offline/.runtime/review/Backups`.
Both the initial automatic ZIP and a later owner-interface manual ZIP validated.
The manual ZIP observed at handoff is
`Financee_Offline_Backup_2026-10-26_213136_471aca3c7b5c4c5fb7338d1167745d1a.zip`,
SHA-256 `adef00b31ad5f8719e23a0ac868576637f52c1c4295757c25a7e225b14c79ee9`.
Its measured capture pause was 0.097 seconds on this small, empty-financial-ledger
review dataset. This is not a large-dataset performance guarantee.

## Recovery and local maintenance

The recovery backend and development controller are implemented. The **packaged
customer GUI/desktop launcher is Phase 5**. Until then, run these from the separate
Financee_Offline repository; customers do not yet have a finished installer.

```
python3 runtime/maintenance.py backup --stack review
python3 runtime/maintenance.py folder --stack review
python3 runtime/maintenance.py open-folder --stack review
python3 runtime/maintenance.py set-folder "/existing/local/backup-folder" --stack review
python3 runtime/maintenance.py inspect "/path/to/backup.zip" --stack review
```

Folder selection preserves old ZIPs in their original location. It uses an atomic
`Config/backup-location.json`; credentials stay unchanged. The selected existing
folder must be accessible to Docker. Missing mount folders fail visibly rather
than silently creating a replacement. Changing folder makes a recovery point due
there. Finder/Explorer GUI execution is implemented but was not separately
certified through an OS interaction test in this phase.

Inspect shows company, timestamp, version, size and the exact ZIP SHA-256. Restore
requires explicit replacement confirmation bound to that inspected digest:

```
python3 runtime/maintenance.py restore "/path/to/backup.zip" --stack review --confirm-sha "SHA-256 shown by inspect"
```

This replaces the active business with the chosen point. It is not a merge/import.
Restore only trusted local recovery ZIPs: checksums detect corruption, not archive
authorship. PostgreSQL logical restore executes source SQL.
[PostgreSQL 16 restore documentation](https://www.postgresql.org/docs/16/app-pgrestore.html).

The controller checks compatibility/space and validates names, duplicate paths,
links, required metadata and every member checksum before replacement. Healthy
current data requires a verified pre-restore rescue ZIP. It stops only the owned
web/backup services, restores into a new candidate database/media directory,
checks schema, active owner, validated constraints, balanced journals, attachment
links/sizes, all table/sequence fingerprints and the source-derived SQL contract,
and clears restored sessions/project cache. One fsynced pointer switches both
DB and media. Application health must report the new generation before commit.
The former DB/media and rescue ZIP are retained; they are never dropped first.

Failure reselects the previous generation. A persistent recovery journal and web
write barrier cover interruption after pointer switching. Normal `runtime/dev.py
up --stack review` rolls an unfinished operation back before starting the app.
A stale web worker also refuses requests after a generation mismatch. Recovery
works without a working Django app; the controller can start the owned DB/cache
and use maintenance tooling independently. Explicit rollback is available with
`python3 runtime/maintenance.py recover --stack review`.

## Actual verification

- 37 Django core tests, including owner/staff/CSRF backup controls; 328 independent
  business assertions; 1530 real HTTP checks across 43 routes and 147 local assets.
- 17 real database/ZIP and fault cases: corruption/future version/missing members,
  unsafe paths/duplicate names/symlinks, disk-full/permission/missing-folder errors,
  cross-process collision and crash release, streamed-request draining and bounded
  drain failure, later financial posting rewind while the old generation retains
  it, rescue retention, session expiry, candidate failure/incomplete switch,
  32-ZIP retention fixtures, foreign-installation protection, interrupted status
  publication, retention error, five-day catch-up and hard-killed backup staging.
- Actual host controller: selected-folder automatic backup; no extra scheduled
  ZIP on same-day full stop/start; confirmed restore and web restart; unchanged
  runtime credentials; retained former media/rescue; expired restored sessions;
  startup rollback after an unverified prepared switch. All on disposable data.
- Real custom dump round trip: ARM64 → **emulated Linux AMD64** → ARM64, with every
  table and sequence fingerprint equal, 190 financial SQL definitions unchanged,
  and attachment/journal integrity checked. This follows the logical archive's
  portability model. [PostgreSQL 16 dump documentation](https://www.postgresql.org/docs/16/app-pgdump.html).
- Review upgrade: 35 public-table fingerprints plus users/role flags, permissions,
  profile and media hashes unchanged. No review restore was executed. Both source
  repositories remain clean and unchanged; their Docker resources were untouched.

ZIP64 members were exercised, but multi-gigabyte/actual disk-exhaustion hardware
benchmarks are not claimed. Missed dates, 30-copy retention and selected faults
are controlled tests, not a 30-day observation. Native Windows/macOS installation,
signing, sleep/reboot recovery and actual target filesystem/platform certification
remain later gates. Core schema remains version 2; no migration was added.

## Manual review gate

1. Open Local Backups and check the folder and completed ZIP status.
2. Click Backup Now; refresh shortly and check the new completed filename.
3. Inspect the ZIP or keep an additional copy on storage you control.
4. Confirm the existing company, AED, users and normal workflows remain intact.

Stop here before Phase 5. Desktop maintenance controls, launchers and installers
have not been packaged. No cloud upload, telemetry, push or publication occurs.
