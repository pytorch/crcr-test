# Cross-Repository CI Relay (CRCR) — Onboarding Guide

This repository serves as the **reference implementation and test bed** for the [Cross-Repository CI Relay (CRCR)](https://github.com/pytorch/rfcs/blob/master/RFC-0050-Cross-Repository-CI-Relay-for-PyTorch-Out-of-Tree-Backends.md) system. It demonstrates how an out-of-tree (OOT) backend can receive upstream PyTorch events and run its own CI in response.

Use this guide to onboard your downstream repository into the CRCR pipeline.

## How It Works

When a PR is opened or code is pushed to `pytorch/pytorch`, the [pytorch-fdn-cross-repo-ci-relay](https://github.com/apps/pytorch-fdn-cross-repo-ci-relay) GitHub App dispatches `repository_dispatch` events to all approved downstream repositories. Your repository receives these events and can trigger builds, tests, or any workflow in response.

```
pytorch/pytorch (PR / push)
        │
        ▼
  CRCR Relay Bot
  (pytorch-fdn-cross-repo-ci-relay)
        │
        ▼
  repository_dispatch
        │
        ├──► your-org/your-repo  (your workflow runs)
        ├──► Ascend/pytorch
        ├──► riseproject-dev/pytorch-ci
        └──► pytorch/crcr-test
```

## Trust Levels

Each downstream repository is assigned a trust level that determines how deeply it integrates with PyTorch CI:

| Level | Name | Description |
|-------|------|-------------|
| **L1** | Onboarding | Events are forwarded to downstream, but upstream receives no feedback. |
| **L2** | Observation | Downstream CI results are displayed on the [HUD](https://hud.pytorch.org) page, but not on PRs. |
| **L3** | Stable | Adds a non-blocking check run on PRs when `ciflow/oot/<name>` label is applied. |
| **L4** | Mature | Adds a blocking check run on every PR; reserved for critical accelerators. |

All new repositories start at **L1**. Promotion to higher levels is based on demonstrated stability and reliability.

## Onboarding Steps

### Step 1: Install the CRCR GitHub App

Install the [pytorch-fdn-cross-repo-ci-relay](https://github.com/apps/pytorch-fdn-cross-repo-ci-relay) GitHub App on your downstream repository.

For installation approval, contact **[@albanD](https://github.com/albanD)** or **[@atalman](https://github.com/atalman)**.

### Step 2: Add Your Repository to the Allowlist

Open a PR against [`pytorch/pytorch`](https://github.com/pytorch/pytorch) to add your repository to the allowlist file:

**File:** [`.github/allowlist.yml`](https://github.com/pytorch/pytorch/blob/main/.github/allowlist.yml)

Add your repository under the appropriate level (new repos start at L1):

```yaml
L1:
  - pytorch/crcr-test
  - Ascend/pytorch
  - riseproject-dev/pytorch-ci
  - your-org/your-repo          # ← add your repo here
```

### Step 3: Create a Dispatch Receiver Workflow

Create a GitHub Actions workflow in your repository that listens for `repository_dispatch` events. The relay sends two event types:

- **`push`** — Triggered when code is pushed to `main` or ciflow tags are created (e.g., `refs/tags/ciflow/trunk/<pr_number>`)
- **`pull_request`** — Triggered when a PR is opened, reopened, synchronized, or closed

Create `.github/workflows/out-of-tree-ci.yml` in your repository:

```yaml
name: PyTorch Out-of-Tree Dispatch

on:
  repository_dispatch:
    types:
      - pull_request
      - push

run-name: >-
  Dispatch -
  ${{
    github.event.client_payload.event_type == 'pull_request' &&
    format(
      'PR #{0} ({1})',
      github.event.client_payload.payload.pull_request.number,
      github.event.client_payload.payload.action
    ) ||
    github.event.client_payload.payload.ref
  }}

concurrency:
  group: >-
    oot-${{ github.event.client_payload.payload.repository.full_name }}-${{
    github.event.client_payload.payload.pull_request.number || github.run_id }}
  cancel-in-progress: true

permissions:
  actions: write
  id-token: write   # required for L2+ callback authentication (OIDC)

jobs:
  cancel-workflow:
    if: ${{ github.event.client_payload.payload.action == 'closed' }}
    runs-on: ubuntu-latest
    steps:
      - run: echo "PR closed, canceling older runs in the same concurrency group"
  build-and-test:
    if: ${{ github.event.client_payload.payload.action != 'closed' }}  # listen to the specific action types you need (opened, reopened, synchronize)
    runs-on: ubuntu-latest
    steps:
      - name: Checkout your repository
        uses: actions/checkout@v4

      - name: Checkout PyTorch at dispatched SHA
        uses: actions/checkout@v4
        with:
          repository: pytorch/pytorch
          ref: ${{ github.event.client_payload.payload.pull_request.head.sha || github.event.client_payload.payload.after }}
          path: pytorch

      # Add your build and test steps here
      - name: Build and test
        run: |
          echo "Building against PyTorch SHA: ${{ github.event.client_payload.payload.pull_request.head.sha || github.event.client_payload.payload.after }}"
          # your build commands here

      - name: Log event to step summary
        if: always()
        run: |
          cat <<'SUMMARY' >> $GITHUB_STEP_SUMMARY
          ```json
          ${{ toJson(github.event) }}
          ```
          SUMMARY
```

### Step 4: Verify the Integration

Once Steps 1–3 are complete, your workflow will start receiving dispatches. You can verify this by:

1. Checking the **Actions** tab of your repository for `repository_dispatch` events
2. Looking for runs triggered by `pytorch-fdn-cross-repo-ci-relay[bot]`
3. Inspecting the step summary for the full event payload

## Critical Tests

This repository is a **downstream CRCR health probe**. It contains no CRCR implementation code — only workflows and validators that run when the relay sends a live `repository_dispatch` event.

**There is no scheduled cron.** All CRCR health checks run in real time, triggered by upstream PyTorch activity (PR open/sync/close or push/tag events). Each run writes a structured `health-report.json` artifact you can use for metrics.

| Workflow | Level | Trigger | What it verifies |
|----------|-------|---------|------------------|
| [`crcr-dispatch-receiver.yml`](.github/workflows/crcr-dispatch-receiver.yml) | L1 | live `repository_dispatch`: `pull_request`, `push` | Dispatch payload, checkout SHA, `delivery_id`; HUD callbacks on `opened`/`reopened` only |
| [`crcr-l2-ci.yml`](.github/workflows/crcr-l2-ci.yml) | L2 | live `repository_dispatch`: `pull_request` (`opened`/`reopened` only) | L1 checks + smoke + `in_progress`/`completed` callbacks, HUD metrics |
| [`crcr-unit-tests.yml`](.github/workflows/crcr-unit-tests.yml) | Offline | push/PR to this repo only | Validator unit tests against JSON fixtures (guards test code, not live CRCR) |

### Event filtering (relay rate limits)

The relay callback Lambda enforces a per-repo sliding-window rate limit (see [crcr-test#8](https://github.com/pytorch/crcr-test/issues/8)). A full L1+L2 probe sends **4 callbacks** (`in_progress` + `completed` x2). PyTorch `synchronize` events are high volume and can exceed the limit during busy periods.

Health probes use **tiered coverage** by event type:

| Event | L1 workflow | L2 workflow | Relay callbacks | HUD rows |
|-------|-------------|-------------|-----------------|----------|
| `opened`, `reopened` | Full probe + HUD | Full probe + HUD | **4** | **2** |
| `synchronize` | Light probe (validate + checkout) | Skipped | **0** | **0** |
| `closed` | Cancel job only | Cancel job only | **0** | **0** |
| `push` / ciflow tag | Light probe (validate + checkout) | N/A | **0** | **0** |

**Light probe** (`l1-light`): validates dispatch payload, checks out PyTorch at the dispatched SHA, verifies the checkout, asserts `delivery_id`, uploads `health-report.json` — no relay callbacks.

**Full probe** (`l1-critical` / `l2-critical`): light checks plus `in_progress`/`completed` callbacks and HUD `test_results`. Callback mechanics are the same regardless of PR `action`; limiting callbacks to `opened`/`reopened` keeps coverage on low-volume events while `synchronize` still exercises dispatch delivery every upstream push.

### When tests run

| Event | What runs |
|-------|-----------|
| PyTorch PR `opened` / `reopened` | L1 full + L2 full (HUD callbacks) |
| PyTorch PR `synchronize` | L1 light only (no callbacks, no L2) |
| PyTorch PR `closed` | L1/L2 cancel jobs only (build jobs skipped) |
| PyTorch push / ciflow tag | L1 light only (no callbacks) |
| Merge to crcr-test main | `crcr-unit-tests` only (offline contract tests) |

### L1 integration points

- `client_payload.event_type` is `pull_request` or `push`
- `client_payload.delivery_id` is present (required for L2 state tracking)
- `client_payload.payload.repository.full_name` is `pytorch/pytorch`
- PR events: `action` in `opened`/`reopened`/`synchronize`/`closed`, valid `pull_request.head.sha`
- Push events: `ref` starts with `refs/`, valid `after` SHA
- PyTorch checkout resolves to the dispatched SHA
- `closed` action runs only the cancel job (no build)
- **`opened`/`reopened`**: full probe with `in_progress`/`completed` callbacks to HUD
- **`synchronize`/`push`**: light probe only (payload + checkout; no callbacks)

### L2 integration points

- Runs only on PR `opened` and `reopened` (skipped on `synchronize` to limit callback volume)
- OIDC token minting (`id-token: write`)
- `in_progress` callback accepted by relay (state machine: `DISPATCHED → IN_PROGRESS`)
- Deterministic smoke checks (no random pass/fail)
- `completed` callback with `conclusion` and `test_results` derived from health checks
- Each health check maps to one HUD test count (`passed` / `failed` / `total`)
- `artifact_url` points at the GitHub Actions run page
- Results visible on [hud.pytorch.org/crcr/pytorch/crcr-test](https://hud.pytorch.org/crcr/pytorch/crcr-test)

### HUD health metrics

L1 and L2 workflows send health probe results to the callback lambda on the `completed`
callback. The relay forwards them to HUD as `workflow.test_results`:

| Health check step outcome | HUD field |
|---------------------------|-----------|
| `success` | counts toward `passed_tests` |
| `failure` / `cancelled` | counts toward `failed_tests` |
| `skipped` | counts toward `skipped_tests` |

`total_tests` is the number of probe checks. `conclusion` is `success` only when every
check succeeded. Per-check names live in the uploaded `health-report.json` artifact.

### Running validators locally

```bash
# Validate a fixture or saved client_payload JSON
python3 tests/validate_dispatch_payload.py < tests/fixtures/pull_request_opened.json

# Run all unit tests
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## Dispatch Payload Structure

The relay wraps the original GitHub event inside `client_payload`:

```json
{
  "event_type": "push",
  "client_payload": {
    "event_type": "push",
    "payload": {
      "ref": "refs/tags/ciflow/trunk/184534",
      "after": "abc123...",
      "deleted": false,
      "base_ref": "refs/heads/main",
      "repository": {
        "full_name": "pytorch/pytorch"
      }
    }
  }
}
```

For `pull_request` events:

```json
{
  "event_type": "pull_request",
  "client_payload": {
    "event_type": "pull_request",
    "payload": {
      "action": "opened",
      "pull_request": {
        "number": 184442,
        "title": "My PR title",
        "head": {
          "sha": "abc123...",
          "repo": {
            "full_name": "user/pytorch"
          }
        }
      },
      "repository": {
        "full_name": "pytorch/pytorch"
      }
    }
  }
}
```

## Key Fields Reference

| Field | Path | Description |
|-------|------|-------------|
| Event type | `github.event.client_payload.event_type` | `push` or `pull_request` |
| Upstream repo | `github.event.client_payload.payload.repository.full_name` | Always `pytorch/pytorch` |
| Push ref | `github.event.client_payload.payload.ref` | Git ref (e.g., `refs/tags/ciflow/trunk/12345`) |
| Push SHA | `github.event.client_payload.payload.after` | Commit SHA for push events |
| PR number | `github.event.client_payload.payload.pull_request.number` | PR number for pull_request events |
| PR action | `github.event.client_payload.payload.action` | `opened`, `reopened`, `synchronize`, `closed` |
| PR head SHA | `github.event.client_payload.payload.pull_request.head.sha` | Head commit SHA of the PR |
| PR head repo | `github.event.client_payload.payload.pull_request.head.repo.full_name` | Fork repo (if applicable) |

## Rate Limiting

The CRCR relay Lambda enforces server-side rate limiting to protect backend infrastructure (Redis, ClickHouse) from callback bursts. The current limit is **60 requests per minute** across all downstream repositories. When multiple downstream repositories send callbacks concurrently — for example, during a large upstream PR push that fans out to many repos — the relay may respond with **HTTP 429 (Too Many Requests)**.

### What Happens on 429

The default callback action (`cross-repo-ci-relay-callback`) uses `curl --fail-with-body`, which treats any non-2xx response as a hard failure. A single transient 429 will fail the callback step and mark the job as errored, even though the rate limit is temporary.

### Recommended: Client-Side Retry with Backoff

As discussed in [#8](https://github.com/pytorch/crcr-test/issues/8), the preferred mitigation is **client-side retry with exponential backoff** rather than raising the server-side threshold. The server-side limiter is a protection that should be preserved — no fixed limit can guarantee a concurrent burst never crosses it.

**Why retry over raising limits** (per [@can-gaa-hou](https://github.com/can-gaa-hou)):
> 429 is inherently transient, so the right place to handle it is the client. Adding retry with backoff (ideally honoring a `Retry-After` header from the relay) makes the callbacks resilient to bursts without weakening the server-side guard.

### Best Practices for Downstream Repositories

1. **Add jitter to workflow steps** — If your workflow has multiple jobs sending callbacks, stagger them with random delays (`sleep $((RANDOM % 10))`) to avoid synchronized bursts.
2. **Anticipate 429 responses** — Design your callback steps to tolerate transient failures. A retry wrapper around the `curl` call can prevent unnecessary job failures.
3. **Honor `Retry-After` headers** — If the relay includes a `Retry-After` header in 429 responses, wait at least that long before retrying.
4. **Limit concurrent callback jobs** — Use GitHub Actions concurrency groups to avoid overwhelming the relay with parallel callbacks from the same repository.

### Planned Improvements

- Client-side retry with backoff in the `cross-repo-ci-relay-callback` action ([pytorch/test-infra](https://github.com/pytorch/test-infra))
- `Retry-After` header support in the relay Lambda

## Related Resources

- [RFC-0050: Cross-Repository CI Relay](https://github.com/pytorch/rfcs/blob/master/RFC-0050-Cross-Repository-CI-Relay-for-PyTorch-Out-of-Tree-Backends.md) — Full CRCR design specification
- [Allowlist](https://github.com/pytorch/pytorch/blob/main/.github/allowlist.yml) — Current list of approved downstream repositories
- [CRCR Relay GitHub App](https://github.com/apps/pytorch-fdn-cross-repo-ci-relay) — The relay bot
- [Tracking Issue](https://github.com/pytorch/pytorch/issues/175022) — CRCR tracking issue

## Contacts

For questions about onboarding, installation approval, or promotion to higher trust levels:

- **[@albanD](https://github.com/albanD)** — PyTorch Core Maintainer
- **[@atalman](https://github.com/atalman)** — PyTorch Dev Infra
- **[@groenenboomj](https://github.com/groenenboomj)**
- **[@jewelkm89](https://github.com/jewelkm89)**
- **[@subinz1](https://github.com/subinz1)**
- **[@fffrog](https://github.com/fffrog)**
