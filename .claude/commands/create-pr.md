Create a merge request / pull request with rich, durable traceability so a reviewer (or a future engineer six months from now) can reconstruct the full development process from the PR description alone.

Optional argument: target branch. If the user passes one (e.g. `/create-pr main` or `/create-pr feat/claude-agent-sdk`), use it. Otherwise default to `main` — BUT if the current branch is part of a phase-based initiative with an integration branch, ask the user whether to target the integration branch or main before pushing.

## Platform detection

Before doing anything else, inspect the remote:

```bash
git remote get-url origin
```

- If the URL contains `github.com` → use `gh` CLI. Check `gh auth status` succeeds; verify `gh` is on PATH.
- If the URL contains `gitlab.com` or another GitLab host → use `glab` CLI. Check `glab auth status` succeeds; verify `glab` is on PATH.
- If neither tool is available → stop and tell the user which CLI to install.

The PR is a "merge request" on GitLab and a "pull request" on GitHub — mirror the user's platform's terminology in progress messages, but the description template is identical.

## Pre-flight (stop and ask before continuing if any fail)

1. Working tree is clean (no uncommitted changes in tracked files). If dirty, stop and tell the user to commit or stash first.
2. Current branch is NOT `main` / `master` / the target branch itself.
3. Current branch has commits that diverge from the target branch — compute with `git log <target>...HEAD --oneline`.
4. Target branch exists locally or on origin.

## Gather context (auto-populate)

Run these in parallel:

- `git branch --show-current` — source branch
- `git log <target>...HEAD --oneline` — commits on this branch
- `git diff <target>...HEAD --stat` — files touched + line counts
- `git diff <target>...HEAD --shortstat` — summary numbers
- `git log -1 --format='%B'` — most recent commit's full message (often already contains rich motivation Claude wrote during `/commit`)
- `ls .agents/plans/ 2>/dev/null` — plan files
- `ls .agents/notes/ 2>/dev/null` — spike/research findings
- `ls .agents/PRPs/feature_requests/ 2>/dev/null` — PRDs
- `ls docs/backend/ docs/ 2>/dev/null | head -40` — operator guides and related docs

For each plan / notes / PRD file, scan the head (first ~40 lines) to identify which one matches the branch's work. The branch name usually correlates: `feat/phase-1-coder-swap` → `.agents/plans/phase-1-claude-agent-sdk-coder-swap.md`, `.agents/notes/phase1-spike-findings.md`. Report what you found before drafting the description — don't assume silently.

If the repo uses `.github/pull_request_template.md` or a GitLab equivalent, read it and honor its section structure on top of the traceability sections below.

## PR title

Use the most recent commit's subject line verbatim if it already follows the `type(scope): subject` convention (which `/commit` produces in this repo). Otherwise construct one from the branch name + commit types. Keep under 70 characters.

## PR description

Assemble a description with these sections, in this order. OMIT any section that doesn't apply — an empty "Codex Review" section is worse than no section at all.

### Summary
One paragraph: what changes, what doesn't change, default behavior preserved. Reference the feature flag if any.

### Motivation
Why this change exists. Pull from PRD / plan context if available. If the branch is one phase of a multi-phase initiative, explain where this phase fits.

### Plan + Artifacts
Bulleted list of committed documents that let a reader reconstruct intent, with relative-path links to files on THIS branch (not absolute URLs — GitLab/GitHub both render relative blob links):
- Plan file
- Spike / pre-phase findings
- Operator guide
- Contract / spec files this MR honors

### Implementation Overview
Grouped by subsystem (not file-by-file). Short bullets per module explaining the moving pieces. Prefer "what + why" over exhaustive line-count listings.

### Review Findings Addressed (only if the branch includes `/codex:adversarial-review` or `/review` outputs in its commits)
If prior Codex / human review findings were addressed on this branch, list each finding with:
- Severity and one-line description
- Evidence the finding was real (pointer to the code or commit where it was fixed)
- The fix taken

Pull this from commit messages that mention "Codex review" or "review fix" — don't invent findings that don't exist.

### Testing
Table with columns: Level | Command | Result. Include at least:
- Unit tests specific to this change
- Regression suite (if the repo has a `baseline_passing.txt` or similar)
- Lint / format
- Type-check
- Any audit / smoke scripts this branch ships

If the commands were run and passed during `/commit` or in recent conversation, state the actual pass counts (e.g. "112/112 passed"). Don't fabricate numbers you haven't seen.

### Test plan (reviewers)
Checklist of manual validation steps a reviewer should take before approving. Pull from the plan's "Validation" or "Verification" section if one exists. Include rollback verification for any feature-flagged change.

### Deferred
Explicit list of work consciously NOT in this PR. Pull from the plan's "Deferred" or "Out of scope" section. Each item should say why it's deferred and what unblocks it.

### Forward links
- Next phase / related MRs
- PRD this implements
- Related prior MRs (previous phases)

### Traceability index
Numbered list mapping every step of the development trail to a committed artifact on this branch:
1. Intent → PRD path + section
2. Plan → plan path
3. Pre-phase validation → findings path + spike scripts if any
4. Implementation → this commit range
5. Review → the MR description itself (this section)
6. Validation → testing table + audit scripts

This section is the whole point of the command — make it concrete, not generic.

## Creating the PR

GitLab:
```bash
glab mr create \
  --source-branch <current> \
  --target-branch <target> \
  --title "<title>" \
  --description "$(cat <body-file>)" \
  --no-editor \
  --yes
```

GitHub:
```bash
gh pr create \
  --base <target> \
  --head <current> \
  --title "<title>" \
  --body-file <body-file>
```

Write the description to a tmp file first (`/tmp/<branch-slug>-pr-body.md`) so HEREDOC / quoting issues don't swallow content.

If `glab mr list --source-branch <current>` or `gh pr list --head <current>` shows an existing open MR/PR from this branch, stop and ask the user: update the existing one via `glab mr update` / `gh pr edit`, or abort?

## Labels (best-effort)

Try to add labels that describe the work:
- Phase / initiative tag (e.g. `phase-1`) pulled from branch name if it matches the `phase-N` pattern
- Scope tag from commit type: `feat`, `fix`, `refactor`, `docs`, `test`
- Subsystem from files touched: `backend`, `frontend`, `observability`, `infra`, etc. Derive from top-level directory of modified paths.

Both `glab` and `gh` will silently skip unknown labels on repos that don't pre-define them — that's fine.

## Before finishing

Push the branch if not already pushed:
```bash
git push -u origin <current>
```

Report to the user:
- Platform detected (GitLab vs GitHub)
- Target branch
- MR / PR URL
- Labels applied
- A one-line traceability summary ("PR description links to plan X, findings Y, operator guide Z")

## Critical rules

- DO NOT invent findings, test counts, or artifacts that don't exist on the branch. Every link in the description must resolve to a real committed file.
- DO NOT strip or rewrite the latest commit message if it already contains the rich context — reuse and cite it.
- DO NOT push `--force`. If the branch is already tracked and needs updating, use regular push; if push is rejected, stop and ask.
- DO NOT bypass hooks (`--no-verify`, `--no-gpg-sign`).
- DO NOT target `main` from a WIP branch without confirming with the user — in phase-based projects the target is usually an integration branch.
- The PR description is the documentation of record for this work. Prioritize durability (links that still resolve a year from now) over cleverness.
