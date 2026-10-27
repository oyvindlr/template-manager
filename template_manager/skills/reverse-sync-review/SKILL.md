---
name: reverse-sync-review
description: Update a project's source template with reusable improvements from committed project changes, using template-manager's automated reverse-sync workspace.
---

# Reverse sync review

Promote reusable improvements with a durable template PR. Use deterministic commands for setup, mapping, validation, publication, and checkpoint updates; spend review time on classification and ambiguous edits. Read repository instructions and preserve unrelated work. Review committed changes only.

## 1. Prepare once

Run `template-reverse-sync --version` and `template-reverse-sync prepare --help` in the project's supported environment. If the console script is unavailable, use `python -m template_manager.reverse_sync`. Do not independently rediscover information already in the report.

```sh
template-reverse-sync --directory "$PROJECT" prepare \
  --until HEAD --remote origin --template-base main --workspace "$WORKSPACE"
```

Use a fresh absolute workspace outside both repositories. `prepare` freezes full endpoint SHAs, caches template objects/renders, creates isolated proposal/base/original checkouts, renders pinned/current templates, and writes `review.md`, `review.json`, `decisions.json`, settings fixtures, and `workspace.json`. Existing checkpoints take precedence; without one, the existing first-merge-after-template-baseline strategy applies. If it cannot resolve a sensible baseline, ask for a starting commit and rerun with `--since`. Reconcile differing local/remote checkpoints before continuing. Access errors never mean absence. Checkpoints remain unchanged.

For different values of affected custom parameters, pass a TOML overlay with `--alternate-settings` or edit the workspace's `alternate-settings.toml`. The default changes the project name and derived forms only. Exercise affected flags in both states, using extra fixture runs when necessary. CLI custom values are strings.

## 2. Classify, apply, and resolve exceptions

Read `review.md` and `decisions.json` first, then `changes.diff`. Groups have inventory paths, mapping hints, and a disposition. Exact rendered matches may already be marked `already upstream`; verify they fit the logical change. All other groups start `requires-review`.

- Set each group's disposition to `accepted`, `excluded`, `already upstream`, or `deferred`, with a short reason. Keep every inventory entry in order; related entries may share a reason. Inspect excluded candidates only when their paths/statistics/context suggest reusable infrastructure. Split mixed logical changes in your edits/report while retaining inventory coverage.
- Accept reusable scaffolding, build/test/CI, and documentation improvements. Exclude domain behavior, deployment identities, secrets, private endpoints, and machine paths. Ask only about ambiguity that affects the patch.

```sh
template-reverse-sync apply --workspace "$WORKSPACE"
```

`apply` only changes accepted, uniquely mapped literal text spans. Read the remaining `application: requires-review` reasons and edit the isolated `template` checkout directly. Additions, deletions, renames, modes, binary changes, conditionals, changed upstream code, and ambiguous substitutions need manual adaptation. Do not apply the project diff wholesale.

Preserve existing placeholders, syntax, conditionals, modes, and named UUID identities. Reuse semantically matching parameters/derived names. Document meaningful new parameters with purpose, example, type/string semantics, and actual defaults or required inputs. Jinja mode does not load cookiecutter.json or run Cookiecutter hooks. Universal constants stay literal. Keep project settings, private data, and review artifacts out of the template patch. Report generator changes separately.

## 3. Validate

Inspect `.template-tests.toml` and its referenced scripts before executing them. Then run:

```sh
template-reverse-sync validate --workspace "$WORKSPACE" --run-tests
```

Without a declared test contract, omit `--run-tests`; the report says `not-declared`, which is generation/static checking rather than build validation. The command renders the actual edited snapshot with source and alternate values into fresh directories, checks placeholders and leaked source values in filenames/content, and runs the declared argv command. It tests the base only on failure. Read `validation.md` and consult JSON/logs for details.

Investigate `regression` and `unresolved-failure`. Record `pre-existing-failure` and `environment/network-failure` with their evidence; do not repeatedly debug them as patch defects. Findings are conservative and may include intentional literal examples; assess them explicitly. Rerun after edits. For network issues, use `preflight --remote <remote> --timeout 20`; preserve TLS verification and distinguish actual errors from informational X.509 messages.

For reusable template CI, use `test-template` with source/alternate settings and the same declared contract; see the README's test contract.

## 4. Publish

Resolve all dispositions before publication; deferred work blocks publication/checkpoint advancement. Run:

```sh
template-reverse-sync publish --workspace "$WORKSPACE" --title "<reusable improvement>"
```

This checks the complete patch against its base, retains `template.patch` and `proposal.md`, commits/pushes the isolated branch without force, and creates or updates the matching GitHub PR (`gh`) or GitLab MR (`glab`). Use an authenticated provider CLI; `--provider` selects explicitly. Publication is authorized when this workflow is invoked unless user/repository instructions restrict it. Do not merge. Failed validation requires explicit `--draft`; inspect the failure first. No-change reviews skip publication. If publication fails, keep the workspace, patch, and branch and report the exact blocker.

Return the proposal URL, compact dispositions/parameter changes, validation and limitations, and exact reviewed SHAs. Avoid exposing private project details in a public proposal.

## 5. Ask once about the checkpoint

After review, explicitly ask whether to advance the recorded ref to `review.json`'s exact `until`, and whether to publish it. State current local/remote values, proposed SHA, and PR status. Explain that advancement removes this range from future reviews even if the PR closes; waiting for merge is valid. Wait for an explicit answer. Never change a checkpoint during preparation/publication.

After approval, use the guarded command; do not assemble raw Git ref pushes:

```sh
template-reverse-sync --directory "$PROJECT" mark-reviewed --from-review "$WORKSPACE/review.json"
# Only if remote publication was requested; expected SHA comes from review.json.
template-reverse-sync --directory "$PROJECT" mark-reviewed \
  --from-review "$WORKSPACE/review.json" --push origin --expected-remote "$OBSERVED_SHA"
```

Choose one command for the approved scope. An empty expected SHA is valid only for confirmed remote absence. The command verifies all dispositions, durable accepted proposals, exact endpoints, ancestry, unchanged checkpoint observations, and uses a lease. On changed refs/lease failure, reconcile; never force. Report actual local and remote states separately, including local success if remote publication failed. If approval is declined, leave refs unchanged.
