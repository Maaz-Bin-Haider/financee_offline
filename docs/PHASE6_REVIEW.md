# Phase 6 Windows setup prototype

2026-11-02, Asia/Karachi. Owner authorized Phase 6 by instructing “move forward”
after the Phase 5 handoff. This is a **source prototype with shared-engine test
evidence**, not a built or certified Windows installer. Stop before Phase 7.

## What is implemented

- Native Windows x64 prerequisite diagnostics: OS build/client edition, native CPU
  architecture, RAM, firmware virtualization/SLAT, WSL version, VM Platform and
  pending Windows restart. Native architecture uses IsWow64Process2 so Windows ARM
  emulation does not qualify as x64 hardware.
- Separate explicit WSL install/update actions with Windows UAC and saved setup
  state. Install requests `wsl --install --no-distribution`; update requests
  `wsl --update`. No automatic reboot, customer Linux account or distro removal.
  Reopen Setup and choose Check / Resume after restarting; no resume task is
  silently installed at sign-in.
- Docker download/requirements open the official Docker page in the browser.
  The customer handles its own interactive prerequisite installer and terms.
  Per-user and all-users Docker paths are recognized. Existing local Linux Docker
  connections are reused; remote connections and different architectures refused.
- Bundled release/delivery manifests pin archive byte count, SHA-256, program
  hashes and exact image IDs. Explicit local import or HTTPS download stages to a
  temporary file, verifies before atomic publication and reuses verified cache.
  Truncated, oversized, corrupt, wrong-architecture and unexpected-tag archives
  are refused before Docker import. HTTPS redirects cannot downgrade to HTTP.
- Archive validation handles classic Docker config IDs and containerd OCI image
  indexes, checking the descriptor path to the actual native config. Each image
  uses a unique Financee-owned tag: Docker save/load does not reliably preserve
  the original repository-digest reference. Conflicting existing tags are refused.
- Setup restart revalidates runtime, cache and images. First start creates a UUID
  installation in an empty chosen folder; repair reuses its identity, credentials,
  generation and separate backup location. A saved stage never skips validation.
  The desktop launcher returns to Setup until a customer folder is configured.
- Native Windows PyInstaller and Inno Setup development build recipes, per-user
  program files, Start Menu/optional desktop shortcuts and program mutexes.
  Installer repair requires the exact recorded program manifest identity, not just
  the same version string; different builds are refused before program replacement.
- Uninstall preparation locks and verifies the selected installation, stops only
  its services and removes only its recorded sign-in hook. It also handles a first
  start interrupted before preferences were saved. Ownership/runtime/stop failures
  refuse program removal. Inno removes its recorded program files. Customer folders,
  backups, cache, named volumes, images, containers and Docker/WSL remain retained.
  There is no data-deletion option or global Docker cleanup.

Ordinary launcher startup still makes no image download/pull/build or online
licence request. The existing review app and engine remain 0.5.0-phase5/schema 2;
setup prototype version is 0.6.0-phase6. Accounting code/SQL/schema did not change.

## Verification and limits

`python -m unittest tests.test_installer tests.test_launcher` passes **81 checks**
(44 installer/prerequisite cases and 37 launcher guards). These use real temporary
archives/configuration and fake Windows/runtime responses. They cover classic/OCI
archives, wrong native config and descriptor hashes, failed/oversized downloads,
HTTP redirect refusal, disk pressure, foreign images/remote endpoints, reboot-state
persistence, interrupted first start, repair, retained data and replaced startup
shortcuts. They are not proof of Windows API/UAC/compiler behavior.

The real staging/export pipeline also produced a four-image native ARM64 archive.
`tests/test_installer_integration.py` exercises the shared setup engine against a
new disposable UUID-owned installation on this Mac. One adapter deliberately
substitutes the known local Unix context for the Windows named pipe. This verifies
cached image validation, empty onboarding readiness (zero owners/company/journal
rows), reopened setup and repair with unchanged runtime keys/generation/container
IDs, and safe stop before program removal. Temporary test containers/networks are
removed; their database volumes and customer folders remain retained. No review
restore or global Docker restart/cleanup was performed. A missing-image load path
is exercised by the fake-runtime tests; the real Mac lifecycle reuses cached images.

The review main services were already stopped when this phase was checked (its
backup worker was running). Tests preserved container IDs/states/image IDs,
configuration, runtime credentials and media. No live review business fingerprint
was queried because the review web/database were stopped. Do not interpret earlier
Phase 5 “left running” evidence as the current state. The existing desktop shortcut
can start the Phase 5 review build normally; it was not rebuilt in this phase.

