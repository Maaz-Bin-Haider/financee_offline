# Local browser dependencies

Every runtime library and UI font is served by Financee's local static server.
`MANIFEST.json` pins upstream npm tarball versions/integrities, SPDX identifiers,
license files and SHA-256/size for each shipped asset. `licenses/` includes the
installed transitive dependency notice set for the prebuilt UMD bundles. Upstream
copyright comments are preserved. Font Awesome uses its combined icon/font/code
license; font packages include SIL OFL notices. The separately adapted Financee
currency font remains under `static/fonts/financee/` with its own provenance.

Developer rebuild, from the repository root:

```
npm ci --prefix scripts/vendor --ignore-scripts --no-audit --no-fund
python3 scripts/vendor_assets.py
python3 tests/test_offline_assets.py
```

No npm, download, font service or CDN is invoked during customer startup/use.
Fontsource stylesheet family aliases retain the original UI family names; binary
font files are unchanged. Bootstrap 5.3.5 unifies the former login 5.3.3 include;
Chart.js 4.4.2 unifies the sales report's 4.4.1 include; AutoTable 3.5.31 unifies
3.5.28 includes. SweetAlert2's former floating major-11 URL is pinned to 11.26.25.
Other versions match the existing source includes. ExcelJS remains bundled for
compatibility but its unused global include is removed: no retained screen uses
its API, and loading it unnecessarily requires eval. No native workbook-export
feature is added.

The transitive inventory includes Node/build-only packages as well as bundled
browser code; it does not assert every installed package ships in a browser bundle.
For old upstream tarballs without a standalone notice, the original README and
package metadata are retained verbatim (including absent license declarations).
