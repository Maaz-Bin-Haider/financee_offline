# ADR 002: isolated runtime and platform gates

Reviewed 2026-10-26, Asia/Karachi. Platform packaging choices are provisional
until native prototypes and real device tests pass.

The review runtime uses a separately built Financee_Offline Linux ARM64 image,
PostgreSQL 16.15, Redis and Nginx. Only Nginx binds 127.0.0.1:18766. Database/cache
have no host port; no container mounts the Docker socket. All Compose project,
volume and network names begin financee_offline_review or financee_offline_test.
Review and test runtime credentials are independently generated and ignored.
Normal startup uses cached digest-pinned dependency images and pull_policy=never.
The app tag is 0.1.0-phase1; exact built digest is recorded at handoff. Source
application images and secrets are never used. Release dependency refresh and
multi-architecture archive manifests are pending their packaging/release gates;
the development Nginx payload is a cached digest, not a certified release choice.

Personal-device settings: PostgreSQL max_connections 40/shared_buffers 128 MB,
Redis cap 64 MB, Gunicorn 2 workers x 2 threads, Nginx 256 connections. No EC2,
SSH, cloud upload, telemetry, billing worker or report-email worker exists.
Backup worker will be introduced only with the shared verified ZIP engine.
Customer folder contract is Config, Data/media, Backups, Logs and Cache, separate
from installed program files. Phase 1 uses ignored .runtime/review and test folders;
packaged setup will move customer selection to Documents/Financee_Offline.
PostgreSQL lives in a stable owned named volume. Developer tooling never removes
volumes, resets databases, prunes Docker or stops the shared Docker runtime.

Windows 11 x64: candidate Docker Desktop Linux containers under WSL2, reuse a
compatible installation with consent for prerequisites. Actual install, reboot,
resume, repair and uninstall testing is pending on a real Windows 11 machine.
[Docker Windows requirements](https://docs.docker.com/desktop/setup/install/windows-install/)
list OS/build and WSL prerequisites plus Microsoft's servicing-policy restriction.

Windows 10 x64 remains required. Docker's page still lists 22H2/build 19045 but
also restricts supported Windows to Microsoft's servicing timeline. This is not
proof that every Windows 10 edition/device is supported. Candidate fallback:
maintained Docker Engine in a dedicated Financee-owned Ubuntu 24.04 WSL2 distro,
without changing existing distros or global WSL/Docker configuration. Microsoft's
[WSL installation prerequisites](https://learn.microsoft.com/en-us/windows/wsl/install)
cover Windows 10 build 19041+ for its guided commands. Ubuntu's
[WSL2 guide](https://documentation.ubuntu.com/wsl/latest/howto/install-ubuntu-wsl2/)
includes Windows 10 21H2+; Docker's [Engine support](https://docs.docker.com/engine/install/ubuntu/)
includes Ubuntu 24.04 and x86_64. These establish a plausible engineering path,
not certification of Engine-in-WSL on Windows 10. Validate current OS servicing,
WSL/kernel, daemon/systemd startup, offline reboot, localhost networking and
customer consent on actual Windows 10 before accepting this path. No obsolete
Desktop version is pinned and Windows 10 has not been dropped. Phase 6 remains
blocked for release certification until that evidence exists.

Apple Silicon: native ARM64 Linux payloads and a native ARM64 controller/app.
Docker supports [current plus two previous major macOS releases](https://docs.docker.com/desktop/setup/install/mac-install/).
This host ran ARM64 Linux containers on macOS 26.5.2; this proves the core runtime,
not a DMG install. Native app, Developer ID signature, notarization and stapled
ticket are pending owner credentials and Phase 7. Never bypass Gatekeeper.

Controller candidate: Python GUI frozen with PyInstaller, Windows setup EXE and
ARM64 app/DMG. Cross-platform freezes are not assumed. Native GUI/provisioning
prototypes remain Phase 5 work before final packaging selection; runtime/dev.py
is explicitly developer tooling, not a shipped launcher. No image archive,
installer, shortcut, signing or cold-boot offline certification is claimed.

Docker Desktop's [own license terms](https://docs.docker.com/subscription-billing/desktop-license/)
require eligibility review independently of Financee's one-time purchase. Obtain
prerequisites from official sources and leave their agreement to the user. Do not
redistribute Desktop or accept terms automatically. Installer/payload tooling
licenses and signing are final release inputs, not presumed approvals.
