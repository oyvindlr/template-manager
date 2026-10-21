---
name: reverse-sync-review
description: Use template-manager's template-reverse-sync command to review committed project changes, classify project-specific versus reusable improvements, propose existing or new template parameters, produce and test a template patch, and open a pull request. Use when promoting improvements from a generated project back into its source template or reviewing changes since a reverse-sync checkpoint.
---

# Reverse sync review

Promote reusable project improvements into their source template with the smallest coherent change. Complete extraction, classification, parameterization, patching, validation, and a template-repository pull request. Keep review checkpoint changes separate and ask the user before creating or updating them.

## 1. Establish inputs and preserve work

This skill runs from a **generated project**, with access to its **source template repository**. Neither is the **template-manager package's source repository**, and a checkout of template-manager is not required. The Python package `template-manager` provides `template-reverse-sync` for extraction/checkpoints and `template-gen` for rendering test projects. Git and a template-manager version supporting reverse sync must be available in the active environment.

- Read applicable instructions in the generated project and source template repositories. Use the project's supported template-manager environment/version, resolving it from dependency declarations, lockfiles, or CI setup where possible; report the installed version with `python -c "from importlib.metadata import version; print(version('template-manager'))"` using that environment's Python interpreter.
- Check `template-reverse-sync --help`, `template-reverse-sync extract --help`, `template-reverse-sync mark-reviewed --help`, and `template-gen --help` in that environment before following the examples. If only the reverse-sync console entry point is missing, use `python -m template_manager.reverse_sync` with the same arguments. If the package or reverse-sync module is unavailable, report the missing prerequisite and resolve the supported installation/version before proceeding; do not silently install the latest release or implement a substitute extractor.
- If behavior differs from this workflow, consult documentation for the installed template-manager version and, when needed, its installed implementation. `template_manager/reverse_sync.py` is a path inside that package, not inside the generated project or template repository; locate it with `python -c "import template_manager.reverse_sync as m; print(m.__file__)"`. Generation is implemented in `template_manager.project_from_template` and can be located the same way. Do not assume a template-manager source checkout or its README is present.
- Identify the generated project repository, its review branch/target commit, `.template_settings.toml`, source template repository/subdirectory, pinned template revision, and intended template PR base branch. Ask only for information that cannot be resolved from configuration and history.
- Inspect Git status in both repositories. Preserve existing work. Use separate worktrees or temporary directories for template edits and generated test projects. Do not reset, clean, stash, commit, or upload unrelated user work.
- Review committed changes only. Report relevant uncommitted/untracked work as outside the review; do not silently commit it or claim it was reviewed.
- Resolve the project target to a full commit SHA once. Call it `UNTIL`; do not let a moving `HEAD` change the review scope.

## 2. Resolve the previous review reference

Use `refs/template-manager/reverse-sync/reviewed` unless repository configuration or the user selects another ref under `refs/template-manager/`. Call the selected ref `REF`.

1. Inspect the local ref and the corresponding ref on the project repository's configured review remote. Custom refs are not fetched by ordinary clones. Record the remote name and observed remote SHA, or its confirmed absence, for a later lease.
2. Fetch an existing remote ref into a separate temporary ref first. Compare local and remote checkpoints before choosing the baseline; do not overwrite a newer local checkpoint with a forced fetch. If divergent, or if multiple refs/remotes plausibly apply, resolve the ambiguity with the user. Treat authentication, network, and missing-history errors as errors, not evidence that no checkpoint exists.
3. If no previous-review ref exists, ask: **“Which project commit should be the starting reference for this review? Changes after that commit through <UNTIL> will be reviewed.”** Offer an identified initial generated commit as a suggestion if useful, but never choose one silently. Wait for the answer before extracting. Use `--since` without creating a ref yet.
4. Resolve the selected start to a full SHA, `SINCE`. Verify it is an ancestor of `UNTIL` and that both endpoints and their pinned template revisions are available. Fetch required history when necessary. Do not substitute a merge base or rewrite a checkpoint to bypass an ancestry error.

A supplied baseline commit is permission to use it for extraction, not permission to create or advance a checkpoint.

## 3. Extract and inspect the entire range

Run from the generated project repository root in the template-manager environment identified in step 1. In the shell examples, set `PROJECT` to that repository's absolute path and `REF`, `SINCE`, and `UNTIL` to the values resolved above. Set `BUNDLE` to a fresh absolute output-directory path outside both repositories. These are shell variables to assign before running the commands, not settings keys. Prefer `template-reverse-sync`; substitute `python -m template_manager.reverse_sync` if its console entry point is unavailable. Global `--directory` and `--checkpoint-ref` options precede the subcommand.

