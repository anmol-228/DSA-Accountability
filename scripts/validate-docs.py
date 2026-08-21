"""Validate required public docs and local Markdown links."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = [
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "docs/GETTING_STARTED.md",
    "docs/INSTALLATION.md",
    "docs/USER_GUIDE.md",
    "docs/HOW_IT_WORKS.md",
    "docs/CURRICULUM_AND_SCHEDULE.md",
    "docs/LOCAL_JAVA_WORKFLOW.md",
    "docs/LEETCODE_INTEGRATION.md",
    "docs/GIT_GITHUB_INTEGRATION.md",
    "docs/CHROME_EXTENSION.md",
    "docs/CONFIGURATION.md",
    "docs/BUILD_FROM_SOURCE.md",
    "docs/TESTING.md",
    "docs/TROUBLESHOOTING.md",
    "docs/SECURITY_PRIVACY.md",
    "docs/FAQ.md",
    "docs/ARCHITECTURE.md",
    "docs/DEVELOPERS.md",
]


def main() -> int:
    errors: list[str] = []
    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            errors.append(f"missing required document: {relative}")

    link_pattern = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
    for document in [ROOT / item for item in REQUIRED if (ROOT / item).is_file()]:
        text = document.read_text(encoding="utf-8")
        for target in link_pattern.findall(text):
            target = target.strip().split("#", 1)[0]
            if not target or re.match(r"^(https?://|mailto:)", target):
                continue
            resolved = (document.parent / target).resolve()
            if not resolved.exists():
                errors.append(f"broken local link: {document.relative_to(ROOT)} -> {target}")

    if errors:
        raise SystemExit("Documentation validation failed:\n- " + "\n- ".join(errors))
    print(f"Documentation validation passed: {len(REQUIRED)} required files and local links are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
