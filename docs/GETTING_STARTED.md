# Getting started

DSA Accountability is a Windows desktop companion for one learner repository.
It creates a local SQLite database for schedule/progress state and uses a
separate Git repository for your Java source and notes.

## Before you begin

Install a Java JDK (17+), Git for Windows, and Google Chrome. VS Code is
recommended. A prebuilt release does not require Python; a source build does.

The app will create:

- `%LOCALAPPDATA%\DSAAccountability\data\progress.sqlite`
- local logs and SQLite-native backups under the same AppData folder
- a random localhost pairing token stored only in that database
- a learner Git repository at the folder you choose

GitHub is optional. Git stores local history; GitHub adds remote backup/sync.
The Chrome extension observes the LeetCode problem page you already opened and
reports fresh submission state to the app on `127.0.0.1`.

## First run

1. Choose the date that should be Curriculum Day 1.
2. Choose an existing learner Git repository or a new/empty folder.
3. Optionally enter an `origin` remote URL and select automatic push.
4. Choose whether the app should launch when you sign in to Windows.
5. Review the real Java, Git, VS Code, and startup checks.
6. Save setup. A fresh 135-day schedule is generated from your selected date.
7. Load and pair the Chrome extension using [Chrome Extension](CHROME_EXTENSION.md).

The first active day is Day 1. The app does not mark anything complete during
setup and never generates learner solutions.

## What happens daily

Open the overlay, complete the active day's tasks, write code in VS Code or
LeetCode, verify it, add your own reflection, and finalize. The next day unlocks
only when every required task for the active day is complete.

Continue with the [User Guide](USER_GUIDE.md).