```sh
template-reverse-sync --directory "$PROJECT" --checkpoint-ref "$REF" extract \
  --since "$SINCE" --until "$UNTIL" -o "$BUNDLE"
```

Read `manifest.json`, `changes.diff`, and all manifest warnings. Verify that the manifest's full `since` and `until` SHAs equal the selected endpoints. Retain these exact SHAs for the report and checkpoint decision.

- Treat inclusion rules as candidate selection, not classification. Inspect the changed-path inventory for the entire range, including every excluded or `no-rule-matched` entry. Read excluded diffs when needed; re-extract with explicit `--include` patterns if useful. Explicit exclusions take precedence.
- Handle additions, deletions, renames, executable modes, and binary changes. Binary notices do not contain the changed data: inspect endpoint blobs separately when relevant, or mark the item deferred.
- Read surrounding code and configuration at the endpoints. Review net changes; do not reintroduce changes that were later reverted.
- Compare the pinned template revisions if settings changed. Imported template updates are not subtracted by the extractor. Identify improvements already present upstream and avoid proposing them again.
- Account for missing historical date/UUID seed warnings, conditional paths, and changed parameter values when mapping rendered files to source files. Do not modify the source project to make extraction succeed.

## 4. Classify changes and propose parameterization

Classify at hunk or logical-change level, splitting mixed files. Produce a compact review table with project path/change, classification, reason, template destination, parameter proposal, and disposition.

Use two classifications:

- **Project-specific:** application behavior, domain data, deployment identity, private endpoints, machine paths, secrets, or choices tied to this project's requirements. Leave these out of the template patch.
- **Template-relevant:** reusable infrastructure, build/test/CI improvements, fixes to generated scaffolding, documentation, or optional capabilities useful to other generated projects. Explain the reusable benefit.

Use dispositions such as `accepted`, `excluded`, `already upstream`, or `deferred`. Keep uncertain classification visibly unresolved and ask a focused question when it affects the patch. A deferred item prevents checkpoint advancement for the whole range.

For every accepted change:

1. Identify hardcoded project names, casing variants, namespaces, paths, URLs, author details, identifiers, and environment-specific values in contents and filenames.
2. Prefer an existing parameter or derived variable whose meaning matches. Inspect saved settings and template usage; do not match arbitrary text merely because its value happens to equal a parameter value.
3. Propose a new parameter only for a meaningful reusable variation. Specify its name, purpose, type/string interpretation, example, default or required status, and how callers supply it. Preserve the current project's behavior when its values are used. Present these proposals in the review report; resolve semantic ambiguity with the user, while implementing clear choices within the requested scope.
4. Keep universal constants literal. Avoid replacing every number or string and avoid adding a general configuration framework for a single change.
5. Follow the template's existing syntax and conventions. Use `%name%` in legacy syntax or `{{ name }}` / `{{ cookiecutter.name }}` in Jinja syntax. Preserve escaping, filters, indentation, and filename substitutions. Do not migrate syntax as an incidental change.
6. Use existing derived project-name forms instead of duplicate parameters. Preserve named UUID identities and the project's persisted seed. Use `%uuid(name)%` or `{{ uuid('name') }}` when appropriate; do not bake a project's generated GUID into a template.
7. Respect renderer semantics: template-manager's Jinja mode does not load `cookiecutter.json` or run Cookiecutter hooks. CLI custom values are strings; test string flags explicitly where required. Add required new values through the actual supported settings/CLI mechanism and document usage. Do not claim a default exists unless the renderer or template implements it.

## 5. Build a template-native patch

- Start a dedicated branch in the source template repository from the intended current PR base. Compare the project's pinned template revision with that base and adapt accepted changes to current source.
- Map rendered paths back to their parameterized template paths. Translate relevant hunks into template code; do not apply the project diff wholesale or copy rendered files over templates.
- Preserve placeholders, conditional branches, file modes, and unrelated template content. Include accepted additions, deletions, and renames intentionally. If a change belongs to the generator rather than the template, report or split it instead of hiding it in the template patch.
- Update parameter documentation/examples and relevant existing tests as needed. Exclude project settings, credentials, private data, extraction bundles, and generated output from the PR.
- Produce a standalone Git patch against the recorded template base, including new files and binary data when applicable. Inspect its complete diff and run `git diff --check` plus `git apply --check` against a clean checkout of that base. Do not commit the patch artifact into the template unless that repository requires it.
- If no template changes remain after review, report that result, skip the empty patch/PR, and continue to the checkpoint question.

