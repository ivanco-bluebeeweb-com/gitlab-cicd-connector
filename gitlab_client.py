"""GitLab REST API client -- PRIVATE-TOKEN auth against a user-supplied
base_url (gitlab.com or self-managed), async wrappers (await ctx.http.*,
same contract as n8n_client.py / mulesoft_client.py) around the CI/CD
domain: pipelines, jobs, runners, variables, triggers, schedules, lint,
artifacts, environments, deployments.

WHY NO HOST DISCOVERY, SAME REASONING AS n8n_client.py.

GitLab has no finite set of hosts to probe -- self-managed instances live
at whatever host the user deployed to. Per docs.gitlab.com/api/rest/,
every request goes to `<base_url>/api/v4/...` where base_url is supplied
directly by the user (defaulting to https://gitlab.com for the common
SaaS case).

WHY `PRIVATE-TOKEN: <token>` HEADER, NOT Bearer/Basic.

GitLab's own docs (docs.gitlab.com/api/rest/authentication/) are explicit
about this header name for Personal/Project/Group Access Tokens -- a
different scheme from n8n's `X-N8N-API-KEY` or MuleSoft's OAuth2 bearer.

WHY 401 vs 403 ARE HANDLED DIFFERENTLY, SAME PRINCIPLE AS n8n_client.py /
mulesoft_client.py.

A 401 means this base_url/token pair is not recognised at all (wrong URL,
wrong/expired token, or instance unreachable under that path). A 403
means the token IS recognised, but lacks the scope/role for the specific
operation (GitLab PATs carry explicit scopes like `api`/`read_api`, and
some operations additionally require a Maintainer/Owner project role) --
a materially different, more specific and more fixable cause that must
not be reported as "wrong token".
"""
from __future__ import annotations

import ipaddress
import urllib.parse
from urllib.parse import urlparse

API_VERSION = "v4"


