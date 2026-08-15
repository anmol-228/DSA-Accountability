# LeetCode integration

The included Manifest V3 extension runs on `leetcode.com/problems/*` and talks
only to the desktop API on `127.0.0.1`.

## Fresh Accepted flow

```mermaid
sequenceDiagram
    participant U as Learner
    participant L as LeetCode page
    participant X as Chrome extension
    participant A as Desktop localhost API
    participant G as Learner Git repo
    U->>L: Open assigned problem
    X->>A: Start authorized problem session
    U->>L: Write Java and click Submit
    X->>X: Arm this submission
    L-->>X: Fresh Accepted result
    X->>A: Send slug, Java source, timestamp, trace
    A->>A: Validate session/day/task/source freshness
    A-->>U: Request reflection
    U->>A: Own explanation and confidence
    A->>G: Write narrow files and local commit
```

Accepted is counted only after a current Submit action arms detection. The
backend also requires a current authorized session, matching problem/task/day,
Java language, a fresh source, and a bounded timestamp. Reloading a historical
Accepted page does not become new work.

The extension does **not** solve questions, write answers, click Submit, bypass
LeetCode, read cookies/passwords, or convert old Accepted results into progress.
The user always authors and submits the solution.

Common failures are covered in [Troubleshooting](TROUBLESHOOTING.md).
