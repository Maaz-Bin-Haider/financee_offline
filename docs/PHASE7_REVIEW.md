# Phase 7 Apple Silicon development installer

2026-11-02, Asia/Karachi. The owner instructed “move forward” after the Windows
build handoff. Phase 7 now has a locally built, self-contained **Apple Silicon
Mac development app and DMG**. Stop before Phase 8. This is ad-hoc signed,
not Developer ID signed/notarized, and not a customer-certified release.
Windows device testing remains deferred; the Windows 10 maintained runtime path
remains unfinished. Those gates have not been silently waived.

## Local build and review

DMG: `dist/Financee-Offline-Apple-Silicon-Development-bec7a2a.dmg`
(497,563,709 bytes), SHA-256:
`1c32839da08604d62108744a4a7a37c60c1a3d3d9e6a0565ab48207d18bc7791`.

Native app source: `bec7a2a2880548b8ab91c8462a5acc2311caa67a`.
Setup version `0.7.0-phase7`; engine `0.5.0-phase5`, schema 2.
The engine remains the previously tested cached ARM64 image; no accounting,
financial SQL, Django schema or live review data was changed in this phase.
The exact app tree/runtime/DMG hashes and test receipts are in PHASE7_RESULTS.json.
All generated apps, payloads, test customer folders and DMGs stay ignored.

The DMG contains `Financee Offline Mac Development.app`, an Applications link and
read-first instructions. The app bundles its Python/Tk runtime, public trust and
licensing resources, program files and all four matching ARM64 runtime images.
It contains no customer profile, business data, credentials, live backups or
Docker Desktop installer. Customers need no Git, Python, Node or terminal for
normal setup/use. Docker itself remains a separate prerequisite obtained through
the official download/requirements page and the user's own prompts/terms.

For later manual review, use a disposable empty business folder. Open the DMG
and app normally if macOS permits this locally built development artifact. If
Gatekeeper blocks it, stop and obtain the signed/notarized build; do not disable
protections, remove quarantine or follow bypass instructions. This development
app is expected to fail distribution Gatekeeper assessment.

1. Choose **Install to My Applications**, or copy the app into Applications.
   The native action stages and verifies a copy in `~/Applications`, launches it,
   and preserves other/different apps. It refuses repair while that app is running.
2. Choose **Check This Mac**, review the official Docker requirements, and finish
   Docker's own setup prompts. Select **Docker Setup Reviewed** only after that.
   Financee never accepts third-party terms or installs Rosetta for the user.
3. Choose **Verify Included Runtime**. It verifies the archive and local images;
   normal daily startup never downloads, pulls, builds or exports images.
4. Choose a **New Empty Business Folder** or explicitly open/repair the existing
   folder using the same build. Initial ZIPs go in its Backups folder; the
   maintenance window can choose another folder. Complete company/currency and
   owner setup in the browser yourself. No universal login or demo business exists.
5. A desktop icon is optional during setup. Sign-in startup stays off unless the
   user selects it in maintenance. Closing the window/browser keeps services alive;
   Stop Financee affects only the recorded installation.
6. Maintenance → File → **Setup / Repair / Prepare Removal** reopens setup. Prepare
   App Removal verifies/stops the owned stack and removes its own optional sign-in
   hook. Then quit and move the app to Trash yourself. Business folders, backups,
   containers/images and recorded database volumes remain retained. Reinstalling
   this exact build can reconnect; data-changing upgrades remain Phase 8.

The development app uses its own `~/Library/Application Support/Financee Offline
Mac Development` preferences/state namespace. It does not replace the old Phase 5
review shortcut or its bound preferences. Running from a disk image, source folder
or App Translocation location cannot initialize a business; install the app first.
Same-build program repair checks bundle identity/release hash, validates a staged
copy, switches atomically and rolls back on verification/receipt failure. A
foreign/different app build is preserved rather than implicitly upgraded.

## Actual verification

- **106 host checks pass**: 17 Mac installer boundaries plus the 89 existing
  installer/prerequisite and launcher checks. They cover app-copy ownership,
  running-app lock, same-build repair, staging/published/receipt failure rollback,
  disk pressure, native prerequisites, remote-context refusal and private alias/
  sign-in preservation. Fixture tests do not certify native dialog behavior.
