#!/usr/bin/env python3
"""Rebuild committed browser dependencies. Developer-only: npm ci --prefix scripts/vendor.
Pass --modules to use an already installed, lock-matching package directory.
Customer startup never runs npm or this script.
"""
import argparse, hashlib, json, re, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--modules', type=Path, default=ROOT/'scripts/vendor/node_modules')
a = p.parse_args(); dest = ROOT/'static/vendor'; dest.mkdir(exist_ok=True)
lock = json.loads((ROOT/'scripts/vendor/package-lock.json').read_text())
assets = {
 'jquery': ['dist/jquery.min.js'],
 'jspdf': ['dist/jspdf.umd.min.js', 'dist/jspdf.umd.min.js.map'],
 'jspdf-autotable': ['dist/jspdf.plugin.autotable.min.js'],
 'exceljs': ['dist/exceljs.min.js', 'dist/exceljs.min.js.map'],
 'chart.js': ['dist/chart.umd.js', 'dist/chart.umd.js.map'],
 'bootstrap': ['dist/css/bootstrap.min.css', 'dist/css/bootstrap.min.css.map'],
 'sweetalert2': ['dist/sweetalert2.all.min.js'],
 '@fortawesome/fontawesome-free': ['css/all.min.css'],
}
fonts = {'@fontsource-variable/inter':['index.css'],
 '@fontsource-variable/dm-sans':['index.css','wght-italic.css'],
 '@fontsource/dm-mono':['400.css','500.css'],
 '@fontsource-variable/playfair-display':['index.css']}
records = []; fonts_css = []
def copy(package, file, output=None):
 src=a.modules/package/file; out=dest/(output or package.replace('@','').replace('/','-'))/file
 out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,out)
 return out
for package, files in assets.items():
 if package=='@fortawesome/fontawesome-free':
  files += [str(x.relative_to(a.modules/package)) for x in (a.modules/package/'webfonts').iterdir() if x.suffix in ('.woff2','.ttf')]
 for file in files:copy(package,file)
for package, styles in fonts.items():
 for style in styles:
  out=copy(package,style)
  text=out.read_text().replace('Inter Variable','Inter').replace('DM Sans Variable','DM Sans').replace('Playfair Display Variable','Playfair Display')
  out.write_text(text)
  fonts_css.append('@import url("./'+str(out.relative_to(dest))+'");')
  for file in re.findall(r'url\(\./([^)]*)\)',text):copy(package,file)
(dest/'fonts.css').write_text('\n'.join(fonts_css)+'\n')
# Preserve the complete installed dependency license set, including the libraries
# bundled into the distributed jsPDF/ExcelJS/Chart.js UMD files.
for key, info in sorted(lock['packages'].items()):
 if not key:continue
 src=a.modules.parent/key
 metadata=json.loads((src/'package.json').read_text())
 package=metadata['name']; version=metadata['version']
 if version!=info['version']:raise SystemExit('Lock mismatch: '+key)
 licenses=[]
 for file in src.iterdir():
  if file.is_file() and re.match(r'(?i)^(licen[cs]e|copying|notice|ofl)(\.|$|-)',file.name):
   out=dest/'licenses'/(key.replace('node_modules/','').replace('/','__'))/file.name
   out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,out);licenses.append(str(out.relative_to(dest)))
 if not licenses:
  # Older npm tarballs sometimes put the license in README or metadata only.
  # Preserve the upstream declaration verbatim rather than inventing a notice.
  for file in [src/'package.json', *src.glob('README*'), *src.glob('readme*')]:
   if file.is_file():
    out=dest/'licenses'/(key.replace('node_modules/','').replace('/','__'))/file.name
    out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,out);licenses.append(str(out.relative_to(dest)))
 records.append(dict(name=package,version=version,license=metadata.get('license'),source=info.get('resolved'),integrity=info.get('integrity'),notices=licenses,direct=package in assets or package in fonts))
files={str(f.relative_to(dest)):dict(size=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest()) for f in sorted(dest.rglob('*')) if f.is_file() and f.name!='MANIFEST.json'}
(dest/'MANIFEST.json').write_text(json.dumps(dict(format_version=1,packages=records,files=files),indent=2)+'\n')
print(f'Vendored {len(assets)+len(fonts)} direct packages; {len(records)} license records; {len(files)} files.')
