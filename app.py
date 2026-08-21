"""Extension declaration, secrets, lifecycle hooks.

WHY BYOK (bring-your-own-key), SAME REASONING AS n8n Connector / MuleSoft
Connector / Automation Anywhere Connector. GitLab lives inside the USER'S
OWN account -- either gitlab.com SaaS or their own self-managed instance --
Imperal cannot and should not broker access to someone else's GitLab
account/instance centrally.

WHY base_url + access_token (TWO SECRETS), NOT AN OAUTH ENTRY, SAME SHAPE
AS n8n Connector.

GitLab's REST API is served at `<instance>/api/v4/...` for BOTH gitlab.com
SaaS and any self-managed instance (confirmed docs.gitlab.com/api/rest/,
2026-08-21) -- there is no finite set of hosts to auto-discover the way
Make.com's zone can be. The connect form therefore asks for the instance
base_url directly (defaulting to https://gitlab.com for the common case),
plus a Personal Access Token.

WHY `PRIVATE-TOKEN` HEADER, NOT Bearer/Basic/X-Api-Key.

GitLab's own docs (docs.gitlab.com/api/rest/authentication/) are explicit:
a Personal/Project/Group Access Token authenticates via the `PRIVATE-TOKEN`
request header -- a different scheme from n8n's `X-N8N-API-KEY` or
MuleSoft's OAuth2 bearer, so it is built exactly as documented rather than
assumed to be a generic Bearer token.

WHY `write_mode="both"`, SAME REASONING AS EVERY OTHER BYOK CONNECTOR IN
THIS PORTFOLIO (n8n/Make.com/MuleSoft/UiPath/Automation Anywhere/Blue
Prism).

Declaring `write_mode="user"` would mean only the platform's generic
Secrets screen could write these -- leaving a first-time user with no
in-app screen explaining what a GitLab Personal Access Token even is or
which scopes it needs. `"both"` keeps the generic Secrets screen as a
fallback while letting `connect_gitlab` validate the token against the
user's own instance *before* saving it.

WHY THIS CONNECTOR IS SCOPED TO CI/CD ONLY, NOT THE WHOLE GITLAB API.

GitLab's REST API surface also covers repository files/commits/branches,
merge requests, issues, wikis, and project/group administration -- a
materially different product surface (source control + project
management) from CI/CD (pipelines/jobs/runners/variables/schedules/
environments/deployments). Per CONNECTOR_DISCOVERY.md, this app covers the
CI/CD domain in full depth; a repository/MR/issue-focused GitLab connector
is a deliberate separate future app, not a silent gap here.
"""

from imperal_sdk import Extension, ChatExtension

ext = Extension(
    "gitlab-cicd-connector",
    version="0.1.0",
    display_name="GitLab CI/CD",
    description=(
        "Connect your own GitLab account (gitlab.com or self-managed) to see and "
        "manage CI/CD from Imperal -- pipelines (list/get/create/retry/cancel/delete), "
        "jobs (list/get/retry/cancel/play/erase/logs), runners (list/get/pause/resume/"
        "tag/delete), project and group CI/CD variables, pipeline trigger tokens, "
        "pipeline schedules (including cron variables), CI Lint validation, job "
        "artifacts (keep/delete), environments, and deployments (including approvals). "
        "Your Personal Access Token is verified against your own instance before it's "
        "saved. Scoped to CI/CD only -- repository files, merge requests, issues and "
        "project administration are out of scope."
    ),
    icon="icon.svg",
    actions_explicit=True,
    capabilities=["gitlab:read", "gitlab:write"],
)

chat = ChatExtension(
    ext,
    tool_name="gitlab-cicd-connector",
    description="View and manage GitLab CI/CD -- pipelines, jobs, runners, variables, schedules, environments",
)

ext.secret(
    "gitlab_connections",
    (
        "Your connected GitLab instances -- stored as a JSON array, one "
        "entry per instance, each with its own base_url, Personal Access "
        "Token, and an optional friendly label. Managed through "
        "connect_gitlab / disconnect_gitlab -- you should not need to edit "
        "this directly."
    ),
    required=True,
    write_mode="both",
    max_bytes=65536,
    rotation_hint_days=180,
)(lambda: None)


@ext.health_check
async def health_check(ctx) -> dict:
    """Fast configuration health; no third-party call -- just confirms at
    least one instance connection is stored, same shape as MuleSoft
    Connector's / CircleCI Connector's health_check."""
    import json as _json
    raw = await ctx.secrets.get("gitlab_connections")
    try:
        count = len(_json.loads(raw)) if raw else 0
    except Exception:
        count = 0
    return {
        "healthy": True,
        "detail": (
            f"{count} GitLab instance(s) connected." if count
            else "Not connected yet -- run connect_gitlab."
        ),
    }
