# Phase 3 local review

Build **0.3.0-phase3**, schema **2**. Core commit
`ef14c04785b82d07c5773d9e089ffdd73f4d86fc`.
Image `financee-offline:0.3.0-phase3`, Linux ARM64,
`sha256:cc6c0760abf2b70ad45d9721d8d7e2b8eb542233b94ed410b7a962d073751e24`.
The following documentation commit records the completed handoff; the image label
identifies its exact implementation snapshot. No remote, push or release upload.

Open http://127.0.0.1:18766/home/ using your existing owner login. The existing
browser session remains signed in. General Settings retains AED, empty cosmetic
symbol override, Asia/Karachi and all 24 local modules enabled. The currency code
and official symbol appear in the badge; amounts display AED. No FX conversion.

## Changes

- All retained screen libraries, styles, icons and fonts use local static URLs.
  Pinned versions, original notices, upstream tarball integrities and SHA-256/size
  inventory live in `static/vendor/`. Developer rebuild instructions are there.
  Git preserves original asset bytes, including upstream license line endings.
- PDF libraries load once, in dependency order. Duplicate CDN includes are removed.
  The unused global ExcelJS include is removed because it requires eval; its
  library remains bundled for compatibility. Existing Excel-readable CSV exports
  remain; no native workbook exporter or Excel-app verification is claimed.
- Multipart transaction forms now record Team Activity when attachments are added.
  The same JSON payload used by the transaction view supplies action/record/date
  attribution. Accounting SQL and attachment access rules are unchanged.
- Normal application/DB/cache services join only an internal Docker network.
  Nginx alone also joins the bridge Docker Desktop needs to publish the loopback
  port. DB/cache have no published ports. Browser CSP restricts resources and
  connections to the local app; existing inline scripts/styles remain permitted.
- Connection failure messages point to retry/restarting Financee, without implying
  that normal operations require internet. Nonroot runtime home creation also
  resolves Gunicorn's control-directory permission error.

## Verification

35 core Django tests, 328 independently checked business assertions, 76 frontend
JS checks, 1185 asset/license/hash checks, and 1530 HTTP checks pass. All 190
retained financial SQL definitions match the source-derived contract. No schema
migration was added and checks report no migration drift.

The real HTTP test signs in through Nginx, fetches 43 retained screen routes and
147 distinct local resources (including CSS font imports), posts a purchase with
a PDF, verifies its exact 100.25 amount and one attributed activity event, compares
uploaded/previewed/downloaded bytes, searches its serial in Spotlight and checks
the activity API. Anonymous attachment access redirects to login. All mutations
use the separately owned disposable `financee_offline_test` database.

The exact image was stopped and restarted with image pulls disabled. Application
TCP connections to a public IP and a public DNS host fail on the internal network.
A separate browser origin (`localhost:18767`) verified login/alerts, charts,
Spotlight, activity, and purchase layout in both themes at desktop and 390×844.
The real chart PDF has two pages; company, USD and numeric totals were extracted,
and the rendered first page shows its chart and footer without overlap. Browser
screenshots and sample files are private test artifacts, outside committed source.

The cold HTTP resource test uses no browser cache. Browser vendor/font URLs were
new local URLs, and CSP disallows CDN resources even if present in a browser cache.
This is scoped offline verification through service egress isolation and browser
origin policy. Host Wi-Fi was not disabled; no physical network-disconnection or
OS-reboot certification is claimed. Nginx's entry bridge is not an egress firewall.

The review upgrade preserves 35 public-table fingerprints, user identities/role
flags, permissions, profile and every media hash. The existing review business
still has zero journal entries and zero attachment rows; test transactions were
never inserted there. Both source repositories remain clean at their original
HEADs. Stable review DB volume and customer folder were retained.

## Manual review gate

1. Refresh the dashboard and check AED in the badge, cards and report output.
2. Open a purchase and check attachments, serial controls and layout in both themes.
3. Try Spotlight and Team Activity using your own review records when available.
4. For device-level confirmation, disconnect internet and reload/login normally.

Use the existing account; there is no new shared password. Review data was not
reset. The disposable test owner and generated transactions are not customer seeds.

Stop here for owner review. Phase 4 daily/catch-up ZIP backups and recoverable
restore have not been implemented. Native Windows 10/11, Apple Silicon installers,
signing/notarization, upgrade recovery and physical platform evidence remain their
later gates. Existing development rescue ZIPs are not certified customer backups.
