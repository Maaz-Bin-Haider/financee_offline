#!/usr/bin/env python3
"""Offline distribution contract: actual resource targets, license/hash inventory,
CSS imports/fonts and executable third-party dependency ordering.
"""
import hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; errors=[]; checks=0
def check(ok,message):
 global checks
 checks+=1
 if not ok:errors.append(message)
manifest=json.loads((ROOT/'static/vendor/MANIFEST.json').read_text())
for name,info in manifest['files'].items():
 p=ROOT/'static/vendor'/name
 check(p.is_file(),f'Missing vendored file {name}')
 if p.is_file():check(p.stat().st_size==info['size'] and hashlib.sha256(p.read_bytes()).hexdigest()==info['sha256'],f'Changed asset {name}')
for pkg in manifest['packages']:
 check(bool(pkg['notices']),f'Missing license notice: {pkg["name"]}')
for p in (ROOT/'templates').rglob('*.html'):
 text=p.read_text()
 for tag in re.findall(r'<(?:script|link|img|iframe|source|video|audio)\b[^>]*>',text,re.I):
  for target in re.findall(r'(?:src|href)=[\'\"]([^\'\"]+)',tag,re.I):
   check(not re.match(r'(?:https?:)?//',target),f'Remote resource {p.relative_to(ROOT)}: {target}')
 for target in re.findall(r'{%\s*static\s+[\'\"]([^\'\"]+)[\'\"]\s*%}',text):
  # admin CSS is supplied by Django's installed static app.
  if not target.startswith('admin/'):check((ROOT/'static'/target).is_file(),f'Missing static target {target}')
for p in (ROOT/'static').rglob('*.css'):
 for target in re.findall(r'url\(\s*[\'\"]?([^\s)\'\"]+)',p.read_text()):
  if target.startswith('data:'):continue
  check(not re.match(r'(?:https?:)?//',target),f'Remote CSS resource {p}: {target}')
  if not target.startswith(('/', '#')):check((p.parent/target.split('?')[0].split('#')[0]).is_file(),f'Missing CSS resource {p}: {target}')
base=(ROOT/'templates/base/base.html').read_text()
libs=['jquery/dist/jquery.min.js','sweetalert2/dist/sweetalert2.all.min.js','chart.js/dist/chart.umd.js','jspdf/dist/jspdf.umd.min.js','jspdf-autotable/dist/jspdf.plugin.autotable.min.js']
positions=[base.index('vendor/'+x) for x in libs]
check(positions==sorted(positions),'Third-party dependency ordering changed')
check(positions[-1]<base.index("js/business.js"),'Libraries must load before app and page code')
check('internal: true' in (ROOT/'runtime/compose.yml').read_text(),'Owned runtime must deny backend egress')
check("connect-src 'self'" in (ROOT/'runtime/nginx.conf').read_text(),'Browser connections must be local')
if errors:
 print('\n'.join(errors));sys.exit(1)
print(f'{checks} offline asset/license/hash checks passed; {len(manifest["packages"])} dependency license records.')
