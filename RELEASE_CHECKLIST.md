# Release gates

No customer release or publication is authorized. Phase 8 source advancement and
GitHub pushes are authorized; Phase 9 distribution work has not started.

| Area | Recorded evidence | Remaining gate |
| --- | --- | --- |
| Core/settings/presentation | Single-company, permissions, currency/timezone and unchanged financial SQL; Phase 1–3 evidence | Full customer platform matrix |
| Offline runtime | Bundled assets/images, isolated loopback/internal networks and cold service tests | Actual disconnected OS reboot/sign-in on supported customer devices |
| Backup/restore | Verified ZIP64, daily/catch-up, retention, rescue/candidate restore, logical architecture round-trip | Customer device recovery acceptance |
| Launcher/installers | Native Mac development DMGs and Windows development setup build | Fresh Windows 10/11 and Mac install/reboot/repair/removal matrix |
| Manual upgrades | Populated schema-2 0.5/0.7 → 0.8, five host interruptions, real candidate/startup faults; native Mac confirm/cancel/upgrade/login/stop; 120 host and 38 core checks | Windows native guards/imports pass; full Phase 8 build/public-artifact approval and customer device tests remain; future schema policies |
| Windows 10 | Explicitly retained target, installer blocks an unqualified runtime | Maintained runtime implementation and actual qualification |
| Signing | Ad-hoc integrity checks, owner-operated signing/notary recipes, pre-upload guard | Owner Developer ID/notary inputs, signed/stapled acceptance, Windows signing |
| Distribution | Source repo/push permission only; generated installers/data stay out of Git | Phase 9 CI/release matrix, hosting/notices/terms and explicit publication approval |

Exact current handoff and remaining platform gates: [Phase 8 review](docs/PHASE8_REVIEW.md)
and [structured results](docs/PHASE8_RESULTS.json). Existing review data and both
source systems are preserved. Passing host tests never certifies unavailable
Windows hardware or signing credentials.
