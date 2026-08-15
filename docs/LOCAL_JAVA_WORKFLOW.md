# Local Java workflow

The app is not a code editor. It opens the canonical exercise source in VS Code
and watches that file for changes.

```text
<learner-repo>/Week-01/Day-001/exercises/EvenOdd.java
```

1. Open the task and choose the VS Code action.
2. Write the solution yourself in the canonical file.
3. Save it; the app's watcher refreshes status.
4. Run verification. The build service invokes real `javac`, then `java` with
   bounded timeouts and task-specific input/output cases.
5. Fix compilation, timeout, or wrong-output failures and rerun.
6. Add your own completion note and finalize.
7. The app stages only the exercise and its day notes, creates a local commit,
   and optionally pushes.

The app will not accept a differently named file as the canonical solution.
When an operation would overwrite an existing file, the code-sync layer creates
a timestamped recovery copy rather than silently discarding it.