- `verify_macos_installer.py` copied the real frozen app outside the checkout,
  removed Python/Tcl/developer/TLS path overrides, restricted PATH to OS tools,
  and passed headless program hashes, native architecture, Tcl and TLS checks.
  It then mounted the actual DMG read-only and repeated those checks plus complete
  bundled runtime verification. Copied/mounted app tree hashes match. All five
  Mach-O files are ARM64; library references are relocatable and app symlinks stay
  inside the bundle. No Rosetta or customer Python installation is needed.
- The first relocated test found the build interpreter's required root-rejection
  policy PEM was missing. It is now bundled unchanged; public certifi CA data and
  its licence are also included. TLS validation/rejection policy was preserved.
  The final copied/mounted app passes TLS initialization without developer files.
- `test_macos_installer_integration.py` performed actual signature-verified app
  copy into a private Applications fixture, refused running-app repair, started
  a new UUID-owned empty installation, repaired program/setup with unchanged
  identity/credentials/generation/container IDs, verified health through the
  installed frozen executable, and performed removal preparation. Owner/company/
  journal counts were `0|0|0`. The native Mac local-context adapter was used.
- Desktop alias and sign-in plist were verified in private fixtures. No actual
  user OS sign-in hook was enabled. Removal preparation stopped only the new test
  stack. Its temporary containers/networks were removed, while customer files,
  app and named volumes remained retained. No review restore occurred.
- Review db/redis/web/nginx were already exited and backup was running. Those
  container states/image IDs and config/credentials/media stayed unchanged. No live
  review business fingerprint was queried while its main services were stopped.
- Real host prerequisites passed on macOS 26.5.2 ARM64, 24 GB RAM, hypervisor
  available, no Rosetta translation. This certifies neither an 8 GB device nor
  every supported macOS release. The Mac was locked during UI availability checks;
  native install/setup/cancellation dialogs have **not** been clicked or visually
  certified. A manual unlock request remains pending.

## Signing/notarization and remaining gates

`security find-identity -v -p codesigning` reported no valid identity. Local ad-hoc
signature integrity verification passes, but `spctl --assess --type execute`
returns exit 3/rejected. No protection was weakened. The notarization helper
refuses this app before submission because a genuine Developer ID Application
signature, hardened runtime and team identity are required.

The owner-operated path is implemented, not executed against Apple:

```text
scripts/build_macos_installer.py --program PROGRAM --archive ARM64_TAR --output NEW_DIR --identity "Developer ID Application: OWNER (TEAM)"
scripts/notarize_macos_installer.py --app SIGNED_APP --output NEW_DIR --identity "Developer ID Application: OWNER (TEAM)" --keychain-profile OWNER_PROFILE
```

PyInstaller signs with the existing identity/hardened runtime. The second command
copies the signed app, submits an app ZIP through notarytool, requires Accepted,
staples/validates the app, builds/signs a DMG, submits/staples/validates it and checks
Gatekeeper. Failed submissions retain logs. It accepts only an owner-configured
keychain profile name; no password/private key is requested or written. Invoking
it uploads program artifacts to Apple and requires separate owner release inputs;
it is never called by normal setup/startup. No Apple submission, public release or
artifact upload was performed in this phase. Phase 7 source commits remain local.

Still pending: native UI testing after manual unlock; real fresh supported Macs,
Docker-absent setup/consent, true offline cold start after OS reboot/sign-in,
Developer ID/notarization/stapled-ticket acceptance, real user repair/removal/
reinstall, and owner review. Phase 8 data-changing upgrades have not started.

## Rebuild and sources

Use a clean independent checkout and the pinned native build environment in
`installer/macos/requirements-build.txt`. Stage/export exact cached ARM64 images
with `stage_installer_program.py` and `export_installer_payload.py`, then run the
Mac builder and verifier. This host uses Python 3.12.14, Tcl/Tk 9.0.4, PyInstaller
6.22.3 and certifi 2026.10.23; notices and resource hashes are bundled. Build
receipts distinguish native launcher source from the retained engine image.

[Docker Mac requirements](https://docs.docker.com/desktop/setup/install/mac-install/)
state current plus two previous macOS releases; the policy reviewed 2026-11-02
uses majors 15, 26 and 27. This is a prerequisite policy, not device certification.
[Apple's macOS 27 release](https://developer.apple.com/news/releases/?id=09282026c)
confirms the current major for that policy.
[PyInstaller signing behavior](https://pyinstaller.org/en/stable/feature-notes.html)
and [Apple notarization guidance](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
support the Developer ID/hardened-runtime/notarytool/stapler path. Actual signed
acceptance still needs credentials and evidence. Docker Desktop is not redistributed.
