Native launcher notices

- Tcl 9.0.4: https://github.com/tcltk/tcl/blob/core-9-0-4/license.terms
- Tk 9.0.4: https://github.com/tcltk/tk/blob/core-9-0-4/license.terms

The native build copies these complete notices, the build interpreter's
LICENSE.txt and installed PyInstaller/dependency notices into program/notices.
The generated release manifest records every included notice's SHA-256.
The separate application image retains its existing pinned dependency/vendor
notices. No customer data, credentials or Docker account configuration is bundled.
