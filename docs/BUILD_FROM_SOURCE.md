# Build from source

## Supported development environment

- Windows 10/11 x64
- Python 3.12–3.14
- PowerShell 5.1 or newer
- JDK 17+
- Git
- Node.js 20+ for extension tests

## Setup

```powershell
.\scripts\check-prerequisites.ps1
.\scripts\setup.ps1
```

This creates `venv` and installs `requirements.txt`. Run from source with:

```powershell
.\scripts\run-dev.ps1
```

Development state is separated from packaged production state under Local
AppData.

## Build

```powershell
.\scripts\build.ps1
```

The script calls PyInstaller in windowed one-directory mode, bundles curriculum
JSON, migrations, timezone data, and clean Git/version/build metadata, then
writes `dist\DSAAccountability\DSAAccountability.exe`.

Create the release ZIP:

```powershell
.\scripts\package-release.ps1 -SkipBuild
```

The ZIP contains the complete PyInstaller directory, unpacked Chrome extension,
and prebuilt quick-start instructions.
