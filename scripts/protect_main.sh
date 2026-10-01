#!/usr/bin/env bash
# Protege main: exige PR, CI en verde (los tres jobs de ci.yml, rama al día) y prohíbe force push y borrado.
# Requiere permiso de admin y que el repo sea público o de una cuenta con GitHub Pro (si no, GitHub responde 403).
#
#   scripts/protect_main.sh [owner/repo]
set -euo pipefail
repo="${1:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
gh api -X PUT "repos/$repo/branches/main/protection" --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["Secretos (gitleaks)", "Backend, pipeline y harness", "Frontend"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0,
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_linear_history": false,
  "required_conversation_resolution": false
}
JSON
echo "main protegida en $repo"
gh api "repos/$repo/branches/main/protection" --jq '{checks: .required_status_checks.contexts, force_push: .allow_force_pushes.enabled, deletions: .allow_deletions.enabled, pr: (.required_pull_request_reviews != null)}'
