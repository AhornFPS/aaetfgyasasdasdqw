# Better Planetside.spec
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['Dior Client.py'], # Deine Hauptdatei
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('web_overlay', 'web_overlay'),
        ('imageformats', 'imageformats'),
        ('config.json', '.'), # Kopiert deine aktuelle Config in das Hauptverzeichnis der EXE
        ('assets/sanction-list.csv', 'assets'),
        ('assets/BlackOpsOne-Regular.ttf', 'assets'),  # Font für Cross-Platform Support
    ],
    hiddenimports=[
        'PyQt6.QtWebEngineWidgets', 
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtPrintSupport' # Oft von WebEngine im Hintergrund benötigt
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Better Planetside',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, # Kein schwarzes Fenster im Hintergrund
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements=None,
    icon='assets/Images/BetterPlannetsideIcon.ico' # Hier den Namen deines Icons anpassen!
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Better Planetside',
)