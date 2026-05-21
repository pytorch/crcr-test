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
