# Git and GitHub integration

The learner repository is separate from the application source. Its name and
location are configurable; `DSA-135` is only the default suggestion.

## Safe local commits

The app never runs `git add .` or `git add -A`. It stages only the solution and
notes belonging to the finalized task. It never force-pushes, resets, rebases,
or rewrites learner history.

Typical commit messages:

- `dsa(day-008): solve LC1 Two Sum`
- `dsa(day-001): complete Java exercise — Even/Odd`
- `dsa(review): revisit LC1 Two Sum`

## GitHub is optional

Git provides local history even when no remote exists. If automatic push is
disabled or `origin` is absent, a successful local commit remains valid and no
push is queued.

When automatic push and `origin` are configured:

```text
work verified → local commit → push attempt
                              ├─ success → pushed
                              └─ offline → pending queue → automatic retry
```

Retry backoff grows from roughly 1 minute to 5, 15, then 30 minutes. Queue rows
are bound to the repository that created the commit, preventing a retry through
a different folder.

Use Git Credential Manager/browser authentication. The app has no field for a
GitHub token and does not store Git credentials.
