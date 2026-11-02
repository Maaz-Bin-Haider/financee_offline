# Local backup, restore and upgrade recovery

Verified ZIP backup and candidate restore are implemented; see the actual
[Phase 4 evidence](docs/PHASE4_REVIEW.md) and
[Phase 5 maintenance controls](docs/PHASE5_REVIEW.md). Native platform/reboot
acceptance remains a separate release gate.

Each completed ZIP contains a PostgreSQL 16 custom-format logical dump, uploaded
media, portable business configuration, a versioned manifest and complete member
hashes/sizes. Runtime credentials stay destination-local. ZIP publication is atomic
after verification. A bounded cross-process pause/drain coordinates DB and files.

Daily/catch-up jobs run while Financee is running and company setup is complete.
Keep the latest 30 completed normal ZIPs; rescue, foreign, corrupt and incomplete
files are not silently rotated away. Backup Now and status are owner-protected;
choose/open a local backup folder through maintenance. Keep an additional
independent copy. No cloud backup or vendor recovery service exists.

Restore is an explicit local-device-owner operation through maintenance. Choose
and inspect the ZIP, confirm replacement, retain a rescue point, restore and
verify a separate database/media candidate, then switch and health-check. A
failed/interrupted candidate retains or reinstates the previous generation.
Sessions/cache expire; destination runtime credentials remain preserved. The
launcher can recover when Django cannot start. Never overwrite the only live
volume or treat a copied PostgreSQL live-data directory as a logical backup.

Manual upgrades now have a paired candidate/rescue workflow; see
[Phase 8 policy, tests and limits](docs/PHASE8_REVIEW.md). Version 0.8 accepts
reviewed schema-2 sources 0.5/0.7 only and refuses unreviewed migrations/downgrades.
Keep the previous app and rescue ZIP. A failed upgrade returns to the previous
runtime paired with its retained DB/media; an old image alone is not a downgrade.
A successful upgrade cannot silently discard later transactions by rolling back.
Final native upgrade confirmation awaits Mac unlock; Windows/native reboot and
signing acceptance remain pending. Never run restore/upgrade tests on the stable
review business or either reference system.
