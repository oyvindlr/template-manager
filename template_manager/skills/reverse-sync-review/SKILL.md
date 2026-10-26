---
name: reverse-sync-review
description: Update a project's source template with reusable improvements from recent project changes. Use when reviewing changes since a reverse-sync checkpoint or promoting project improvements back into the template.
---

# Reverse sync review

Use recent committed changes in a project to update the template the project was created from. Identify reusable improvements, adapt them to the template's parameters, test the result, and open a template pull request.

**template-manager** is the Python command-line tool used to generate the project from that template. Prefer `template-reverse-sync review`, which produces the primary evidence for this workflow; use `template-gen` for targeted generated-project validation. Optimize for a useful, durable template proposal rather than exhaustive or perfect reverse engineering.

## 1. Identify the project, template, and review range

- Read repository instructions. Preserve existing work; use separate worktrees or temporary directories for template edits and generated tests.
- Set these shell variables for the examples: `PROJECT` is the project's absolute repository path; `UNTIL` is the full target commit SHA, resolved once; `REF` is `refs/template-manager/reverse-sync/reviewed` unless another ref under `refs/template-manager/` is selected; `PROJECT_REMOTE` is the review remote; and `TEMPLATE_BASE` is the intended template PR base.
- Run `template-reverse-sync --version`, then let the review report identify settings, repository state, template source/revision/base, and local/remote checkpoint state.
- When no checkpoint exists, accept the command's `first-merge-after-template-baseline` baseline if it matches the project history. Ask the user only when the report fails to identify one or the suggested merge is clearly wrong; rerun with `--since`.
- Resolve divergent checkpoints, ambiguous remotes, or access errors with the user. Access errors do not establish absence.

## 2. Extract and review changes

Set `BUNDLE` to a fresh absolute directory outside both repositories. Global options precede the subcommand:

```sh
template-reverse-sync --directory "$PROJECT" --checkpoint-ref "$REF" review \
  --until "$UNTIL" --remote "$PROJECT_REMOTE" --template-base "$TEMPLATE_BASE" \
  -o "$BUNDLE"
```

If the console entry point is unavailable, use `python -m template_manager.reverse_sync` in the same environment. If the module is also missing, resolve the supported installation before proceeding.

Read `review.md` first and use `review.json` as the authoritative structured context. Verify its endpoints and baseline source. Read `changes.diff` for selected candidates.

- Start with entries classified `likely-template-relevant` or `ambiguous`.
- Treat classification hints as triage only. Inspect `likely-project-specific` entries in `all-changes.diff` only when their path, statistics, commit subject, or relationship to an accepted change suggests reusable infrastructure.
- Group related files into logical changes and assign one disposition per group. It is acceptable to disposition obviously domain-specific entries together.
- Read surrounding project/template code only for accepted or genuinely uncertain changes. Do not independently repeat repository, checkpoint, settings, commit, or inventory discovery already present in the report.
- Account for report warnings, parameterized paths, settings changes, renames, modes, and binary entries. Defer anything that cannot be assessed safely.

Produce a compact table of each logical change, its classification, reason, template destination, parameter proposal, and disposition:

- **Project-specific:** application/domain behavior, deployment identities, private endpoints, machine paths, or secrets. Exclude from the template.
- **Template-relevant:** reusable scaffolding, infrastructure, build/test/CI, documentation, or optional capabilities.

Record dispositions such as `accepted`, `excluded`, `already upstream`, or `deferred`. Resolve only uncertainty that materially affects the patch with the user.

## 3. Adapt accepted changes to the template

- Branch from the intended current template PR base. Map generated paths and hunks back to template source; adapt to upstream changes rather than applying the project diff wholesale.
- Replace project-specific values in contents and filenames with semantically matching existing parameters or derived names. Keep universal constants literal.
- Introduce parameters only for useful variation. Document each new parameter's purpose, type, example, default or required status, and supported way to supply it. Preserve the original project's behavior with its values.
- Follow existing syntax: `%name%` for legacy templates or `{{ name }}` / `{{ cookiecutter.name }}` for Jinja. Preserve escaping, conditionals, file modes, and named UUID identities (`%uuid(name)%` or `{{ uuid('name') }}`).
- template-manager's Jinja renderer does not load `cookiecutter.json` or run Cookiecutter hooks. CLI custom values are strings; test flag semantics and implement any claimed defaults.
- Update relevant documentation and tests. Keep project settings, private data, extraction bundles, and generated output out of the template patch. Report generator changes separately.
- Run `git diff --check`. Retain a standalone patch only when publication fails or the user requests one; a pushed branch and pull request are otherwise the durable proposal.

## 4. Validate generated projects

Use `template-gen` to render the patched template into isolated directories.

- Use temporary settings copies pointing to the intended source, revision, and subdirectory. Saved settings can override CLI arguments. Verify the effective source and parameters; do not assume generation uses uncommitted template edits.
- Disable remote project creation with `--no-gitlab-project`. Control rendering date and UUID seed for meaningful comparisons.
- Render once with the source project's values and once with different values for affected parameters. Check contents and filenames for leaked project values, unresolved placeholders, and inconsistent identifiers.
- Render the unmodified base only when the change affects rendering semantics, the patched render fails unexpectedly, or a meaningful before/after comparison is needed.
- Run the smallest generated-project check covering the accepted changes. A successful targeted check is sufficient; broaden only when failures or risk justify it.
- Record material limitations. Use a draft PR only when a failure makes the proposal unsafe to review, not for minor warnings or incomplete optional validation.

## 5. Publish the proposal

Commit and push only intended template changes, then open or update the matching template PR without an extra generic approval step. Follow any user/repository publication restrictions; do not merge or force-push shared history.

Describe the reusable changes, parameter usage, validation, and material limitations. Return the PR, review table, and exact reviewed SHAs. Return a standalone patch only if one was needed. Avoid exposing private project details. If publication fails, retain local artifacts and report the blocker.

If no template changes remain, skip the empty patch/PR and report that result.

## 6. Ask before updating the checkpoint

After review, explicitly ask whether to create/update `REF` to `review.json`'s **exact `until` SHA**, and whether to publish it to the project remote. State its current value or absence and the PR status. Wait for an explicit answer.

Only advance when every change, including excluded candidates, has a disposition and accepted changes have a durable proposal. Deferred or unresolved work blocks advancement. Explain that advancing excludes this range from future reviews even if the PR is later closed; the user may prefer to wait for merge.

Before writing, re-read local and remote refs. Reconcile any changes since review began, and verify the local checkpoint is an ancestor of the target. After approval:

```sh
template-reverse-sync --directory "$PROJECT" --checkpoint-ref "$REF" mark-reviewed "$UNTIL"
```

Publish only if requested. Set `PROJECT_REMOTE` to the recorded project remote and `EXPECTED_REMOTE_SHA` to its observed checkpoint SHA; use an empty string only for confirmed absence:

```sh
git -C "$PROJECT" push --force-with-lease="$REF:$EXPECTED_REMOTE_SHA" \
  "$PROJECT_REMOTE" "$REF:$REF"
```

If the lease fails, fetch and reconcile instead of forcing. Report the actual local and remote checkpoint states. If approval is declined, leave them unchanged.
