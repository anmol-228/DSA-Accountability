# FAQ

## Can I start on another date?

Yes. First Run lets you choose Day 1 and derives Day 135 as Day 1 + 134 days.

## Can I use Python instead of Java?

No. Version 1.1.0 validates and records Java only.

## Does it solve or submit LeetCode questions?

No. You write and submit every solution. The extension only recognizes a fresh
result after you click Submit.

## Do I need LeetCode Premium?

No. The curriculum uses free-tier problems and includes fallback mappings.

## Do I need GitHub?

No. Local Git is required for the completion record; GitHub remote sync is
optional.

## What if I am offline?

Local verification and commits still work. Configured pushes remain pending and
retry with backoff when connectivity returns.

## What if I miss a day?

The earliest incomplete day stays active. The app reports delay but never skips
required work.

## Can I change the curriculum?

Developers can edit `curriculum/build_schedule.py`, regenerate assets, and test.
There is no supported in-app curriculum editor.

## Where is progress stored?

Under `%LOCALAPPDATA%\DSAAccountability\data\progress.sqlite` for a packaged
install. Learner source/notes live in the Git repository you selected.

## Can I move my learner repository?

Yes, but move/copy it yourself, verify its `.git` history, then save the new
path in Settings. Do not point Settings at an unrelated repository.

## How do I reset or uninstall?

Follow [Maintenance](MAINTENANCE.md). Back up first; AppData and the learner
repository are separate destructive decisions.
