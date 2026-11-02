# Native ARM64 only; public program/payload inputs are supplied by the builder.
import os
from pathlib import Path
root=Path(SPECPATH).parents[1]
program=os.environ['FINANCEE_MAC_PROGRAM'];archive=os.environ['FINANCEE_MAC_ARCHIVE']
name='Financee Offline Mac Development'
identity=os.environ.get('FINANCEE_MAC_SIGN_IDENTITY') or None
a=Analysis([str(root/'installer/macos_entry.py')],pathex=[str(root)],binaries=[],datas=[(program,'program'),(archive,'payload')],hiddenimports=[],hookspath=[],excludes=[],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name=name,debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,target_arch='arm64',codesign_identity=identity,entitlements_file=None,argv_emulation=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name=name)
app=BUNDLE(coll,name=name+'.app',bundle_identifier='com.financee.offline.macos.development',version='0.7.0',info_plist={'CFBundleShortVersionString':'0.7.0','CFBundleVersion':'700','LSMinimumSystemVersion':'15.0','NSHighResolutionCapable':True,'NSDocumentsFolderUsageDescription':'Financee stores business data and backups only in the folder you choose.','NSDesktopFolderUsageDescription':'Financee creates a desktop icon only when you select that option.'})
