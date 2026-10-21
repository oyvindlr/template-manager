---
name: reverse-sync-review
description: Update a project's source template with reusable improvements from recent project changes. Use when reviewing changes since a reverse-sync checkpoint or promoting project improvements back into the template.
---

# Reverse sync review

Use recent committed changes in a project to update the template the project was created from. Identify reusable improvements, adapt them to the template's parameters, test the result, and open a template pull request.

**template-manager** is the Python command-line tool used to generate the project from that template. Its commands are available: `template-reverse-sync` extracts changes and manages review checkpoints; `template-gen` generates projects for testing. Use their `--help` output for options. Work from the generated project; a checkout of template-manager itself is unnecessary.

## 1. Identify the project, template, and review range

- Read repository instructions and `.template_settings.toml`. Identify the source template repository/subdirectory, pinned template revision, and intended template PR base. Use the project's supported template-manager environment and report its version.
- Check Git status in both repositories. Preserve existing work; use separate worktrees or temporary directories for template edits and generated tests. Review committed changes only and report relevant uncommitted work separately.
- Set these shell variables for the examples: `PROJECT` is the project's absolute repository path; `UNTIL` is the full target commit SHA, resolved once; `REF` is `refs/template-manager/reverse-sync/reviewed` unless another ref under `refs/template-manager/` is selected.
- Inspect the local checkpoint and its counterpart on the project's review remote. Record the remote name and observed SHA or confirmed absence. Custom refs are not fetched by ordinary clones: fetch an existing remote checkpoint into a temporary ref and compare it with the local one. Resolve divergent checkpoints or ambiguous remotes with the user. Access errors do not establish absence.
- If no checkpoint exists, ask which project commit should start the review and wait for the answer. Suggest the initial generated commit if identifiable. Use the answer as an extraction baseline without creating a checkpoint.
- Resolve the baseline to full SHA `SINCE`; verify it is an ancestor of `UNTIL` and required project/template history is available. Do not silently substitute a merge base.

## 2. Extract and review changes

Set `BUNDLE` to a fresh absolute directory outside both repositories. Global options precede the subcommand:

```sh
template-reverse-sync --directory "$PROJECT" --checkpoint-ref "$REF" extract \
  --since "$SINCE" --until "$UNTIL" -o "$BUNDLE"
```

If the console entry point is unavailable, use `python -m template_manager.reverse_sync` in the same environment. If the module is also missing, resolve the supported installation before proceeding.

Read `manifest.json`, `changes.diff`, and warnings. Verify the manifest endpoints match `SINCE` and `UNTIL`.

- Inspect the entire changed-path inventory, including excluded and `no-rule-matched` entries. Inclusion rules select candidates, not reusable improvements. Read excluded diffs as needed; `--include` can expand selection, but explicit exclusions take priority.
- Review net changes with surrounding code. Include additions, deletions, renames, file modes, and relevant binary blobs; defer anything you cannot assess.
- Compare pinned template revisions when settings changed. The extractor does not subtract imported template updates; avoid proposing changes already upstream.
- Account for changed parameters, conditional paths, and missing historical date/UUID seed warnings when mapping generated files back to templates.

Produce a compact table of each logical change, its classification, reason, template destination, parameter proposal, and disposition:

- **Project-specific:** application/domain behavior, deployment identities, private endpoints, machine paths, or secrets. Exclude from the template.
- **Template-relevant:** reusable scaffolding, infrastructure, build/test/CI, documentation, or optional capabilities.

Record dispositions such as `accepted`, `excluded`, `already upstream`, or `deferred`. Resolve uncertainty affecting the patch with the user.

## 3. Adapt accepted changes to the template

- Branch from the intended current template PR base. Map generated paths and hunks back to template source; adapt to upstream changes rather than applying the project diff wholesale.
- Replace project-specific values in contents and filenames with semantically matching existing parameters or derived names. Keep universal constants literal.
- Introduce parameters only for useful variation. Document each new parameter's purpose, type, example, default or required status, and supported way to supply it. Preserve the original project's behavior with its values.
- Follow existing syntax: `%name%` for legacy templates or `{{ name }}` / `{{ cookiecutter.name }}` for Jinja. Preserve escaping, conditionals, file modes, and named UUID identities (`%uuid(name)%` or `{{ uuid('name') }}`).
- template-manager's Jinja renderer does not load `cookiecutter.json` or run Cookiecutter hooks. CLI custom values are strings; test flag semantics and implement any claimed defaults.
- Update relevant documentation and tests. Keep project settings, private data, extraction bundles, and generated output out of the template patch. Report generator changes separately.
- Retain a standalone Git patch against the recorded template base, including new files and binary data as needed. Check its full diff with `git diff --check` and `git apply --check` against a clean checkout of that base.

## 4. Validate generated projects

Use `template-gen` to render both the base and patched template into isolated directories.

- Use temporary settings copies pointing to the intended source, revision, and subdirectory. Saved settings can override CLI arguments. Verify the effective source and parameters; do not assume generation uses uncommitted template edits.
- Disable remote project creation with `--no-gitlab-project`. Control rendering date and UUID seed for meaningful comparisons.
- First render with the source project's values; confirm accepted improvements appear and excluded changes do not.
- Render with a different project name and different values for affected parameters. Exercise affected conditionals, including absent optional values where supported. Check contents and filenames for leaked project values, unresolved placeholders, and inconsistent identifiers.
- Run relevant template and generated-project checks. Record commands, results, and limitations; generation alone does not establish build/runtime correctness. Fix introduced failures. If required validation remains blocked, open only a draft PR explaining the limitation.

## 5. Publish the proposal

Commit and push only intended template changes, then open or update the matching template PR without an extra generic approval step. Follow any user/repository publication restrictions; do not merge or force-push shared history.

Describe the reusable changes, parameter usage, validation, and material limitations. Return the PR, standalone patch, review table, and exact reviewed SHAs. Avoid exposing private project details. If publication fails, retain local artifacts and report the blocker.

If no template changes remain, skip the empty patch/PR and report that result.

## 6. Ask before updating the checkpoint

After review, explicitly ask whether to create/update `REF` to the **manifest's exact `until` SHA**, and whether to publish it to the project remote. State its current value or absence and the PR status. Wait for an explicit answer.

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
