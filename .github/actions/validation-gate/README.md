# Validation Gate — Composite GitHub Action

CI-to-Linear feedback loop for AI-generated branches. Creates PRs on success, bounces tickets on failure.

## Usage

Reference this action from any AmakaFlow repo's validation workflow:

```yaml
# .github/workflows/agent-validation.yml
name: Validate AI Branch
on:
  push:
    branches: ['agent/**']

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build
        id: build
        run: |
          # your build command
          npm run build

      - name: Test
        id: test
        if: success()
        run: |
          npm test 2>&1 | tee test-output.txt
          echo "summary=Tests: $(grep -c 'PASS' test-output.txt) passed" >> "$GITHUB_OUTPUT"

      - name: Lint
        id: lint
        if: success()
        run: npm run lint

      # Capture which step failed (if any)
      - name: Determine outcome
        id: outcome
        if: always()
        run: |
          if [ "${{ steps.build.outcome }}" == "failure" ]; then
            echo "ci_outcome=failure" >> "$GITHUB_OUTPUT"
            echo "failed_step=build" >> "$GITHUB_OUTPUT"
          elif [ "${{ steps.test.outcome }}" == "failure" ]; then
            echo "ci_outcome=failure" >> "$GITHUB_OUTPUT"
            echo "failed_step=test" >> "$GITHUB_OUTPUT"
          elif [ "${{ steps.lint.outcome }}" == "failure" ]; then
            echo "ci_outcome=failure" >> "$GITHUB_OUTPUT"
            echo "failed_step=lint" >> "$GITHUB_OUTPUT"
          else
            echo "ci_outcome=success" >> "$GITHUB_OUTPUT"
            echo "failed_step=" >> "$GITHUB_OUTPUT"
          fi

      # Run the validation gate
      - name: Validation Gate
        if: always()
        uses: supergeri/amakaflow-automation/.github/actions/validation-gate@main
        with:
          linear-api-key: ${{ secrets.LINEAR_API_KEY }}
          repo-name: my-repo
          test-results-summary: ${{ steps.test.outputs.summary }}
          ci-outcome: ${{ steps.outcome.outputs.ci_outcome }}
          failed-step: ${{ steps.outcome.outputs.failed_step }}
          failure-logs: ${{ steps.test.outputs.logs || '' }}
```

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `linear-api-key` | Yes | — | Linear API key |
| `ticket-id` | No | (from branch) | Linear ticket ID (e.g., `AMA-123`) |
| `repo-name` | Yes | — | Repository name for Linear comments |
| `test-results-summary` | No | `"No test summary available."` | Markdown test summary |
| `ci-outcome` | Yes | — | `"success"` or `"failure"` |
| `failed-step` | No | `""` | Which step failed |
| `failure-logs` | No | `""` | Truncated error logs |
| `max-retries` | No | `2` | Max retries before Backlog escalation |
| `phase` | No | `"a"` | `"a"` (build/test/lint) or `"b"` (adds eval checks). Reserved for future use. |

## Outputs

| Output | Description |
|--------|-------------|
| `pr-url` | URL of the created PR (success only) |
| `action-taken` | `"pr-created"`, `"retry"`, `"escalated"`, or `"skipped"` |

## Behavior

### On Success
1. Creates PR with test summary and Linear link
2. Posts "CI passed" comment on Linear ticket
3. Ticket stays in "In Review" for human merge

### On Failure (retries remaining)
1. Posts failure comment with logs and `[retry:N/M]` tag
2. Moves ticket back to "Todo" for Antfarm retry

### On Failure (retries exhausted)
1. Posts escalation comment
2. Moves ticket to "Backlog"
3. Adds "Bug" label

## Requirements

- `LINEAR_API_KEY` secret in the calling repo
- `jq` available on the runner (pre-installed on GitHub-hosted runners)
- Branch follows `agent/AMA-{id}-{description}` naming convention
- GitHub label `"Auto-validated by CI"` must exist in the calling repo (created automatically on first PR if using `--label`)
