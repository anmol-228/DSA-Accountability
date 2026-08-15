# User guide

## Startup and main widget

The app can launch at Windows sign-in and shows a compact always-on-top widget.
Expand it to see the active day, required tasks, streaks, delay, and projected
finish. Settings and History are available from the app controls/tray.

## Day progression and delay

The active day is the earliest incomplete day. A missed due date increases the
schedule-delay number but does not unlock or skip work. Completing every
required task unlocks the next curriculum day immediately, including on the
same calendar date.

## Local exercises

Open the exercise in VS Code, replace the skeleton with your own Java solution,
and use the app's compile/test action. Finalize is enabled only after the
canonical file passes real `javac` compilation and the task's functional tests.
Add your own note before the app makes a narrow local commit.

## LeetCode tasks

Open the requested problem through the app, solve and submit it yourself in
Java, then wait for a fresh Accepted result. The app asks for your pattern,
time/space complexity, explanation, assistance level, and confidence before
writing the captured source and notes to the learner repository.

## Git and GitHub

Local commit success is the durable completion boundary. With automatic push
enabled and an `origin` configured, the app attempts a push. Network failures
enter a retry queue; they do not invalidate the local work. With no remote or
automatic push disabled, work stays in local Git without a failing queue item.

## Revisions and confidence

Green and Yellow use the normal D+2/D+7/D+21/D+45 sequence. Red adds early D+1
and D+3 reviews. Confidence is part of the learner's reflection; it is not
inferred or fabricated by the app.

## History, settings, and recovery

History shows curriculum completion and dates. Settings controls startup,
auto-push, learner-repository path, remote URL, pairing token, backup/export,
and integration diagnostics. Use **Backup now** before upgrades or risky
maintenance. See [Maintenance](MAINTENANCE.md) for recovery and migration.
