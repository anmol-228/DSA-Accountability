# Installation

## Option A — prebuilt Windows release

Recommended for normal users.

1. Download `DSAAccountability-Windows-x64-v1.1.0.zip` from GitHub Releases.
2. Verify the SHA-256 value shown in the release notes if one is provided.
3. Extract the whole ZIP to a stable folder. Do not run from inside the ZIP.
4. Run `DSAAccountability.exe`.
5. Complete First Run Setup.
6. Load the included `chrome-extension` directory as an unpacked extension.
7. Pair once and begin Day 1.

Keep the extracted folder in place if Windows startup is enabled because its
shortcut points to that executable.

## Option B — build from source

Requirements: Windows 10/11 x64, Python 3.12+, PowerShell, JDK 17+, Git, Node.js
for extension tests, Chrome, and optionally VS Code.

```powershell
git clone https://github.com/anmol-228/DSA-Accountability.git
cd DSA-Accountability
.\scripts\check-prerequisites.ps1
.\scripts\setup.ps1 -RunTests
.\scripts\run-dev.ps1
```

`setup.ps1` creates `venv`, installs only `requirements.txt`, regenerates
curriculum/extension assets, and optionally tests/builds. It does not install
global software or modify Git credentials.

Build the executable:

```powershell
.\scripts\build.ps1
```

The output is `dist\DSAAccountability\DSAAccountability.exe`. Create the
distribution ZIP with:

```powershell
.\scripts\package-release.ps1 -SkipBuild
```

## Learner repository options

- Choose an existing Git repository.
- Choose an empty/new folder and let the app run `git init -b main`.
- Create locally first, then create a GitHub repository yourself and add its URL
  during First Run or later in Settings.

GitHub CLI is not required. Use Git Credential Manager/browser authentication
when a push first needs credentials; do not paste personal access tokens into
the app.
