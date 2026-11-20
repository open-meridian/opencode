# Provenance

What this branch adds to OpenCode, and where each part came from. The repository stays under upstream's MIT
licence (`LICENSE`), with upstream's notices kept. Nothing here is copied from AGPL- or GPL-licensed code.

| What | Where it came from |
|---|---|
| Everything under `open-meridian/`, and `.github/workflows/open-meridian.yml` | Written for this branch. |
| The client name sent at registration (`packages/core/src/mcp/oauth.ts`, one line) | Changed on this branch from upstream's. |
| The example configuration, the agent and its permission rules | Written from OpenCode's own documentation (`services/site/src/docs/content/`: MCP servers, permissions, agents, providers). |
| The CI deployment's first run (`ci/first_run.py`) | Written for this branch from the Secret names and keys the released Open Meridian chart reads, as its values and templates name them; no code is taken from Open Meridian's repositories. |
| How the CI signs in (`ci/consent.py`) | Written for this branch against the deployment's consent page as it is served; it uses Playwright. |

## Third-party software the CI uses

Installed on the runner by the workflow, pinned by version or checksum, and not part of what a person copies:

| Software | Licence |
|---|---|
| argon2-cffi | MIT |
| Playwright for Python, and the Chromium it installs | Apache-2.0; Chromium's own licences |
| k3d, k3s | MIT; Apache-2.0 |
| Helm | Apache-2.0 |
| The Open Meridian CLI and chart, used as released | Their own licences; run, not copied |
