# Financee Offline desktop controller

Phase 5 local development implementation, version 0.5.0-phase5 / schema 2.
The frozen Apple Silicon app contains Python/Tk and its controller/resources;
opening it requires no checkout, terminal, Python, Git or Node installation.
The cached tested Docker payload and supported local Docker runtime remain
prerequisites. Installer import/prerequisite handling belongs to Phases 6/7.

`installation.py` separates installed program resources from a chosen writable
customer folder. New setup accepts only an empty folder, creates independent
random keys, records the owned project/volume/port, and opens empty company
onboarding. Existing installs retain configuration, credentials and data.
Moving a folder requires repair; startup never guesses a replacement volume.

`controller.py` verifies program hashes, local Docker context, native Linux
image IDs, existing service images/customer mounts/volume/loopback binding and
product + installation-specific health. All compose mutations are project scoped;
normal launch never builds/pulls images or uses global stop/down/prune. Missing
owned volumes, unrelated ports and different image versions are refused before
mutation. Explicit update/release recovery is Phase 8. A healthy matching build
is reused. Per-installation host locks serialize operations; a separate GUI lock
forwards second-launch requests to the existing window. Work runs off the GUI
thread, and closing a busy window waits for completion.

Backup, inspect and digest-confirmed restore call the shared Phase 4 engine in
the owned runtime. Restore retains the rescue/previous data, checks candidate
health, commits only after success and rolls back on restart failure. A missing
or invalid ZIP never replaces the active dataset. The local device owner is the
maintenance authority; these operations are not remotely exposed through Django.

`integration.py` creates an explicit desktop shortcut and opt-in OS sign-in
entry. Neither startup registration nor global Docker preferences are changed
by opening the app. macOS LaunchAgents and Windows Startup shortcuts are scoped
to the installation ID. Windows source hooks require native Windows verification;
this Mac build does not certify Windows, reboot, installer or notarization gates.

Developer build (isolated native ARM64 Python with Tk and pinned requirements):

```
.runtime/phase5-tools/python/bin/python scripts/build_launcher.py --customer .runtime/review
```

Outputs stay in ignored `.runtime/phase5-launcher`. Test/customer profile paths
in these local development apps are deliberately absolute and machine specific;
final installers must use the unbound first-run app. No private profile content
is copied into an app. Artifacts are ad-hoc signed locally, not notarized or
approved for public distribution. Native test cases and remaining review gates
are recorded in docs/PHASE5_REVIEW.md.

Host guard tests use fake runtime responses and private temporary OS-hook paths.
`tests/test_launcher_integration.py` guards the disposable `financee_offline_test`
installation, restores real backups there, returns its original pointer, and
creates/stops a separate empty owned test installation. It never restores review.