Exact local payload hash, source revision and receipts are in PHASE6_RESULTS.json.
No Windows EXE has been generated on this Mac. The Windows builder intentionally
refuses this host. No Inno compilation, native Windows UI, UAC/WSL installation,
Windows reboot/resume, servicing eligibility, Windows filesystem/mount behavior,
real uninstall, Authenticode signature or Windows offline operation is certified.
No image/archive/installer was uploaded and Phase 6 commits remain local.

## Build on a dedicated native Windows x64 machine

These are **developer build steps**, not customer instructions. Use a clean
checkout, native 64-bit Python 3.12 with Tk, Inno Setup and a dedicated compatible
local Linux-container runtime. Review current Docker/Windows servicing eligibility
first. The build has no automatic compiler/prerequisite download or terms acceptance.

1. Create an isolated Python environment under `.runtime`, then install
   `installer/windows/requirements-build.txt` in it.
2. Explicitly build the engine from this independent checkout using
   `docker build --platform linux/amd64 -f runtime/Dockerfile -t financee-offline-phase6-engine:dev .`.
   Obtain/cache the exact AMD64 PostgreSQL/Redis/Nginx references in
   `runtime/compose.yml` on that dedicated build machine. Do not replace the image
   references on the shared Mac review runtime with another architecture.
3. Run the following with that isolated interpreter:

```powershell
python scripts/stage_installer_program.py --architecture amd64 --engine-image financee-offline-phase6-engine:dev --output .runtime/phase6-program-amd64
python scripts/export_installer_payload.py --program .runtime/phase6-program-amd64 --output .runtime/phase6-payload-amd64
python scripts/build_windows_installer.py --program .runtime/phase6-payload-amd64/program --archive .runtime/phase6-payload-amd64/financee-offline-runtime-amd64.tar --iscc 'C:\Path\To\ISCC.exe'
```

The export contains only program resources and cached image archives. The frozen
setup/launcher contain their Python/Tk runtime and notices; customers need no Git,
Python, compiler or source checkout. The image archive is a separate setup payload;
choose Import Local Runtime File in this development build. There is no published
URL. `--download-url` on the exporter is a future explicit release input, not an
upload or authorization to publish. Outputs and build receipts stay ignored under
`.runtime/phase6-windows`. The resulting setup would be **unsigned development
software**; native build success alone does not clear the customer acceptance gate.

## Windows 10 and remaining acceptance

Windows 10 x64 is still required. Docker lists build 19045 and also limits Desktop
support to Windows versions within Microsoft's servicing timeline. A build-number
check alone cannot establish eligibility. This prototype explicitly blocks Windows
10 runtime/business setup. It neither silently drops that target nor installs an
obsolete Desktop release. The candidate maintained Docker Engine in a dedicated
Financee-owned Ubuntu WSL2 distro remains **unimplemented and unqualified**. Ubuntu
24.04/AMD64 Engine support establishes a possible engineering route, not Windows 10
certification. Phase 6 cannot be marked complete until that required path is settled.

Native acceptance still needs Windows 10/11 x64 machines: fresh install with/without
Docker, declined UAC/terms, old WSL and restart resume, no terminal/account setup,
real archive import with missing images, disk/access failures, occupied loopback
port, existing-business repair, other-project isolation, offline cold start/reboot,
backup/restore, sign-in opt-in, retained-data uninstall and reinstall. Authenticode
credentials and approved payload hosting are owner-provided release inputs. Mac
DMG/notarization (Phase 7) and data-changing upgrades (Phase 8) have not been started.

## Upstream references checked 2026-11-02

- [Docker Windows requirements and installation modes](https://docs.docker.com/desktop/setup/install/windows-install/):
  WSL 2.1.5+, Linux containers, RAM/virtualization/build and servicing requirements;
  per-user `%LOCALAPPDATA%\Programs\DockerDesktop` and all-users installation paths.
- [Microsoft WSL commands](https://learn.microsoft.com/en-us/windows/wsl/basic-commands),
  [WSL installation](https://learn.microsoft.com/en-us/windows/wsl/install):
  no-distribution installation, update and possible restart/administrator workflow.
- [Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/):
  maintained Ubuntu/AMD64 candidate, with Windows 10 integration still to prove.
- [Inno Setup licence](https://jrsoftware.org/files/is/license.txt),
  [commercial use request](https://jrsoftware.org/isinfo.php),
  [native architecture restrictions](https://jrsoftware.org/ishelp/topic_setup_architecturesallowed.htm),
  [program mutexes](https://jrsoftware.org/ishelp/topic_setup_appmutex.htm):
  retained upstream notices, native x64 restriction, program replacement guards.
  No compiler is redistributed by this repository.
