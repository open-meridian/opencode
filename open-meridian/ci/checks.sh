#!/bin/bash
# What this fork adds, held to its rules. Run from the repository's root.
#
# 1. Paths: what a person copies from open-meridian/workspace/ reaches a
#    deployment through its MCP server alone -- no cluster tool, no database
#    or bus address, no dashboard cookie or terminal, no plugin host -- and
#    names no address but the server's /mcp (and the config schema's).
# 2. Names: nothing we add names a private sample or an internal name.
# 3. Licences: nothing we add brings a package into the workspace's
#    dependencies, carries an AGPL or GPL notice, or drops upstream's MIT
#    licence; the provenance file is there.
set -euo pipefail
failed=0
fail() { echo "checks: $*" >&2; failed=1; }

base="${BASE_REF:-origin/open-meridian}"
ours=(open-meridian .github/workflows/open-meridian.yml)

# 1. Paths.
if grep -RInE 'kubectl|helm |k3d|psql|postgres(ql)?://|nats://|:4222|/terminal|Cookie|plugins\.[a-z]|/sign-in|/oauth/token|Bearer ' \
     open-meridian/workspace; then
  fail "open-meridian/workspace names a path to the deployment other than its MCP server"
fi
while IFS= read -r url; do
  case "$url" in
    https://opencode.ai/config.json|https://meridian.localhost/mcp) ;;
    *) fail "open-meridian/workspace names an address that is not the server's /mcp: $url" ;;
  esac
done < <(grep -RhoE 'https?://[^" ),]+' open-meridian/workspace | sort -u)

# 2. Names.
if grep -RIniE 'persona|plugin-sample|sample-(fx|multi-asset|options|pricing|reporting|operations)|discretionary pm|systematic pm' \
     "${ours[@]}" --exclude=checks.sh; then
  fail "a private sample or an internal name appears in what we add"
fi

# 3. Licences.
if git diff --name-only "$base" HEAD -- package.json bun.lock 'packages/*/package.json' | grep -q .; then
  fail "our changes touch the workspace's dependencies"
fi
if grep -RIlE 'GNU (Affero )?General Public License|AGPL-3|SPDX-License-Identifier: *(A?GPL)' "${ours[@]}" --exclude=checks.sh; then
  fail "an AGPL or GPL notice in what we add"
fi
grep -q '^MIT License' LICENSE || fail "upstream's MIT licence is not at LICENSE"
[ -f open-meridian/PROVENANCE.md ] || fail "open-meridian/PROVENANCE.md is missing"

[ "$failed" -eq 0 ] && echo "checks: paths, names and licences hold"
exit "$failed"
