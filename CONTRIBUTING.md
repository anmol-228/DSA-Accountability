# Contributing

1. Fork the repository and create a focused branch.
2. Keep user data, databases, logs, tokens, credentials, and machine-specific
   paths out of commits.
3. Use the existing service boundaries and narrow Git/file operations.
4. Add tests and run `scripts\test.ps1`.
5. Run public-safety and documentation/link checks before opening a PR.

Tests must use pytest-owned temporary resources and must never read, migrate,
write, commit, or push a real installation. Database migrations, Chrome changes,
and filesystem/Git changes require explicit regression coverage.

Use clear commits such as `fix: ...`, `feat: ...`, `docs: ...`, or `test: ...`.
PRs should state tests run, production-safety impact, migration impact, Chrome
extension impact, and screenshots when UI behavior changes. Do not include
generated build output or unrelated formatting churn.
