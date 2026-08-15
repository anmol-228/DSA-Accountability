# Security and privacy

- The desktop API binds only to `127.0.0.1` and scans ports 8765–8784 when the
  default is occupied.
- Authenticated endpoints require a random pairing token in `X-DSA-Token`.
- The token is stored in the local SQLite database and Chrome's
  `chrome.storage.local`; it must not be shared, committed, or included in
  screenshots.
- Raw tokens are never written to application logs. A shortened one-way hash
  may appear for local pairing-continuity diagnostics.
- The extension's host permissions are limited to LeetCode problem pages and
  loopback HTTP. It does not read cookies, passwords, or account history.
- Learner code and progress remain local unless the user explicitly configures
  GitHub and pushes.
- Git credentials are handled by Git/Git Credential Manager, not stored by the
  application or repository.
- Production SQLite databases, WAL files, backups, logs, Chrome profiles, and
  learner repositories are excluded from source control and release archives.

Use **Backup now** before upgrades. Do not copy only a live `progress.sqlite`
while the app is running; use SQLite's Online Backup API through the app.

Report vulnerabilities using the process in [SECURITY.md](../SECURITY.md).