class ProviderError(Exception):
    """Raised for any GitLab API call that fails, carrying a status_code
    and a human-readable detail so handlers can distinguish 401 (bad
    token) from 403 (token ok, insufficient scope/role) from 404 (not
    found) from anything else."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"GitLab API error {status_code}: {detail}")


def _normalize_base_url(base_url: str) -> str:
    return (base_url or "").rstrip("/")


def normalize_base_url(value: str, allow_private_http: bool = False) -> str:
    """Validate a user-supplied base_url before it is ever used in a request
    (AUTH_AND_CREDENTIALS_STANDARD.md Part C / task #2368). Same shape as
    Home Assistant Connector's home_assistant_client.normalize_base_url --
    requires HTTPS by default (gitlab.com and almost every self-managed
    instance use it); HTTP is accepted only when the caller explicitly opts
    in AND the host resolves to localhost or a private/loopback address, so
    a self-managed GitLab on a private network still works while a bare
    unchecked base_url can't be pointed at an arbitrary internal host."""
    raw = (value or "").strip().rstrip("/")
    parsed = urlparse(raw)
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProviderError(400, "GitLab base URL must contain only a scheme, host and optional port/path.")
    if parsed.scheme == "https":
        return raw
    if parsed.scheme != "http" or not allow_private_http:
        raise ProviderError(400, "Use HTTPS, or explicitly allow HTTP for a private-network GitLab instance.")
    host = parsed.hostname.lower()
    if host == "localhost":
        return raw
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        raise ProviderError(400, "HTTP is allowed only for localhost or a literal private IP address.")
    if not (address.is_private or address.is_loopback):
        raise ProviderError(400, "HTTP is allowed only for a private-network or localhost address.")
    return raw


def _encode_project_id(project_id) -> str:
    """GitLab accepts either a numeric project ID or a URL-encoded
    namespaced path (e.g. 'group/subgroup/project'). Namespaced paths
    must be percent-encoded per docs.gitlab.com/api/rest/#namespaced-
    paths -- numeric IDs pass through untouched."""
    project_id = str(project_id or "")
    if project_id.isdigit():
        return project_id
    return urllib.parse.quote(project_id, safe="")


def _headers(token: str) -> dict:
    return {"PRIVATE-TOKEN": token, "Accept": "application/json"}


def _api(base_url: str, path: str) -> str:
    return f"{_normalize_base_url(base_url)}/api/{API_VERSION}{path}"


def _error_detail(resp) -> str:
    try:
        body = resp.json() if resp.text else {}
    except Exception:
        body = {}
    if isinstance(body, dict):
        return body.get("message") or body.get("error") or ""
    return ""


def _check_status(resp, action: str):
    if resp.status_code == 401:
        raise ProviderError(
            401,
            f"GitLab rejected the request to {action}: the base URL or "
            "Personal Access Token isn't recognised. Check the base URL "
            "has no typo and the token hasn't expired or been revoked.",
        )
    if resp.status_code == 403:
        detail = _error_detail(resp)
        raise ProviderError(
            403,
            f"GitLab recognised your token for {action}, but it's missing "
            "the required scope or your role on this project/group is too "
            "low." + (f" ({detail})" if detail else ""),
        )
    if resp.status_code == 404:
        raise ProviderError(404, f"Not found while trying to {action}.")
    if resp.status_code == 429:
        raise ProviderError(429, f"GitLab rate-limited the request to {action}. Try again shortly.")
    if resp.status_code >= 500:
        raise ProviderError(resp.status_code, f"GitLab's own server had a problem while trying to {action}.")
    if resp.status_code not in (200, 201, 202, 204):
        detail = _error_detail(resp)
        raise ProviderError(
            resp.status_code,
            f"Unexpected response while trying to {action} (HTTP {resp.status_code})."
            + (f" {detail}" if detail else ""),
        )
    if not resp.text:
        return {}
    try:
        return resp.json()
    except Exception:
        return {}


async def check_connection(ctx, base_url: str, token: str) -> dict:
    resp = await ctx.http.get(_api(base_url, "/user"), headers=_headers(token))
    return _check_status(resp, "verify connection")


# ──────────────────────────────────────────────────────────────────────────
# Pipelines
# ──────────────────────────────────────────────────────────────────────────

async def list_pipelines(ctx, base_url: str, token: str, project_id, **filters):
    params = {k: v for k, v in filters.items() if v is not None and v != ""}
    resp = await ctx.http.get(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/pipelines"),
        headers=_headers(token), params=params,
    )
    return _check_status(resp, "list pipelines")


async def get_pipeline(ctx, base_url: str, token: str, project_id, pipeline_id):
    resp = await ctx.http.get(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/pipelines/{pipeline_id}"),
        headers=_headers(token),
    )
    return _check_status(resp, "get pipeline")


async def get_pipeline_variables(ctx, base_url: str, token: str, project_id, pipeline_id):
    resp = await ctx.http.get(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/pipelines/{pipeline_id}/variables"),
        headers=_headers(token),
    )
    return _check_status(resp, "get pipeline variables")


async def get_pipeline_test_report(ctx, base_url: str, token: str, project_id, pipeline_id):
    resp = await ctx.http.get(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/pipelines/{pipeline_id}/test_report"),
        headers=_headers(token),
    )
    return _check_status(resp, "get pipeline test report")


async def create_pipeline(ctx, base_url: str, token: str, project_id, ref: str, variables=None):
    body = {"ref": ref}
    if variables:
        body["variables"] = variables
    resp = await ctx.http.post(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/pipeline"),
        headers=_headers(token), json=body,
    )
    return _check_status(resp, "create pipeline")


async def retry_pipeline(ctx, base_url: str, token: str, project_id, pipeline_id):
    resp = await ctx.http.post(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/pipelines/{pipeline_id}/retry"),
        headers=_headers(token), json={},
    )
    return _check_status(resp, "retry pipeline")


async def cancel_pipeline(ctx, base_url: str, token: str, project_id, pipeline_id):
    resp = await ctx.http.post(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/pipelines/{pipeline_id}/cancel"),
        headers=_headers(token), json={},
    )
    return _check_status(resp, "cancel pipeline")


async def delete_pipeline(ctx, base_url: str, token: str, project_id, pipeline_id):
    resp = await ctx.http.delete(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/pipelines/{pipeline_id}"),
        headers=_headers(token),
    )
    _check_status(resp, "delete pipeline")
    return {"deleted": True, "id": str(pipeline_id)}


# ──────────────────────────────────────────────────────────────────────────
# Jobs
# ──────────────────────────────────────────────────────────────────────────

async def list_project_jobs(ctx, base_url: str, token: str, project_id, **filters):
    params = {k: v for k, v in filters.items() if v is not None and v != ""}
    resp = await ctx.http.get(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/jobs"),
        headers=_headers(token), params=params,
    )
    return _check_status(resp, "list project jobs")


async def list_pipeline_jobs(ctx, base_url: str, token: str, project_id, pipeline_id, **filters):
    params = {k: v for k, v in filters.items() if v is not None and v != ""}
    resp = await ctx.http.get(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/pipelines/{pipeline_id}/jobs"),
        headers=_headers(token), params=params,
    )
    return _check_status(resp, "list pipeline jobs")


async def list_pipeline_bridges(ctx, base_url: str, token: str, project_id, pipeline_id, **filters):
    params = {k: v for k, v in filters.items() if v is not None and v != ""}
    resp = await ctx.http.get(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/pipelines/{pipeline_id}/bridges"),
        headers=_headers(token), params=params,
    )
    return _check_status(resp, "list pipeline bridges")


async def get_job(ctx, base_url: str, token: str, project_id, job_id):
    resp = await ctx.http.get(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/jobs/{job_id}"),
        headers=_headers(token),
    )
    return _check_status(resp, "get job")


async def get_job_trace(ctx, base_url: str, token: str, project_id, job_id) -> str:
    """Returns the raw text log, not JSON -- GitLab serves this endpoint
    as text/plain."""
    resp = await ctx.http.get(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/jobs/{job_id}/trace"),
        headers=_headers(token),
    )
    if resp.status_code == 401:
        raise ProviderError(401, "GitLab rejected the request to get job trace: token not recognised.")
    if resp.status_code == 403:
        raise ProviderError(403, "GitLab recognised your token, but it lacks access to this job's trace.")
    if resp.status_code == 404:
        raise ProviderError(404, "Job trace not found (job may not have started yet, or was erased).")
    if resp.status_code not in (200, 201, 202, 204):
        raise ProviderError(resp.status_code, f"Unexpected response getting job trace (HTTP {resp.status_code}).")
    return resp.text or ""


async def retry_job(ctx, base_url: str, token: str, project_id, job_id):
    resp = await ctx.http.post(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/jobs/{job_id}/retry"),
        headers=_headers(token), json={},
    )
    return _check_status(resp, "retry job")


async def cancel_job(ctx, base_url: str, token: str, project_id, job_id):
    resp = await ctx.http.post(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/jobs/{job_id}/cancel"),
        headers=_headers(token), json={},
    )
    return _check_status(resp, "cancel job")


async def play_job(ctx, base_url: str, token: str, project_id, job_id):
    resp = await ctx.http.post(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/jobs/{job_id}/play"),
        headers=_headers(token), json={},
    )
    return _check_status(resp, "play job")


async def erase_job(ctx, base_url: str, token: str, project_id, job_id):
    resp = await ctx.http.post(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/jobs/{job_id}/erase"),
        headers=_headers(token), json={},
    )
    return _check_status(resp, "erase job")


# ──────────────────────────────────────────────────────────────────────────
# Job Artifacts
# ──────────────────────────────────────────────────────────────────────────

def download_job_artifacts_url(base_url: str, project_id, job_id) -> str:
    """GitLab does not proxy the binary artifact archive through JSON --
    return the direct download URL; the caller authenticates the same way
    (their own browser session or PRIVATE-TOKEN header)."""
    return _api(base_url, f"/projects/{_encode_project_id(project_id)}/jobs/{job_id}/artifacts")


async def keep_job_artifacts(ctx, base_url: str, token: str, project_id, job_id):
    resp = await ctx.http.post(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/jobs/{job_id}/artifacts/keep"),
        headers=_headers(token), json={},
    )
    return _check_status(resp, "keep job artifacts")


async def delete_job_artifacts(ctx, base_url: str, token: str, project_id, job_id):
    resp = await ctx.http.delete(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/jobs/{job_id}/artifacts"),
        headers=_headers(token),
    )
    _check_status(resp, "delete job artifacts")
    return {"deleted": True, "id": str(job_id)}


# ──────────────────────────────────────────────────────────────────────────
# Runners
# ──────────────────────────────────────────────────────────────────────────

async def list_runners(ctx, base_url: str, token: str, all_runners: bool = False, **filters):
    params = {k: v for k, v in filters.items() if v is not None and v != ""}
    path = "/runners/all" if all_runners else "/runners"
    resp = await ctx.http.get(_api(base_url, path), headers=_headers(token), params=params)
    return _check_status(resp, "list runners")


async def get_runner(ctx, base_url: str, token: str, runner_id):
    resp = await ctx.http.get(_api(base_url, f"/runners/{runner_id}"), headers=_headers(token))
    return _check_status(resp, "get runner")


async def update_runner(ctx, base_url: str, token: str, runner_id, **fields):
    body = {k: v for k, v in fields.items() if v is not None}
    resp = await ctx.http.put(_api(base_url, f"/runners/{runner_id}"), headers=_headers(token), json=body)
    return _check_status(resp, "update runner")


async def delete_runner(ctx, base_url: str, token: str, runner_id):
    resp = await ctx.http.delete(_api(base_url, f"/runners/{runner_id}"), headers=_headers(token))
    _check_status(resp, "delete runner")
    return {"deleted": True, "id": str(runner_id)}


async def list_runner_jobs(ctx, base_url: str, token: str, runner_id, **filters):
    params = {k: v for k, v in filters.items() if v is not None and v != ""}
    resp = await ctx.http.get(
        _api(base_url, f"/runners/{runner_id}/jobs"), headers=_headers(token), params=params,
    )
    return _check_status(resp, "list runner jobs")


async def list_project_runners(ctx, base_url: str, token: str, project_id, **filters):
    params = {k: v for k, v in filters.items() if v is not None and v != ""}
    resp = await ctx.http.get(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/runners"),
        headers=_headers(token), params=params,
    )
    return _check_status(resp, "list project runners")


async def enable_project_runner(ctx, base_url: str, token: str, project_id, runner_id):
    resp = await ctx.http.post(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/runners"),
        headers=_headers(token), json={"runner_id": runner_id},
    )
    return _check_status(resp, "enable project runner")


async def disable_project_runner(ctx, base_url: str, token: str, project_id, runner_id):
    resp = await ctx.http.delete(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/runners/{runner_id}"),
        headers=_headers(token),
    )
    _check_status(resp, "disable project runner")
    return {"deleted": True, "id": str(runner_id)}


# ──────────────────────────────────────────────────────────────────────────
# CI/CD Variables -- project level
# ──────────────────────────────────────────────────────────────────────────

async def list_project_variables(ctx, base_url: str, token: str, project_id, **filters):
    params = {k: v for k, v in filters.items() if v is not None and v != ""}
    resp = await ctx.http.get(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/variables"),
        headers=_headers(token), params=params,
    )
    return _check_status(resp, "list project variables")


async def get_project_variable(ctx, base_url: str, token: str, project_id, key: str, **filters):
    params = {k: v for k, v in filters.items() if v is not None and v != ""}
    resp = await ctx.http.get(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/variables/{key}"),
        headers=_headers(token), params=params,
    )
    return _check_status(resp, "get project variable")


async def create_project_variable(ctx, base_url: str, token: str, project_id, key: str, value: str, **fields):
    body = {"key": key, "value": value, **{k: v for k, v in fields.items() if v is not None}}
    resp = await ctx.http.post(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/variables"),
        headers=_headers(token), json=body,
    )
    return _check_status(resp, "create project variable")


async def update_project_variable(ctx, base_url: str, token: str, project_id, key: str, **fields):
    body = {k: v for k, v in fields.items() if v is not None}
    resp = await ctx.http.put(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/variables/{key}"),
        headers=_headers(token), json=body,
    )
    return _check_status(resp, "update project variable")


async def delete_project_variable(ctx, base_url: str, token: str, project_id, key: str, **filters):
    params = {k: v for k, v in filters.items() if v is not None and v != ""}
    resp = await ctx.http.delete(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/variables/{key}"),
        headers=_headers(token), params=params,
    )
    _check_status(resp, "delete project variable")
    return {"deleted": True, "id": key}


# ──────────────────────────────────────────────────────────────────────────
# CI/CD Variables -- group level
# ──────────────────────────────────────────────────────────────────────────

async def list_group_variables(ctx, base_url: str, token: str, group_id, **filters):
    params = {k: v for k, v in filters.items() if v is not None and v != ""}
    resp = await ctx.http.get(
        _api(base_url, f"/groups/{_encode_project_id(group_id)}/variables"),
        headers=_headers(token), params=params,
    )
    return _check_status(resp, "list group variables")


async def get_group_variable(ctx, base_url: str, token: str, group_id, key: str):
    resp = await ctx.http.get(
        _api(base_url, f"/groups/{_encode_project_id(group_id)}/variables/{key}"),
        headers=_headers(token),
    )
    return _check_status(resp, "get group variable")


async def create_group_variable(ctx, base_url: str, token: str, group_id, key: str, value: str, **fields):
    body = {"key": key, "value": value, **{k: v for k, v in fields.items() if v is not None}}
    resp = await ctx.http.post(
        _api(base_url, f"/groups/{_encode_project_id(group_id)}/variables"),
        headers=_headers(token), json=body,
    )
    return _check_status(resp, "create group variable")


async def update_group_variable(ctx, base_url: str, token: str, group_id, key: str, **fields):
    body = {k: v for k, v in fields.items() if v is not None}
    resp = await ctx.http.put(
        _api(base_url, f"/groups/{_encode_project_id(group_id)}/variables/{key}"),
        headers=_headers(token), json=body,
    )
    return _check_status(resp, "update group variable")


async def delete_group_variable(ctx, base_url: str, token: str, group_id, key: str):
    resp = await ctx.http.delete(
        _api(base_url, f"/groups/{_encode_project_id(group_id)}/variables/{key}"),
        headers=_headers(token),
    )
    _check_status(resp, "delete group variable")
    return {"deleted": True, "id": key}


# ──────────────────────────────────────────────────────────────────────────
# Pipeline Trigger Tokens
# ──────────────────────────────────────────────────────────────────────────

async def list_triggers(ctx, base_url: str, token: str, project_id):
    resp = await ctx.http.get(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/triggers"),
        headers=_headers(token),
    )
    return _check_status(resp, "list triggers")


async def create_trigger(ctx, base_url: str, token: str, project_id, description: str):
    resp = await ctx.http.post(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/triggers"),
        headers=_headers(token), json={"description": description},
    )
    return _check_status(resp, "create trigger")


async def update_trigger(ctx, base_url: str, token: str, project_id, trigger_id, description: str):
    resp = await ctx.http.put(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/triggers/{trigger_id}"),
        headers=_headers(token), json={"description": description},
    )
    return _check_status(resp, "update trigger")


async def delete_trigger(ctx, base_url: str, token: str, project_id, trigger_id):
    resp = await ctx.http.delete(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/triggers/{trigger_id}"),
        headers=_headers(token),
    )
    _check_status(resp, "delete trigger")
    return {"deleted": True, "id": str(trigger_id)}


async def run_pipeline_trigger(ctx, base_url: str, project_id, trigger_token: str, ref: str, variables=None):
    """Auth here is the trigger_token itself (as a form field), NOT the
    caller's Personal Access Token -- this is GitLab's documented
    external-CI trigger mechanism, meant to run without a full PAT."""
    body = {"token": trigger_token, "ref": ref}
    if variables:
        for k, v in variables.items():
            body[f"variables[{k}]"] = v
    resp = await ctx.http.post(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/trigger/pipeline"),
        data=body,
    )
    return _check_status(resp, "run pipeline trigger")


# ──────────────────────────────────────────────────────────────────────────
# Pipeline Schedules
# ──────────────────────────────────────────────────────────────────────────

async def list_pipeline_schedules(ctx, base_url: str, token: str, project_id, **filters):
    params = {k: v for k, v in filters.items() if v is not None and v != ""}
    resp = await ctx.http.get(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/pipeline_schedules"),
        headers=_headers(token), params=params,
    )
    return _check_status(resp, "list pipeline schedules")


async def get_pipeline_schedule(ctx, base_url: str, token: str, project_id, schedule_id):
    resp = await ctx.http.get(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/pipeline_schedules/{schedule_id}"),
        headers=_headers(token),
    )
    return _check_status(resp, "get pipeline schedule")


async def create_pipeline_schedule(ctx, base_url: str, token: str, project_id, description: str, ref: str, cron: str, **fields):
    body = {"description": description, "ref": ref, "cron": cron,
            **{k: v for k, v in fields.items() if v is not None}}
    resp = await ctx.http.post(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/pipeline_schedules"),
        headers=_headers(token), json=body,
    )
    return _check_status(resp, "create pipeline schedule")


async def update_pipeline_schedule(ctx, base_url: str, token: str, project_id, schedule_id, **fields):
    body = {k: v for k, v in fields.items() if v is not None}
    resp = await ctx.http.put(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/pipeline_schedules/{schedule_id}"),
        headers=_headers(token), json=body,
    )
    return _check_status(resp, "update pipeline schedule")


async def delete_pipeline_schedule(ctx, base_url: str, token: str, project_id, schedule_id):
    resp = await ctx.http.delete(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/pipeline_schedules/{schedule_id}"),
        headers=_headers(token),
    )
    _check_status(resp, "delete pipeline schedule")
    return {"deleted": True, "id": str(schedule_id)}


async def run_pipeline_schedule(ctx, base_url: str, token: str, project_id, schedule_id):
    resp = await ctx.http.post(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/pipeline_schedules/{schedule_id}/play"),
        headers=_headers(token), json={},
    )
    return _check_status(resp, "run pipeline schedule")


async def create_schedule_variable(ctx, base_url: str, token: str, project_id, schedule_id, key, value, variable_type="env_var"):
    resp = await ctx.http.post(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/pipeline_schedules/{schedule_id}/variables"),
        headers=_headers(token), json={"key": key, "value": value, "variable_type": variable_type},
    )
    return _check_status(resp, "create schedule variable")


async def update_schedule_variable(ctx, base_url: str, token: str, project_id, schedule_id, key, **fields):
    body = {k: v for k, v in fields.items() if v is not None}
    resp = await ctx.http.put(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/pipeline_schedules/{schedule_id}/variables/{key}"),
        headers=_headers(token), json=body,
    )
    return _check_status(resp, "update schedule variable")


async def set_schedule_variable(ctx, base_url: str, token: str, project_id, schedule_id, key, value, variable_type="env_var"):
    """GitLab's pipeline-schedule-variables API has no single upsert
    endpoint -- only separate POST (create) and PUT (update by key).
    This wrapper tries create first, and falls back to update if the key
    already exists (GitLab returns 400 'key has already been taken')."""
    try:
        return await create_schedule_variable(ctx, base_url, token, project_id, schedule_id, key, value, variable_type)
    except ProviderError as e:
        if e.status_code == 400:
            return await update_schedule_variable(ctx, base_url, token, project_id, schedule_id, key,
                                                    value=value, variable_type=variable_type)
        raise


async def delete_schedule_variable(ctx, base_url: str, token: str, project_id, schedule_id, key):
    resp = await ctx.http.delete(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/pipeline_schedules/{schedule_id}/variables/{key}"),
        headers=_headers(token),
    )
    _check_status(resp, "delete schedule variable")
    return {"deleted": True, "id": key}


# ──────────────────────────────────────────────────────────────────────────
# CI Lint
# ──────────────────────────────────────────────────────────────────────────

async def lint_ci_yaml(ctx, base_url: str, token: str, content: str, include_merged_yaml: bool = False, include_jobs: bool = False):
    body = {"content": content, "include_merged_yaml": include_merged_yaml, "include_jobs": include_jobs}
    resp = await ctx.http.post(_api(base_url, "/ci/lint"), headers=_headers(token), json=body)
    return _check_status(resp, "lint CI YAML")


async def project_lint_ci_yaml(ctx, base_url: str, token: str, project_id, content: str | None = None,
                                dry_run: bool = False, ref: str | None = None):
    body = {"dry_run": dry_run}
    if content:
        body["content"] = content
    if ref:
        body["ref"] = ref
    resp = await ctx.http.post(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/ci/lint"),
        headers=_headers(token), json=body,
    )
    return _check_status(resp, "lint project CI YAML")


# ──────────────────────────────────────────────────────────────────────────
# Environments
# ──────────────────────────────────────────────────────────────────────────

async def list_environments(ctx, base_url: str, token: str, project_id, **filters):
    params = {k: v for k, v in filters.items() if v is not None and v != ""}
    resp = await ctx.http.get(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/environments"),
        headers=_headers(token), params=params,
    )
    return _check_status(resp, "list environments")


async def get_environment(ctx, base_url: str, token: str, project_id, environment_id):
    resp = await ctx.http.get(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/environments/{environment_id}"),
        headers=_headers(token),
    )
    return _check_status(resp, "get environment")


async def create_environment(ctx, base_url: str, token: str, project_id, name: str, **fields):
    body = {"name": name, **{k: v for k, v in fields.items() if v is not None}}
    resp = await ctx.http.post(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/environments"),
        headers=_headers(token), json=body,
    )
    return _check_status(resp, "create environment")


async def update_environment(ctx, base_url: str, token: str, project_id, environment_id, **fields):
    body = {k: v for k, v in fields.items() if v is not None}
    resp = await ctx.http.put(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/environments/{environment_id}"),
        headers=_headers(token), json=body,
    )
    return _check_status(resp, "update environment")


async def delete_environment(ctx, base_url: str, token: str, project_id, environment_id):
    resp = await ctx.http.delete(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/environments/{environment_id}"),
        headers=_headers(token),
    )
    _check_status(resp, "delete environment")
    return {"deleted": True, "id": str(environment_id)}


async def stop_environment(ctx, base_url: str, token: str, project_id, environment_id):
    resp = await ctx.http.post(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/environments/{environment_id}/stop"),
        headers=_headers(token), json={},
    )
    return _check_status(resp, "stop environment")


# ──────────────────────────────────────────────────────────────────────────
# Deployments
# ──────────────────────────────────────────────────────────────────────────

async def list_deployments(ctx, base_url: str, token: str, project_id, **filters):
    params = {k: v for k, v in filters.items() if v is not None and v != ""}
    resp = await ctx.http.get(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/deployments"),
        headers=_headers(token), params=params,
    )
    return _check_status(resp, "list deployments")


async def get_deployment(ctx, base_url: str, token: str, project_id, deployment_id):
    resp = await ctx.http.get(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/deployments/{deployment_id}"),
        headers=_headers(token),
    )
    return _check_status(resp, "get deployment")


async def approve_deployment(ctx, base_url: str, token: str, project_id, deployment_id, status: str, comment: str | None = None):
    """status must be 'approved' or 'rejected' -- GitLab's own deployment
    approval-rules mechanism."""
    body = {"status": status}
    if comment:
        body["comment"] = comment
    resp = await ctx.http.post(
        _api(base_url, f"/projects/{_encode_project_id(project_id)}/deployments/{deployment_id}/approval"),
        headers=_headers(token), json=body,
    )
    return _check_status(resp, "approve/reject deployment")


# ──────────────────────────────────────────────────────────────────────────
# Bulk operations + Project CI Audit (Tier 3 value-add)
# ──────────────────────────────────────────────────────────────────────────

async def bulk_pipeline_action(ctx, base_url: str, token: str, project_id, pipeline_ids: list, action: str):
    """action is 'retry' or 'cancel'. Continues past per-item failures,
    same convention as MuleSoft Connector's bulk_* helpers."""
    fn = retry_pipeline if action == "retry" else cancel_pipeline
    results, succeeded, failed = [], 0, 0
    for pid in pipeline_ids:
        try:
            p = await fn(ctx, base_url, token, project_id, pid)
            results.append({"pipeline_id": pid, "ok": True, "status": p.get("status", "")})
            succeeded += 1
        except ProviderError as e:
            results.append({"pipeline_id": pid, "ok": False, "status": "", "error": e.detail})
            failed += 1
    return {"results": results, "succeeded": succeeded, "failed": failed}


async def bulk_job_action(ctx, base_url: str, token: str, project_id, job_ids: list, action: str):
    """action is 'retry' or 'cancel'. Continues past per-item failures."""
    fn = retry_job if action == "retry" else cancel_job
    results, succeeded, failed = [], 0, 0
    for jid in job_ids:
        try:
            j = await fn(ctx, base_url, token, project_id, jid)
            results.append({"job_id": jid, "ok": True, "status": j.get("status", "")})
            succeeded += 1
        except ProviderError as e:
            results.append({"job_id": jid, "ok": False, "status": "", "error": e.detail})
            failed += 1
    return {"results": results, "succeeded": succeeded, "failed": failed}


async def audit_project_ci(ctx, base_url: str, token: str, project_id, recent_pipelines: int = 20):
    """One-glance health snapshot as a set of named check rows -- pipeline
    success rate, failing-pipeline count, runner availability, and a
    stale/undocumented-variables flag -- same value-add shape as
    MuleSoft's audit_cloudhub_environment."""
    import datetime as _dt

    pipelines_resp = await list_pipelines(ctx, base_url, token, project_id,
                                           per_page=recent_pipelines, order_by="id", sort="desc")
    pipelines = pipelines_resp if isinstance(pipelines_resp, list) else []
    runners_resp = await list_project_runners(ctx, base_url, token, project_id)
    runners = runners_resp if isinstance(runners_resp, list) else []
    try:
        variables_resp = await list_project_variables(ctx, base_url, token, project_id, per_page=100)
        variables = variables_resp if isinstance(variables_resp, list) else []
    except ProviderError:
        variables = []

    total = len(pipelines)
    succeeded = sum(1 for p in pipelines if p.get("status") == "success")
    failing = sum(1 for p in pipelines if p.get("status") in ("failed", "canceled"))
    success_rate = round((succeeded / total) * 100, 1) if total else 0.0
    offline_runners = sum(1 for r in runners if not (r.get("online") or r.get("status") == "online"))
    undocumented_vars = [v for v in variables if not (v.get("description") or "").strip()]
    stale_flagged = bool(undocumented_vars)

    rows = [
        {
            "check": "Pipeline success rate",
            "status": "ok" if success_rate >= 90 else ("warn" if success_rate >= 60 else "fail"),
            "detail": f"{succeeded}/{total} of the last {total} sampled pipelines succeeded ({success_rate}%).",
        },
        {
            "check": "Failing pipelines",
            "status": "ok" if failing == 0 else ("warn" if failing < total / 2 else "fail"),
            "detail": f"{failing} of {total} sampled pipelines failed or were cancelled.",
        },
        {
            "check": "Runner availability",
            "status": "ok" if offline_runners == 0 else ("warn" if offline_runners < len(runners) else "fail"),
            "detail": f"{offline_runners} of {len(runners)} project runners are offline.",
        },
        {
            "check": "CI/CD variable documentation",
            "status": "ok" if not stale_flagged else "warn",
            "detail": (
                f"{len(undocumented_vars)} of {len(variables)} project variables have no description."
                if variables else "No project-level CI/CD variables found."
            ),
        },
    ]

    return {
        "project_id": str(project_id),
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "rows": rows,
        "success_rate_pct": success_rate,
        "failing_pipelines": failing,
        "stale_variables_flagged": stale_flagged,
        "offline_runners": offline_runners,
    }


async def get_failed_jobs_summary(ctx, base_url: str, token: str, project_id, recent_pipelines: int = 10):
    """Value-add report: scan the most recent pipelines' failed jobs so
    recurring flaky/broken jobs stand out instead of scrolling through
    every pipeline individually."""
    pipelines_resp = await list_pipelines(ctx, base_url, token, project_id,
                                           per_page=recent_pipelines, order_by="id", sort="desc")
    pipelines = pipelines_resp if isinstance(pipelines_resp, list) else []

    rows = []
    for p in pipelines:
        pid = p.get("id")
        try:
            jobs_resp = await list_pipeline_jobs(ctx, base_url, token, project_id, pid, scope="failed")
        except ProviderError:
            continue
        jobs = jobs_resp if isinstance(jobs_resp, list) else []
        for j in jobs:
            rows.append({
                "pipeline_id": pid,
                "job_id": j.get("id", 0),
                "job_name": j.get("name", ""),
                "stage": j.get("stage", ""),
                "failure_reason": j.get("failure_reason") or "unknown",
                "web_url": j.get("web_url", ""),
            })

    return {"rows": rows, "total_failed": len(rows)}