## 6. Test the modified template

Test the actual patched source, not the old revision pinned in the project's saved settings.

Use `template-gen` from the environment identified in step 1 for generation; confirm its settings and output options with `template-gen --help`.

1. Render the base and patched template into fresh isolated output directories using the source project's parameters. Make temporary settings copies that explicitly point to the intended local source/revision and template subdirectory. Saved settings can override CLI arguments; verify the effective template revision, parameters, syntax, date, and UUID seed. Never edit the real project's settings for this test.
2. Disable remote project creation during generation (`--no-gitlab-project` with the current CLI). Control date/UUID seed for meaningful comparisons. Inspect generation behavior before assuming an uncommitted template worktree will be used.
3. Compare base versus patched output. Confirm accepted improvements render correctly, original project values are reproduced where intended, and excluded application changes have not leaked in. Explain expected differences rather than comparing the whole generated tree blindly with an evolved application.
4. Render again with a different project name and different values for every reused/new parameter involved in the patch. Exercise affected conditionals in both states, including absent optional values where supported. Check contents and filenames for leaked original values, unresolved placeholders, broken identifiers, or inconsistent references; allow intentional literal template examples.
5. Run template repository checks and relevant build/test/lint/configuration checks on the generated projects. Check UUID reference consistency when affected. Add focused regression coverage when it verifies a meaningful failure mode.
6. Record commands, configurations, results, and limitations. Distinguish successful generation from successful build/runtime validation. Fix introduced failures and rerun affected checks. If required validation is blocked, explain why and open only a clearly labeled draft PR; do not claim tests passed.

## 7. Create the pull request

When this workflow is invoked to perform reverse sync, proceed with the requested template branch, commit, push, and PR without an extra generic approval step unless the user or repository instructions restrict publication. Creating this skill alone does not authorize running reverse sync or opening a template PR now.

- Stage only the intended template changes. Commit and push the review branch without force-pushing shared history. Open a PR against the selected template base, or update the matching existing PR for this review rather than duplicating it. Do not merge it.
- Describe the reusable change, affected parameters and defaults/required inputs, validation results, and material limitations. Include the source project review range and review dispositions where appropriate; avoid disclosing private project details in a public template repository.
- Retain the standalone patch and review report as review artifacts outside generated/template source. Return the PR link and artifact locations, with exact reviewed endpoint SHAs.
- If publication fails, retain the branch, patch, and report and state the precise blocker. Do not claim a PR exists. Leave the checkpoint unchanged while accepted changes have no durable disposition.

## 8. Ask about creating/updating the review reference

After finishing the review, including a no-change review, explicitly ask whether to create or update the project review reference to the **manifest's exact `until` SHA**, and whether it should also be published to the project remote. State the current value or absence, proposed SHA, and PR status. Wait for an explicit answer before changing any checkpoint. Never advance to a newer `HEAD`.

- Advance only when every change in the range has a recorded disposition, including excluded candidates. Keep the reference unchanged if any work remains deferred or unresolved. A PR is a durable proposal, not a merged improvement: explain that advancing now means this range will not be offered again, even if the PR is later closed. Let the user decide whether to wait for merge.
- Before writing, re-read local and remote refs. If either changed since review began, stop and reconcile; do not overwrite another reviewer's progress. Verify the current local checkpoint is an ancestor of the proposed target.
- After approval, use `template-reverse-sync` in the same environment to update the local reference:

```sh
template-reverse-sync --directory "$PROJECT" --checkpoint-ref "$REF" mark-reviewed "$UNTIL"
```

- For publication, set `PROJECT_REMOTE` to the project remote recorded in step 2 and `EXPECTED_REMOTE_SHA` to its observed checkpoint SHA (or an empty string for confirmed absence). Publish only if requested, using a lease against the **observed remote ref SHA**. It is often the manifest's `since`, but can differ when an explicit baseline was supplied. Use an empty expected SHA only when the remote ref was confirmed absent:

```sh
git -C "$PROJECT" push --force-with-lease="$REF:$EXPECTED_REMOTE_SHA" \
  "$PROJECT_REMOTE" "$REF:$REF"
```

- If the lease fails, fetch and reconcile; never retry with an unconditional force push. Report local-only success separately from remote success and leave newer refs intact.
- If the user declines, leave the reference unchanged. End with the review result, patch/PR, tests, and actual checkpoint state.
