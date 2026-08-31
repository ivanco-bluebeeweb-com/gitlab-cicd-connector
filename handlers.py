"""Chat functions for GitLab CI/CD Connector: connection management,
pipelines, jobs, runners, CI/CD variables (project + group), pipeline
trigger tokens, pipeline schedules, CI Lint, job artifacts, environments,
deployments, and bulk operations + project audit (Tier 3 value-add).
Built on gitlab_client.py / schemas.py, following the same shape as
MuleSoft Connector's / n8n Connector's handlers.py.
"""
from __future__ import annotations

import json
import uuid

from imperal_sdk import ActionResult

import gitlab_client as gc
from app import ext, chat
from schemas import (
    NoParams,
    ConnectGitlabParams, ProviderConnection, ProviderConnectionList,
    DisconnectGitlabParams, DeleteResult,
    ListPipelinesParams, Pipeline, PipelineList,
    GetPipelineParams, PipelineDetail,
    GetPipelineVariablesParams, PipelineVariable, PipelineVariableList,
    CreatePipelineParams, RetryPipelineParams, CancelPipelineParams,
    DeletePipelineParams, PipelineActionResult,
    GetPipelineTestReportParams, TestSuiteSummary, PipelineTestReport,
    ListProjectJobsParams, ListPipelineJobsParams, Job, JobList,
    ListPipelineBridgesParams, PipelineBridge, PipelineBridgeList,
    GetJobParams, GetJobTraceParams, JobTrace,
    JobActionParams, JobActionResult,
    GetJobArtifactsParams, ArtifactsInfo,
    KeepJobArtifactsParams, DeleteJobArtifactsParams,
    ListRunnersParams, Runner, RunnerList,
    GetRunnerParams, RunnerDetail,
    UpdateRunnerParams, DeleteRunnerParams, ListRunnerJobsParams,
    ListProjectRunnersParams, EnableProjectRunnerParams, DisableProjectRunnerParams,
    ListProjectVariablesParams, Variable, VariableList,
    GetProjectVariableParams, CreateProjectVariableParams,
    UpdateProjectVariableParams, DeleteProjectVariableParams,
    ListGroupVariablesParams, GetGroupVariableParams, CreateGroupVariableParams,
    UpdateGroupVariableParams, DeleteGroupVariableParams,
    ListTriggersParams, Trigger, TriggerList,
    CreateTriggerParams, UpdateTriggerParams, DeleteTriggerParams,
    RunPipelineTriggerParams,
    ListPipelineSchedulesParams, PipelineSchedule, PipelineScheduleList,
    GetPipelineScheduleParams, CreatePipelineScheduleParams,
    UpdatePipelineScheduleParams, DeletePipelineScheduleParams,
    RunPipelineScheduleParams,
    ScheduleVariableParams, DeleteScheduleVariableParams,
    LintCiYamlParams, ProjectLintCiYamlParams, LintResult,
    ListEnvironmentsParams, Environment, EnvironmentList,
    GetEnvironmentParams, CreateEnvironmentParams,
    UpdateEnvironmentParams, DeleteEnvironmentParams, StopEnvironmentParams,
    EnvironmentActionResult,
    ListDeploymentsParams, Deployment, DeploymentList,
    GetDeploymentParams, ApproveDeploymentParams,
    BulkPipelineIdsParams, BulkResultItem, BulkResult,
    BulkJobIdsParams, BulkJobResultItem, BulkJobResult,
    AuditProjectCiParams, AuditReport, AuditRow,
    GetFailedJobsSummaryParams, FailedJobsSummary, FailedJobSummaryRow,
)

_SECRET_NAME = "gitlab_connections"


# ──────────────────────────────────────────────────────────────────────────
# Connection storage helpers -- one secret holding a JSON array of
# connection records, same precedent as MuleSoft Connector / n8n Connector
# / CircleCI Connector (ctx.secrets has no "one secret per id" primitive).
# ──────────────────────────────────────────────────────────────────────────

async def _load_connections(ctx) -> list[dict]:
    raw = await ctx.secrets.get(_SECRET_NAME)
    try:
        return json.loads(raw) if raw else []
    except Exception:
        return []


async def _save_connections(ctx, connections: list[dict]) -> None:
    await ctx.secrets.set(_SECRET_NAME, json.dumps(connections))


async def _find_connection(ctx, connection_id: str) -> dict | None:
    connections = await _load_connections(ctx)
    if not connection_id and len(connections) == 1:
        return connections[0]
    for c in connections:
        if c.get("id") == connection_id:
            return c
    return None


async def _resolve(ctx, connection_id: str) -> tuple[str, str] | None:
    conn = await _find_connection(ctx, connection_id)
    if not conn:
        return None
    return conn["base_url"], conn["access_token"]


def _err(prefix: str, e: "gc.ProviderError") -> ActionResult:
    return ActionResult.error(f"{prefix}: {e.detail}", code=f"GITLAB_HTTP_{e.status_code}")


def _no_connection() -> ActionResult:
    return ActionResult.error(
        "No GitLab connection found. Connect one first with connect_gitlab.",
        code="GITLAB_NOT_CONNECTED",
    )


# ──────────────────────────────────────────────────────────────────────────
# Connection management
# ──────────────────────────────────────────────────────────────────────────

@chat.function(
    "connect_gitlab",
    "Connect your GitLab instance by saving your Personal Access Token "
    "plus its base URL, after checking they actually work together. "
    "You'll need a Personal Access Token with the 'api' scope (or "
    "'read_api' for read-only use) -- create it in User Settings > Access "
    "Tokens (works for both gitlab.com and your own self-managed "
    "instance). Scoped to CI/CD only -- repository files, merge requests "
    "and issues are out of scope here.",
    action_type="write",
    chain_callable=True,
    data_model=ProviderConnection,
    event="gitlab-cicd-connector.connect_gitlab",
    effects=["gitlab.provider.connected"],
)
async def connect_gitlab(ctx, params: ConnectGitlabParams) -> ActionResult:
    """Connect your GitLab instance by saving your Personal Access Token plus its base URL, after checking they actually work together. You'll need a Personal Access Token with the 'api' scope (or 'read_api' for read-only use) -- create it in User Settings > Access Tokens (works for both gitlab.com and your own self-managed instance). Scoped to CI/CD only -- repository files, merge requests and issues are out of scope here."""
    if not params.access_token:
        return ActionResult.error("Please provide your GitLab Personal Access Token.", code="GITLAB_MISSING_TOKEN")
    try:
        base_url = gc.normalize_base_url(params.base_url, params.allow_private_http)
    except gc.ProviderError as e:
        return _err("Could not connect", e)
    try:
        user = await gc.check_connection(ctx, base_url, params.access_token)
    except gc.ProviderError as e:
        return _err("Could not connect", e)

    connections = await _load_connections(ctx)
    conn_id = str(uuid.uuid4())
    label = params.label or user.get("username") or base_url
    connections.append({
        "id": conn_id,
        "title": label,
        "base_url": base_url,
        "access_token": params.access_token,
        "detail": f"{base_url} -- {user.get('username', '')}",
    })
    await _save_connections(ctx, connections)
    return ActionResult.success(
        ProviderConnection(id=conn_id, title=label, connected=True,
                            detail=f"Connected as {user.get('username', '')}",
                            base_url=base_url),
        summary=f"GitLab connected -- {base_url}.",
        refresh_panels=["gitlab_connect", "gitlab_settings"],
    )


@chat.function(
    "disconnect_gitlab",
    "Disconnect a GitLab instance: deletes the saved Personal Access "
    "Token. Nothing in GitLab itself is changed; the token remains valid "
    "there until you revoke it yourself.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="gitlab-cicd-connector.disconnect_gitlab",
    effects=["gitlab.provider.disconnected"],
)
async def disconnect_gitlab(ctx, params: DisconnectGitlabParams) -> ActionResult:
    """Disconnect a GitLab instance: deletes the saved Personal Access Token. Nothing in GitLab itself is changed; the token remains valid there until you revoke it yourself."""
    connections = await _load_connections(ctx)
    remaining = [c for c in connections if c.get("id") != params.connection_id]
    if len(remaining) == len(connections) and connections:
        return ActionResult.error("Connection not found.", code="GITLAB_CONN_NOT_FOUND")
    await _save_connections(ctx, remaining)
    return ActionResult.success(
        DeleteResult(deleted=True, id=params.connection_id),
        summary="GitLab instance disconnected.",
        refresh_panels=["gitlab_connect", "gitlab_settings"],
    )


@chat.function(
    "list_connections",
    "List the connected GitLab instances.",
    action_type="read",
    chain_callable=True,
    data_model=ProviderConnectionList,
)
async def list_connections(ctx, params: NoParams) -> ActionResult:
    """List the connected GitLab instances."""
    connections = await _load_connections(ctx)
    items = [ProviderConnection(id=c.get("id", ""), title=c.get("title", ""), connected=True,
                                 detail=c.get("detail", ""), base_url=c.get("base_url", ""))
             for c in connections]
    return ActionResult.success(ProviderConnectionList(connections=items), summary="Connections listed.")


# ──────────────────────────────────────────────────────────────────────────
# Pipelines
# ──────────────────────────────────────────────────────────────────────────

@chat.function(
    "list_pipelines",
    "List pipelines in a project, optionally filtered by ref, status, "
    "scope, source, or the username who triggered them.",
    action_type="read",
    chain_callable=True,
    data_model=PipelineList,
)
async def list_pipelines(ctx, params: ListPipelinesParams) -> ActionResult:
    """List pipelines in a project, optionally filtered by ref, status, scope, source, or the username who triggered them."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    filters = {k: v for k, v in {
        "ref": params.ref, "status": params.status, "scope": params.scope,
        "source": params.source, "username": params.username,
        "order_by": params.order_by, "sort": params.sort,
        "page": params.page, "per_page": params.per_page,
    }.items() if v}
    try:
        data = await gc.list_pipelines(ctx, base_url, token, params.project_id, **filters)
    except gc.ProviderError as e:
        return _err("Could not list pipelines", e)
    items = [Pipeline(id=p.get("id", 0), iid=p.get("iid", 0),
                       project_id=p.get("project_id", 0), status=p.get("status", ""),
                       source=p.get("source", ""), ref=p.get("ref", ""), sha=p.get("sha", ""),
                       web_url=p.get("web_url", ""), created_at=p.get("created_at", ""),
                       updated_at=p.get("updated_at", ""))
             for p in (data if isinstance(data, list) else [])]
    return ActionResult.success(PipelineList(pipelines=items), summary="Pipelines listed.")


@chat.function(
    "get_pipeline",
    "Read one pipeline in full -- status, timing, and its own CI/CD variables entrypoint.",
    action_type="read",
    chain_callable=True,
    data_model=PipelineDetail,
)
async def get_pipeline(ctx, params: GetPipelineParams) -> ActionResult:
    """Read one pipeline in full -- status, timing, and its own CI/CD variables entrypoint."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        p = await gc.get_pipeline(ctx, base_url, token, params.project_id, params.pipeline_id)
    except gc.ProviderError as e:
        return _err("Could not get pipeline", e)
    return ActionResult.success(PipelineDetail(
        id=p.get("id", 0), iid=p.get("iid", 0), project_id=p.get("project_id", 0),
        status=p.get("status", ""), source=p.get("source", ""), ref=p.get("ref", ""),
        sha=p.get("sha", ""), before_sha=p.get("before_sha", ""), tag=p.get("tag", False),
        yaml_errors=p.get("yaml_errors") or "", user=(p.get("user") or {}).get("username", ""),
        created_at=p.get("created_at", ""), updated_at=p.get("updated_at", ""),
        started_at=p.get("started_at") or "", finished_at=p.get("finished_at") or "",
        duration=p.get("duration") or 0, queued_duration=p.get("queued_duration") or 0,
        coverage=p.get("coverage") or "", web_url=p.get("web_url", ""),
    ), summary="Pipeline retrieved.")


@chat.function(
    "get_pipeline_variables",
    "Read the CI/CD variables a specific pipeline run was actually triggered with.",
    action_type="read",
    chain_callable=True,
    data_model=PipelineVariableList,
)
async def get_pipeline_variables(ctx, params: GetPipelineVariablesParams) -> ActionResult:
    """Read the CI/CD variables a specific pipeline run was actually triggered with."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        data = await gc.get_pipeline_variables(ctx, base_url, token, params.project_id, params.pipeline_id)
    except gc.ProviderError as e:
        return _err("Could not get pipeline variables", e)
    items = [PipelineVariable(key=v.get("key", ""), value=v.get("value", ""),
                               variable_type=v.get("variable_type", ""))
             for v in data] if isinstance(data, list) else []
    return ActionResult.success(PipelineVariableList(variables=items), summary="Pipeline variables retrieved.")


@chat.function(
    "get_pipeline_test_report",
    "Read a pipeline's aggregated JUnit test report, if the pipeline "
    "published one (total/success/failed/skipped/error counts per suite).",
    action_type="read",
    chain_callable=True,
    data_model=PipelineTestReport,
)
async def get_pipeline_test_report(ctx, params: GetPipelineTestReportParams) -> ActionResult:
    """Read a pipeline's aggregated JUnit test report, if the pipeline published one (total/success/failed/skipped/error counts per suite)."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        data = await gc.get_pipeline_test_report(ctx, base_url, token, params.project_id, params.pipeline_id)
    except gc.ProviderError as e:
        return _err("Could not get pipeline test report", e)
    suites = [TestSuiteSummary(name=s.get("name", ""), total_count=s.get("total_count", 0),
                                success_count=s.get("success_count", 0), failed_count=s.get("failed_count", 0),
                                skipped_count=s.get("skipped_count", 0), error_count=s.get("error_count", 0))
              for s in (data.get("test_suites") or [])]
    return ActionResult.success(PipelineTestReport(
        total_time=data.get("total_time", 0.0), total_count=data.get("total_count", 0),
        success_count=data.get("success_count", 0), failed_count=data.get("failed_count", 0),
        skipped_count=data.get("skipped_count", 0), error_count=data.get("error_count", 0),
        test_suites=suites,
    ), summary="Pipeline test report retrieved.")


@chat.function(
    "create_pipeline",
    "Trigger a new pipeline run for a project on a given ref (branch/tag), "
    "optionally passing CI/CD variables.",
    action_type="write",
    chain_callable=True,
    data_model=Pipeline,
    event="gitlab-cicd-connector.create_pipeline",
    effects=["gitlab.pipeline.created"],
)
async def create_pipeline(ctx, params: CreatePipelineParams) -> ActionResult:
    """Trigger a new pipeline run for a project on a given ref (branch/tag), optionally passing CI/CD variables."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    variables = None
    if params.variables_json:
        try:
            variables = json.loads(params.variables_json)
        except Exception:
            return ActionResult.error(
                "variables_json must be valid JSON, e.g. [{\"key\":\"DEPLOY_ENV\",\"value\":\"staging\"}]",
                code="GITLAB_BAD_VARIABLES_JSON",
            )
    try:
        p = await gc.create_pipeline(ctx, base_url, token, params.project_id, params.ref, variables)
    except gc.ProviderError as e:
        return _err("Could not create pipeline", e)
    return ActionResult.success(
        Pipeline(id=p.get("id", 0), iid=p.get("iid", 0), project_id=p.get("project_id", 0),
                  status=p.get("status", ""), source=p.get("source", ""), ref=p.get("ref", ""),
                  sha=p.get("sha", ""), web_url=p.get("web_url", ""),
                  created_at=p.get("created_at", ""), updated_at=p.get("updated_at", "")),
        summary=f"Pipeline #{p.get('id')} started on {params.ref}.",
    )


@chat.function(
    "retry_pipeline",
    "Retry a failed or canceled pipeline's failed jobs.",
    action_type="write",
    chain_callable=True,
    data_model=PipelineActionResult,
    event="gitlab-cicd-connector.retry_pipeline",
    effects=["gitlab.pipeline.retried"],
)
async def retry_pipeline(ctx, params: RetryPipelineParams) -> ActionResult:
    """Retry a failed or canceled pipeline's failed jobs."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        p = await gc.retry_pipeline(ctx, base_url, token, params.project_id, params.pipeline_id)
    except gc.ProviderError as e:
        return _err("Could not retry pipeline", e)
    return ActionResult.success(
        PipelineActionResult(id=p.get("id", 0), status=p.get("status", "")),
        summary=f"Pipeline #{params.pipeline_id} retried.",
    )


@chat.function(
    "cancel_pipeline",
    "Cancel a running pipeline.",
    action_type="write",
    chain_callable=True,
    data_model=PipelineActionResult,
    event="gitlab-cicd-connector.cancel_pipeline",
    effects=["gitlab.pipeline.canceled"],
)
async def cancel_pipeline(ctx, params: CancelPipelineParams) -> ActionResult:
    """Cancel a running pipeline."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        p = await gc.cancel_pipeline(ctx, base_url, token, params.project_id, params.pipeline_id)
    except gc.ProviderError as e:
        return _err("Could not cancel pipeline", e)
    return ActionResult.success(
        PipelineActionResult(id=p.get("id", 0), status=p.get("status", "")),
        summary=f"Pipeline #{params.pipeline_id} canceled.",
    )


@chat.function(
    "delete_pipeline",
    "Permanently delete a pipeline and its jobs/artifacts/logs. Cannot be undone.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="gitlab-cicd-connector.delete_pipeline",
    effects=["gitlab.pipeline.deleted"],
)
async def delete_pipeline(ctx, params: DeletePipelineParams) -> ActionResult:
    """Permanently delete a pipeline and its jobs/artifacts/logs. Cannot be undone."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        result = await gc.delete_pipeline(ctx, base_url, token, params.project_id, params.pipeline_id)
    except gc.ProviderError as e:
        return _err("Could not delete pipeline", e)
    return ActionResult.success(
        DeleteResult(deleted=True, id=result.get("id", str(params.pipeline_id))),
        summary=f"Pipeline #{params.pipeline_id} deleted.",
    )


def _job_entity(j: dict) -> Job:
    runner = j.get("runner") or {}
    return Job(
        id=j.get("id", 0), name=j.get("name", ""), stage=j.get("stage", ""),
        status=j.get("status", ""), ref=j.get("ref", ""), tag=j.get("tag", False),
        allow_failure=j.get("allow_failure", False),
        created_at=j.get("created_at", ""), started_at=j.get("started_at", "") or "",
        finished_at=j.get("finished_at", "") or "", duration=j.get("duration", 0.0) or 0.0,
        web_url=j.get("web_url", ""),
        runner=(runner.get("description") or runner.get("name") or "") if isinstance(runner, dict) else "",
    )


def _jobs_from(data) -> list[Job]:
    return [_job_entity(j) for j in (data if isinstance(data, list) else [])]


# ──────────────────────────────────────────────────────────────────────────
# Jobs
# ──────────────────────────────────────────────────────────────────────────

@chat.function(
    "list_project_jobs",
    "List jobs across a project's pipelines, optionally filtered by status scope.",
    action_type="read",
    chain_callable=True,
    data_model=JobList,
)
async def list_project_jobs(ctx, params: ListProjectJobsParams) -> ActionResult:
    """List jobs across a project's pipelines, optionally filtered by status scope."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    filters = {"scope": params.scope, "page": params.page, "per_page": params.per_page}
    filters = {k: v for k, v in filters.items() if v}
    try:
        data = await gc.list_project_jobs(ctx, base_url, token, params.project_id, **filters)
    except gc.ProviderError as e:
        return _err("Could not list project jobs", e)
    items = _jobs_from(data)
    return ActionResult.success(JobList(jobs=items), summary="Project jobs listed.")


@chat.function(
    "list_pipeline_jobs",
    "List the jobs belonging to one pipeline, optionally filtered by status scope.",
    action_type="read",
    chain_callable=True,
    data_model=JobList,
)
async def list_pipeline_jobs(ctx, params: ListPipelineJobsParams) -> ActionResult:
    """List the jobs belonging to one pipeline, optionally filtered by status scope."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    filters = {}
    if params.scope:
        filters["scope"] = params.scope
    if params.include_retried:
        filters["include_retried"] = params.include_retried
    try:
        data = await gc.list_pipeline_jobs(ctx, base_url, token, params.project_id, params.pipeline_id, **filters)
    except gc.ProviderError as e:
        return _err("Could not list pipeline jobs", e)
    items = _jobs_from(data)
    return ActionResult.success(JobList(jobs=items), summary="Pipeline jobs listed.")


@chat.function(
    "list_pipeline_bridges",
    "List the bridge (trigger) jobs of a pipeline -- jobs that trigger "
    "downstream/multi-project pipelines, with the downstream pipeline "
    "and project they triggered.",
    action_type="read",
    chain_callable=True,
    data_model=PipelineBridgeList,
)
async def list_pipeline_bridges(ctx, params: ListPipelineBridgesParams) -> ActionResult:
    """List the bridge (trigger) jobs of a pipeline -- jobs that trigger downstream/multi-project pipelines, with the downstream pipeline and project they triggered."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    filters = {"scope": params.scope} if params.scope else {}
    try:
        data = await gc.list_pipeline_bridges(ctx, base_url, token, params.project_id, params.pipeline_id, **filters)
    except gc.ProviderError as e:
        return _err("Could not list pipeline bridges", e)
    items = []
    for b in (data if isinstance(data, list) else []):
        downstream = b.get("downstream_pipeline") or {}
        items.append(PipelineBridge(
            id=b.get("id", 0), name=b.get("name", ""), stage=b.get("stage", ""),
            status=b.get("status", ""),
            downstream_pipeline_id=(downstream.get("id", 0) if isinstance(downstream, dict) else 0),
            downstream_project_id=(downstream.get("project_id", 0) if isinstance(downstream, dict) else 0),
            web_url=b.get("web_url", ""),
        ))
    return ActionResult.success(PipelineBridgeList(bridges=items), summary="Pipeline bridges listed.")


@chat.function(
    "get_job",
    "Read one job in full -- status, timing, runner, and stage.",
    action_type="read",
    chain_callable=True,
    data_model=Job,
)
async def get_job(ctx, params: GetJobParams) -> ActionResult:
    """Read one job in full -- status, timing, runner, and stage."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        j = await gc.get_job(ctx, base_url, token, params.project_id, params.job_id)
    except gc.ProviderError as e:
        return _err("Could not get job", e)
    return ActionResult.success(_job_entity(j), summary="Job retrieved.")


@chat.function(
    "get_job_trace",
    "Read a job's console log/trace, capped to the last N lines (traces can be very large).",
    action_type="read",
    chain_callable=True,
    data_model=JobTrace,
)
async def get_job_trace(ctx, params: GetJobTraceParams) -> ActionResult:
    """Read a job's console log/trace, capped to the last N lines (traces can be very large)."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        trace = await gc.get_job_trace(ctx, base_url, token, params.project_id, params.job_id)
    except gc.ProviderError as e:
        return _err("Could not get job trace", e)
    lines = trace.splitlines()
    truncated = len(lines) > params.tail_lines
    tail = lines[-params.tail_lines:] if truncated else lines
    return ActionResult.success(JobTrace(job_id=params.job_id, trace="\n".join(tail), truncated=truncated), summary="Job trace retrieved.")


@chat.function(
    "retry_job",
    "Retry a failed or canceled job.",
    action_type="write",
    chain_callable=True,
    data_model=JobActionResult,
    event="gitlab-cicd-connector.retry_job",
    effects=["gitlab.job.retried"],
)
async def retry_job(ctx, params: JobActionParams) -> ActionResult:
    """Retry a failed or canceled job."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        j = await gc.retry_job(ctx, base_url, token, params.project_id, params.job_id)
    except gc.ProviderError as e:
        return _err("Could not retry job", e)
    return ActionResult.success(
        JobActionResult(id=j.get("id", 0), status=j.get("status", ""), web_url=j.get("web_url", "")),
        summary=f"Job #{params.job_id} retried.",
    )


@chat.function(
    "cancel_job",
    "Cancel a running job.",
    action_type="write",
    chain_callable=True,
    data_model=JobActionResult,
    event="gitlab-cicd-connector.cancel_job",
    effects=["gitlab.job.canceled"],
)
async def cancel_job(ctx, params: JobActionParams) -> ActionResult:
    """Cancel a running job."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        j = await gc.cancel_job(ctx, base_url, token, params.project_id, params.job_id)
    except gc.ProviderError as e:
        return _err("Could not cancel job", e)
    return ActionResult.success(
        JobActionResult(id=j.get("id", 0), status=j.get("status", ""), web_url=j.get("web_url", "")),
        summary=f"Job #{params.job_id} canceled.",
    )


@chat.function(
    "play_job",
    "Run a manual job that's waiting for a trigger.",
    action_type="write",
    chain_callable=True,
    data_model=JobActionResult,
    event="gitlab-cicd-connector.play_job",
    effects=["gitlab.job.played"],
)
async def play_job(ctx, params: JobActionParams) -> ActionResult:
    """Run a manual job that's waiting for a trigger."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        j = await gc.play_job(ctx, base_url, token, params.project_id, params.job_id)
    except gc.ProviderError as e:
        return _err("Could not play job", e)
    return ActionResult.success(
        JobActionResult(id=j.get("id", 0), status=j.get("status", ""), web_url=j.get("web_url", "")),
        summary=f"Job #{params.job_id} started.",
    )


@chat.function(
    "erase_job",
    "Erase a job's trace and artifacts (irreversible cleanup, job record itself stays).",
    action_type="destructive",
    chain_callable=True,
    data_model=JobActionResult,
    event="gitlab-cicd-connector.erase_job",
    effects=["gitlab.job.erased"],
)
async def erase_job(ctx, params: JobActionParams) -> ActionResult:
    """Erase a job's trace and artifacts (irreversible cleanup, job record itself stays)."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        j = await gc.erase_job(ctx, base_url, token, params.project_id, params.job_id)
    except gc.ProviderError as e:
        return _err("Could not erase job", e)
    return ActionResult.success(
        JobActionResult(id=j.get("id", 0), status=j.get("status", ""), web_url=j.get("web_url", "")),
        summary=f"Job #{params.job_id} erased.",
    )


# ──────────────────────────────────────────────────────────────────────────
# Runners
# ──────────────────────────────────────────────────────────────────────────

def _runner_entity(r: dict) -> Runner:
    return Runner(
        id=r.get("id", 0), description=r.get("description", ""),
        active=r.get("active", False), paused=r.get("paused", False),
        is_shared=r.get("is_shared", False), runner_type=r.get("runner_type", ""),
        status=r.get("status", ""), online=r.get("online", False),
        tag_list=r.get("tag_list") or [],
    )


@chat.function(
    "list_runners",
    "List runners visible to you (or, with all_runners, every runner on "
    "the instance if you're an admin), optionally filtered by scope "
    "(active/paused/online/offline), type, or tags.",
    action_type="read",
    chain_callable=True,
    data_model=RunnerList,
)
async def list_runners(ctx, params: ListRunnersParams) -> ActionResult:
    """List runners visible to you (or, with all_runners, every runner on the instance if you're an admin), optionally filtered by scope (active/paused/online/offline), type, or tags."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    filters = {k: v for k, v in {
        "scope": params.scope, "type": params.runner_type, "tag_list": params.tag_list,
    }.items() if v}
    try:
        data = await gc.list_runners(ctx, base_url, token, all_runners=params.all_runners, **filters)
    except gc.ProviderError as e:
        return _err("Could not list runners", e)
    items = [_runner_entity(r) for r in (data if isinstance(data, list) else [])]
    return ActionResult.success(RunnerList(runners=items), summary="Runners listed.")


@chat.function(
    "get_runner",
    "Read one runner in full -- version, IP, tags, timeout, and contact status.",
    action_type="read",
    chain_callable=True,
    data_model=RunnerDetail,
)
async def get_runner(ctx, params: GetRunnerParams) -> ActionResult:
    """Read one runner in full -- version, IP, tags, timeout, and contact status."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        r = await gc.get_runner(ctx, base_url, token, params.runner_id)
    except gc.ProviderError as e:
        return _err("Could not get runner", e)
    return ActionResult.success(RunnerDetail(
        id=r.get("id", 0), description=r.get("description", ""),
        active=r.get("active", False), paused=r.get("paused", False),
        is_shared=r.get("is_shared", False), runner_type=r.get("runner_type", ""),
        status=r.get("status", ""), online=r.get("online", False),
        tag_list=r.get("tag_list") or [], run_untagged=r.get("run_untagged", False),
        locked=r.get("locked", False), access_level=r.get("access_level", ""),
        version=r.get("version", ""), ip_address=r.get("ip_address", ""),
        maximum_timeout=r.get("maximum_timeout", 0) or 0, contacted_at=r.get("contacted_at", "") or "",
    ), summary="Runner retrieved.")


@chat.function(
    "update_runner",
    "Update a runner's description, pause state, tags, untagged-job "
    "acceptance, lock, access level, or max timeout. Only given fields change.",
    action_type="write",
    chain_callable=True,
    data_model=RunnerDetail,
    event="gitlab-cicd-connector.update_runner",
    effects=["gitlab.runner.updated"],
)
async def update_runner(ctx, params: UpdateRunnerParams) -> ActionResult:
    """Update a runner's description, pause state, tags, untagged-job acceptance, lock, access level, or max timeout. Only given fields change."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    fields = {}
    if params.description:
        fields["description"] = params.description
    if params.active is not None:
        fields["active"] = params.active
    if params.paused is not None:
        fields["paused"] = params.paused
    if params.tag_list:
        fields["tag_list"] = [t.strip() for t in params.tag_list.split(",") if t.strip()]
    if params.run_untagged is not None:
        fields["run_untagged"] = params.run_untagged
    if params.locked is not None:
        fields["locked"] = params.locked
    if params.access_level:
        fields["access_level"] = params.access_level
    if params.maximum_timeout is not None:
        fields["maximum_timeout"] = params.maximum_timeout
    try:
        r = await gc.update_runner(ctx, base_url, token, params.runner_id, **fields)
    except gc.ProviderError as e:
        return _err("Could not update runner", e)
    return ActionResult.success(RunnerDetail(
        id=r.get("id", 0), description=r.get("description", ""),
        active=r.get("active", False), paused=r.get("paused", False),
        is_shared=r.get("is_shared", False), runner_type=r.get("runner_type", ""),
        status=r.get("status", ""), online=r.get("online", False),
        tag_list=r.get("tag_list") or [], run_untagged=r.get("run_untagged", False),
        locked=r.get("locked", False), access_level=r.get("access_level", ""),
        version=r.get("version", ""), ip_address=r.get("ip_address", ""),
        maximum_timeout=r.get("maximum_timeout", 0) or 0, contacted_at=r.get("contacted_at", "") or "",
    ), summary=f"Runner #{params.runner_id} updated.")


@chat.function(
    "delete_runner",
    "Permanently delete/unregister a runner. Cannot be undone.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="gitlab-cicd-connector.delete_runner",
    effects=["gitlab.runner.deleted"],
)
async def delete_runner(ctx, params: DeleteRunnerParams) -> ActionResult:
    """Permanently delete/unregister a runner. Cannot be undone."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        result = await gc.delete_runner(ctx, base_url, token, params.runner_id)
    except gc.ProviderError as e:
        return _err("Could not delete runner", e)
    return ActionResult.success(
        DeleteResult(deleted=True, id=result.get("id", str(params.runner_id))),
        summary=f"Runner #{params.runner_id} deleted.",
    )


@chat.function(
    "list_runner_jobs",
    "List jobs that ran on one specific runner, optionally filtered by status.",
    action_type="read",
    chain_callable=True,
    data_model=JobList,
)
async def list_runner_jobs(ctx, params: ListRunnerJobsParams) -> ActionResult:
    """List jobs that ran on one specific runner, optionally filtered by status."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    filters = {k: v for k, v in {
        "status": params.status, "page": params.page, "per_page": params.per_page,
    }.items() if v}
    try:
        data = await gc.list_runner_jobs(ctx, base_url, token, params.runner_id, **filters)
    except gc.ProviderError as e:
        return _err("Could not list runner jobs", e)
    return ActionResult.success(JobList(jobs=_jobs_from(data)), summary="Runner jobs listed.")


@chat.function(
    "list_project_runners",
    "List runners enabled/assigned to a specific project.",
    action_type="read",
    chain_callable=True,
    data_model=RunnerList,
)
async def list_project_runners(ctx, params: ListProjectRunnersParams) -> ActionResult:
    """List runners enabled/assigned to a specific project."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        data = await gc.list_project_runners(ctx, base_url, token, params.project_id)
    except gc.ProviderError as e:
        return _err("Could not list project runners", e)
    items = [_runner_entity(r) for r in (data if isinstance(data, list) else [])]
    return ActionResult.success(RunnerList(runners=items), summary="Project runners listed.")


@chat.function(
    "enable_project_runner",
    "Enable (assign) an existing runner for a project so its pipelines can use it.",
    action_type="write",
    chain_callable=True,
    data_model=RunnerDetail,
    event="gitlab-cicd-connector.enable_project_runner",
    effects=["gitlab.runner.enabled"],
)
async def enable_project_runner(ctx, params: EnableProjectRunnerParams) -> ActionResult:
    """Enable (assign) an existing runner for a project so its pipelines can use it."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        r = await gc.enable_project_runner(ctx, base_url, token, params.project_id, params.runner_id)
    except gc.ProviderError as e:
        return _err("Could not enable project runner", e)
    return ActionResult.success(RunnerDetail(
        id=r.get("id", 0), description=r.get("description", ""),
        active=r.get("active", False), paused=r.get("paused", False),
        is_shared=r.get("is_shared", False), runner_type=r.get("runner_type", ""),
        status=r.get("status", ""), online=r.get("online", False),
        tag_list=r.get("tag_list") or [],
    ), summary=f"Runner #{params.runner_id} enabled for project.")


@chat.function(
    "disable_project_runner",
    "Disable (unassign) a runner from a project. Does not delete the runner itself.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="gitlab-cicd-connector.disable_project_runner",
    effects=["gitlab.runner.disabled"],
)
async def disable_project_runner(ctx, params: DisableProjectRunnerParams) -> ActionResult:
    """Disable (unassign) a runner from a project. Does not delete the runner itself."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        result = await gc.disable_project_runner(ctx, base_url, token, params.project_id, params.runner_id)
    except gc.ProviderError as e:
        return _err("Could not disable project runner", e)
    return ActionResult.success(
        DeleteResult(deleted=True, id=result.get("id", str(params.runner_id))),
        summary=f"Runner #{params.runner_id} disabled for project.",
    )


# ──────────────────────────────────────────────────────────────────────────
# CI/CD Variables -- project level
# ──────────────────────────────────────────────────────────────────────────

def _variable_entity(v: dict) -> Variable:
    return Variable(
        key=v.get("key", ""), value=v.get("value", ""),
        variable_type=v.get("variable_type", ""), protected=v.get("protected", False),
        masked=v.get("masked", False), hidden=v.get("hidden", False),
        raw=v.get("raw", False), environment_scope=v.get("environment_scope", ""),
        description=v.get("description", "") or "",
    )


@chat.function(
    "list_project_variables",
    "List CI/CD variables defined at project level.",
    action_type="read",
    chain_callable=True,
    data_model=VariableList,
)
async def list_project_variables(ctx, params: ListProjectVariablesParams) -> ActionResult:
    """List CI/CD variables defined at project level."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        data = await gc.list_project_variables(ctx, base_url, token, params.project_id,
                                                page=params.page, per_page=params.per_page)
    except gc.ProviderError as e:
        return _err("Could not list project variables", e)
    items = [_variable_entity(v) for v in (data if isinstance(data, list) else [])]
    return ActionResult.success(VariableList(variables=items), summary="Project variables listed.")


@chat.function(
    "get_project_variable",
    "Read one project CI/CD variable's value and settings.",
    action_type="read",
    chain_callable=True,
    data_model=Variable,
)
async def get_project_variable(ctx, params: GetProjectVariableParams) -> ActionResult:
    """Read one project CI/CD variable's value and settings."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    filters = {"filter[environment_scope]": params.environment_scope} if params.environment_scope else {}
    try:
        v = await gc.get_project_variable(ctx, base_url, token, params.project_id, params.key, **filters)
    except gc.ProviderError as e:
        return _err("Could not get project variable", e)
    return ActionResult.success(_variable_entity(v), summary="Project variable retrieved.")


@chat.function(
    "create_project_variable",
    "Create a new project-level CI/CD variable -- key/value plus "
    "protection, masking, scope, and type settings.",
    action_type="write",
    chain_callable=True,
    data_model=Variable,
    event="gitlab-cicd-connector.create_project_variable",
    effects=["gitlab.variable.created"],
)
async def create_project_variable(ctx, params: CreateProjectVariableParams) -> ActionResult:
    """Create a new project-level CI/CD variable -- key/value plus protection, masking, scope, and type settings."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        v = await gc.create_project_variable(
            ctx, base_url, token, params.project_id, params.key, params.value,
            variable_type=params.variable_type, protected=params.protected,
            masked=params.masked, hidden=params.hidden, raw=params.raw,
            environment_scope=params.environment_scope, description=params.description or None,
        )
    except gc.ProviderError as e:
        return _err("Could not create project variable", e)
    return ActionResult.success(_variable_entity(v), summary=f"Variable '{params.key}' created.")


@chat.function(
    "update_project_variable",
    "Update an existing project CI/CD variable's value/protection/masking/scope/description.",
    action_type="write",
    chain_callable=True,
    data_model=Variable,
    event="gitlab-cicd-connector.update_project_variable",
    effects=["gitlab.variable.updated"],
)
async def update_project_variable(ctx, params: UpdateProjectVariableParams) -> ActionResult:
    """Update an existing project CI/CD variable's value/protection/masking/scope/description."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    fields = {k: v for k, v in {
        "value": params.value or None, "protected": params.protected, "masked": params.masked,
        "raw": params.raw, "environment_scope": params.environment_scope or None,
        "description": params.description or None,
    }.items() if v is not None}
    if params.filter_environment_scope:
        fields["filter[environment_scope]"] = params.filter_environment_scope
    try:
        v = await gc.update_project_variable(ctx, base_url, token, params.project_id, params.key, **fields)
    except gc.ProviderError as e:
        return _err("Could not update project variable", e)
    return ActionResult.success(_variable_entity(v), summary=f"Variable '{params.key}' updated.")


@chat.function(
    "delete_project_variable",
    "Permanently delete a project CI/CD variable.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="gitlab-cicd-connector.delete_project_variable",
    effects=["gitlab.variable.deleted"],
)
async def delete_project_variable(ctx, params: DeleteProjectVariableParams) -> ActionResult:
    """Permanently delete a project CI/CD variable."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    filters = {"filter[environment_scope]": params.environment_scope} if params.environment_scope else {}
    try:
        await gc.delete_project_variable(ctx, base_url, token, params.project_id, params.key, **filters)
    except gc.ProviderError as e:
        return _err("Could not delete project variable", e)
    return ActionResult.success(DeleteResult(deleted=True, id=params.key), summary=f"Variable '{params.key}' deleted.")


# ──────────────────────────────────────────────────────────────────────────
# CI/CD Variables -- group level
# ──────────────────────────────────────────────────────────────────────────

@chat.function(
    "list_group_variables",
    "List CI/CD variables defined at group level (inherited by every project in the group).",
    action_type="read",
    chain_callable=True,
    data_model=VariableList,
)
async def list_group_variables(ctx, params: ListGroupVariablesParams) -> ActionResult:
    """List CI/CD variables defined at group level (inherited by every project in the group)."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        data = await gc.list_group_variables(ctx, base_url, token, params.group_id,
                                              page=params.page, per_page=params.per_page)
    except gc.ProviderError as e:
        return _err("Could not list group variables", e)
    items = [_variable_entity(v) for v in (data if isinstance(data, list) else [])]
    return ActionResult.success(VariableList(variables=items), summary="Group variables listed.")


@chat.function(
    "get_group_variable",
    "Read one group CI/CD variable's value and settings.",
    action_type="read",
    chain_callable=True,
    data_model=Variable,
)
async def get_group_variable(ctx, params: GetGroupVariableParams) -> ActionResult:
    """Read one group CI/CD variable's value and settings."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        v = await gc.get_group_variable(ctx, base_url, token, params.group_id, params.key)
    except gc.ProviderError as e:
        return _err("Could not get group variable", e)
    return ActionResult.success(_variable_entity(v), summary="Group variable retrieved.")


@chat.function(
    "create_group_variable",
    "Create a new group-level CI/CD variable, inherited by every project in the group.",
    action_type="write",
    chain_callable=True,
    data_model=Variable,
    event="gitlab-cicd-connector.create_group_variable",
    effects=["gitlab.variable.created"],
)
async def create_group_variable(ctx, params: CreateGroupVariableParams) -> ActionResult:
    """Create a new group-level CI/CD variable, inherited by every project in the group."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        v = await gc.create_group_variable(
            ctx, base_url, token, params.group_id, params.key, params.value,
            variable_type=params.variable_type, protected=params.protected,
            masked=params.masked, environment_scope=params.environment_scope,
            description=params.description or None,
        )
    except gc.ProviderError as e:
        return _err("Could not create group variable", e)
    return ActionResult.success(_variable_entity(v), summary=f"Group variable '{params.key}' created.")


@chat.function(
    "update_group_variable",
    "Update an existing group CI/CD variable's value/protection/masking/scope/description.",
    action_type="write",
    chain_callable=True,
    data_model=Variable,
    event="gitlab-cicd-connector.update_group_variable",
    effects=["gitlab.variable.updated"],
)
async def update_group_variable(ctx, params: UpdateGroupVariableParams) -> ActionResult:
    """Update an existing group CI/CD variable's value/protection/masking/scope/description."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    fields = {k: v for k, v in {
        "value": params.value or None, "protected": params.protected, "masked": params.masked,
        "environment_scope": params.environment_scope or None, "description": params.description or None,
    }.items() if v is not None}
    try:
        v = await gc.update_group_variable(ctx, base_url, token, params.group_id, params.key, **fields)
    except gc.ProviderError as e:
        return _err("Could not update group variable", e)
    return ActionResult.success(_variable_entity(v), summary=f"Group variable '{params.key}' updated.")


@chat.function(
    "delete_group_variable",
    "Permanently delete a group CI/CD variable.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="gitlab-cicd-connector.delete_group_variable",
    effects=["gitlab.variable.deleted"],
)
async def delete_group_variable(ctx, params: DeleteGroupVariableParams) -> ActionResult:
    """Permanently delete a group CI/CD variable."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        await gc.delete_group_variable(ctx, base_url, token, params.group_id, params.key)
    except gc.ProviderError as e:
        return _err("Could not delete group variable", e)
    return ActionResult.success(DeleteResult(deleted=True, id=params.key), summary=f"Group variable '{params.key}' deleted.")


# ──────────────────────────────────────────────────────────────────────────
# Pipeline Trigger Tokens
# ──────────────────────────────────────────────────────────────────────────

def _trigger_entity(t: dict) -> Trigger:
    owner = t.get("owner") or {}
    return Trigger(
        id=t.get("id", 0), description=t.get("description", ""), token=t.get("token", ""),
        owner=(owner.get("username") or "") if isinstance(owner, dict) else "",
        created_at=t.get("created_at", ""), last_used=t.get("last_used", "") or "",
    )


@chat.function(
    "list_pipeline_triggers",
    "List pipeline trigger tokens defined on a project.",
    action_type="read",
    chain_callable=True,
    data_model=TriggerList,
)
async def list_pipeline_triggers(ctx, params: ListTriggersParams) -> ActionResult:
    """List pipeline trigger tokens defined on a project."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        data = await gc.list_triggers(ctx, base_url, token, params.project_id)
    except gc.ProviderError as e:
        return _err("Could not list pipeline triggers", e)
    items = [_trigger_entity(t) for t in (data if isinstance(data, list) else [])]
    return ActionResult.success(TriggerList(triggers=items), summary="Pipeline triggers listed.")


@chat.function(
    "create_pipeline_trigger",
    "Create a new pipeline trigger token for a project -- use its token "
    "value with run_pipeline_trigger to trigger pipelines from external "
    "CI/CD systems without a full Personal Access Token.",
    action_type="write",
    chain_callable=True,
    data_model=Trigger,
    event="gitlab-cicd-connector.create_pipeline_trigger",
    effects=["gitlab.trigger.created"],
)
async def create_pipeline_trigger(ctx, params: CreateTriggerParams) -> ActionResult:
    """Create a new pipeline trigger token for a project -- use its token value with run_pipeline_trigger to trigger pipelines from external CI/CD systems without a full Personal Access Token."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        t = await gc.create_trigger(ctx, base_url, token, params.project_id, params.description)
    except gc.ProviderError as e:
        return _err("Could not create pipeline trigger", e)
    return ActionResult.success(_trigger_entity(t), summary=f"Trigger '{params.description}' created.")


@chat.function(
    "update_pipeline_trigger",
    "Update an existing pipeline trigger token's description.",
    action_type="write",
    chain_callable=True,
    data_model=Trigger,
    event="gitlab-cicd-connector.update_pipeline_trigger",
    effects=["gitlab.trigger.updated"],
)
async def update_pipeline_trigger(ctx, params: UpdateTriggerParams) -> ActionResult:
    """Update an existing pipeline trigger token's description."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        t = await gc.update_trigger(ctx, base_url, token, params.project_id, params.trigger_id, params.description)
    except gc.ProviderError as e:
        return _err("Could not update pipeline trigger", e)
    return ActionResult.success(_trigger_entity(t), summary=f"Trigger #{params.trigger_id} updated.")


@chat.function(
    "delete_pipeline_trigger",
    "Permanently revoke/delete a pipeline trigger token.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="gitlab-cicd-connector.delete_pipeline_trigger",
    effects=["gitlab.trigger.deleted"],
)
async def delete_pipeline_trigger(ctx, params: DeleteTriggerParams) -> ActionResult:
    """Permanently revoke/delete a pipeline trigger token."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        await gc.delete_trigger(ctx, base_url, token, params.project_id, params.trigger_id)
    except gc.ProviderError as e:
        return _err("Could not delete pipeline trigger", e)
    return ActionResult.success(DeleteResult(deleted=True, id=str(params.trigger_id)), summary=f"Trigger #{params.trigger_id} deleted.")


@chat.function(
    "run_pipeline_trigger",
    "Trigger a pipeline run using a trigger token (not a Personal Access "
    "Token) -- GitLab's documented mechanism for external CI/CD systems.",
    action_type="write",
    chain_callable=True,
    data_model=PipelineActionResult,
    event="gitlab-cicd-connector.run_pipeline_trigger",
    effects=["gitlab.trigger.ran"],
)
async def run_pipeline_trigger(ctx, params: RunPipelineTriggerParams) -> ActionResult:
    """Trigger a pipeline run using a trigger token (not a Personal Access Token) -- GitLab's documented mechanism for external CI/CD systems."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, _token = resolved
    variables = None
    if params.variables_json:
        try:
            variables = json.loads(params.variables_json)
        except Exception:
            return ActionResult.error(
                "variables_json must be a valid JSON object, e.g. {\"DEPLOY_ENV\":\"staging\"}",
                code="GITLAB_BAD_VARIABLES_JSON",
            )
    try:
        p = await gc.run_pipeline_trigger(ctx, base_url, params.project_id, params.trigger_token, params.ref, variables)
    except gc.ProviderError as e:
        return _err("Could not run pipeline trigger", e)
    return ActionResult.success(
        PipelineActionResult(id=p.get("id", 0), status=p.get("status", ""), web_url=p.get("web_url", "")),
        summary=f"Pipeline #{p.get('id')} triggered on {params.ref}.",
    )


# ──────────────────────────────────────────────────────────────────────────
# Pipeline Schedules
# ──────────────────────────────────────────────────────────────────────────

def _schedule_entity(s: dict) -> PipelineSchedule:
    owner = s.get("owner") or {}
    return PipelineSchedule(
        id=s.get("id", 0), description=s.get("description", ""), ref=s.get("ref", ""),
        cron=s.get("cron", ""), cron_timezone=s.get("cron_timezone", ""),
        next_run_at=s.get("next_run_at", "") or "", active=s.get("active", False),
        owner=(owner.get("username") or "") if isinstance(owner, dict) else "",
    )


@chat.function(
    "list_pipeline_schedules",
    "List pipeline schedules (cron-triggered pipelines) defined on a project.",
    action_type="read",
    chain_callable=True,
    data_model=PipelineScheduleList,
)
async def list_pipeline_schedules(ctx, params: ListPipelineSchedulesParams) -> ActionResult:
    """List pipeline schedules (cron-triggered pipelines) defined on a project."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        data = await gc.list_pipeline_schedules(ctx, base_url, token, params.project_id)
    except gc.ProviderError as e:
        return _err("Could not list pipeline schedules", e)
    items = [_schedule_entity(s) for s in (data if isinstance(data, list) else [])]
    return ActionResult.success(PipelineScheduleList(schedules=items), summary="Pipeline schedules listed.")


@chat.function(
    "get_pipeline_schedule",
    "Read one pipeline schedule in full, including its next run time and owner.",
    action_type="read",
    chain_callable=True,
    data_model=PipelineSchedule,
)
async def get_pipeline_schedule(ctx, params: GetPipelineScheduleParams) -> ActionResult:
    """Read one pipeline schedule in full, including its next run time and owner."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        s = await gc.get_pipeline_schedule(ctx, base_url, token, params.project_id, params.schedule_id)
    except gc.ProviderError as e:
        return _err("Could not get pipeline schedule", e)
    return ActionResult.success(_schedule_entity(s), summary="Pipeline schedule retrieved.")


@chat.function(
    "create_pipeline_schedule",
    "Create a new pipeline schedule -- a cron-triggered pipeline on a given ref.",
    action_type="write",
    chain_callable=True,
    data_model=PipelineSchedule,
    event="gitlab-cicd-connector.create_pipeline_schedule",
    effects=["gitlab.schedule.created"],
)
async def create_pipeline_schedule(ctx, params: CreatePipelineScheduleParams) -> ActionResult:
    """Create a new pipeline schedule -- a cron-triggered pipeline on a given ref."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        s = await gc.create_pipeline_schedule(
            ctx, base_url, token, params.project_id, params.description, params.ref,
            params.cron, cron_timezone=params.cron_timezone, active=params.active,
        )
    except gc.ProviderError as e:
        return _err("Could not create pipeline schedule", e)
    return ActionResult.success(_schedule_entity(s), summary=f"Schedule '{params.description}' created.")


@chat.function(
    "update_pipeline_schedule",
    "Update an existing pipeline schedule's description, ref, cron, timezone, or active state.",
    action_type="write",
    chain_callable=True,
    data_model=PipelineSchedule,
    event="gitlab-cicd-connector.update_pipeline_schedule",
    effects=["gitlab.schedule.updated"],
)
async def update_pipeline_schedule(ctx, params: UpdatePipelineScheduleParams) -> ActionResult:
    """Update an existing pipeline schedule's description, ref, cron, timezone, or active state."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    fields = {k: v for k, v in {
        "description": params.description or None, "ref": params.ref or None,
        "cron": params.cron or None, "cron_timezone": params.cron_timezone or None,
        "active": params.active,
    }.items() if v is not None}
    try:
        s = await gc.update_pipeline_schedule(ctx, base_url, token, params.project_id, params.schedule_id, **fields)
    except gc.ProviderError as e:
        return _err("Could not update pipeline schedule", e)
    return ActionResult.success(_schedule_entity(s), summary=f"Schedule #{params.schedule_id} updated.")


@chat.function(
    "delete_pipeline_schedule",
    "Permanently delete a pipeline schedule.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="gitlab-cicd-connector.delete_pipeline_schedule",
    effects=["gitlab.schedule.deleted"],
)
async def delete_pipeline_schedule(ctx, params: DeletePipelineScheduleParams) -> ActionResult:
    """Permanently delete a pipeline schedule."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        await gc.delete_pipeline_schedule(ctx, base_url, token, params.project_id, params.schedule_id)
    except gc.ProviderError as e:
        return _err("Could not delete pipeline schedule", e)
    return ActionResult.success(
        DeleteResult(deleted=True, id=str(params.schedule_id)),
        summary=f"Schedule #{params.schedule_id} deleted.",
    )


@chat.function(
    "run_pipeline_schedule",
    "Trigger a pipeline schedule to run right now (rate-limited by GitLab to once per minute).",
    action_type="write",
    chain_callable=True,
    data_model=PipelineActionResult,
    event="gitlab-cicd-connector.run_pipeline_schedule",
    effects=["gitlab.schedule.ran"],
)
async def run_pipeline_schedule(ctx, params: RunPipelineScheduleParams) -> ActionResult:
    """Trigger a pipeline schedule to run right now (rate-limited by GitLab to once per minute)."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        p = await gc.run_pipeline_schedule(ctx, base_url, token, params.project_id, params.schedule_id)
    except gc.ProviderError as e:
        return _err("Could not run pipeline schedule", e)
    return ActionResult.success(
        PipelineActionResult(id=p.get("id", 0) if isinstance(p, dict) else 0,
                              status=p.get("status", "") if isinstance(p, dict) else "",
                              web_url=p.get("web_url", "") if isinstance(p, dict) else ""),
        summary=f"Schedule #{params.schedule_id} triggered.",
    )


@chat.function(
    "set_schedule_variable",
    "Create or update a CI/CD variable attached to a pipeline schedule (upserts: creates if new, updates if the key already exists).",
    action_type="write",
    chain_callable=True,
    data_model=Variable,
    event="gitlab-cicd-connector.set_schedule_variable",
    effects=["gitlab.schedule.variable_set"],
)
async def set_schedule_variable(ctx, params: ScheduleVariableParams) -> ActionResult:
    """Create or update a CI/CD variable attached to a pipeline schedule (upserts: creates if new, updates if the key already exists)."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        v = await gc.set_schedule_variable(ctx, base_url, token, params.project_id, params.schedule_id,
                                            params.key, params.value, params.variable_type)
    except gc.ProviderError as e:
        return _err("Could not set schedule variable", e)
    return ActionResult.success(_variable_entity(v), summary=f"Schedule variable '{params.key}' set.")


@chat.function(
    "delete_schedule_variable",
    "Permanently remove a CI/CD variable from a pipeline schedule.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="gitlab-cicd-connector.delete_schedule_variable",
    effects=["gitlab.schedule.variable_deleted"],
)
async def delete_schedule_variable(ctx, params: DeleteScheduleVariableParams) -> ActionResult:
    """Permanently remove a CI/CD variable from a pipeline schedule."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        await gc.delete_schedule_variable(ctx, base_url, token, params.project_id, params.schedule_id, params.key)
    except gc.ProviderError as e:
        return _err("Could not delete schedule variable", e)
    return ActionResult.success(DeleteResult(deleted=True, id=params.key), summary=f"Schedule variable '{params.key}' deleted.")


# ──────────────────────────────────────────────────────────────────────────
# CI Lint
# ──────────────────────────────────────────────────────────────────────────

@chat.function(
    "lint_ci_yaml",
    "Validate raw .gitlab-ci.yml content against GitLab's CI Lint engine -- checks syntax and semantic errors before you commit a pipeline config.",
    action_type="read",
    chain_callable=True,
    data_model=LintResult,
)
async def lint_ci_yaml(ctx, params: LintCiYamlParams) -> ActionResult:
    """Validate raw .gitlab-ci.yml content against GitLab's CI Lint engine -- checks syntax and semantic errors before you commit a pipeline config."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        data = await gc.lint_ci_yaml(ctx, base_url, token, params.content,
                                      params.include_merged_yaml, params.include_jobs)
    except gc.ProviderError as e:
        return _err("Could not lint CI YAML", e)
    return ActionResult.success(LintResult(
        valid=data.get("valid", False), errors=data.get("errors") or [], warnings=data.get("warnings") or [],
        merged_yaml=data.get("merged_yaml", "") or "",
        job_names=[j.get("name", "") for j in (data.get("jobs") or [])] if data.get("jobs") else [],
    ), summary="Lint ci yaml done.")


@chat.function(
    "project_lint_ci_yaml",
    "Validate a project's own .gitlab-ci.yml (its current config on a ref, or explicit content), with the project's own includes/extends resolved.",
    action_type="read",
    chain_callable=True,
    data_model=LintResult,
)
async def project_lint_ci_yaml(ctx, params: ProjectLintCiYamlParams) -> ActionResult:
    """Validate a project's own .gitlab-ci.yml (its current config on a ref, or explicit content), with the project's own includes/extends resolved."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        data = await gc.project_lint_ci_yaml(ctx, base_url, token, params.project_id,
                                              params.content or None, params.dry_run, params.ref or None)
    except gc.ProviderError as e:
        return _err("Could not lint project CI YAML", e)
    return ActionResult.success(LintResult(
        valid=data.get("valid", False), errors=data.get("errors") or [], warnings=data.get("warnings") or [],
        merged_yaml=data.get("merged_yaml", "") or "", job_names=[],
    ), summary="Project lint ci yaml done.")


# ──────────────────────────────────────────────────────────────────────────
# Job Artifacts
# ──────────────────────────────────────────────────────────────────────────

@chat.function(
    "get_job_artifacts_url",
    "Get the signed download URL for a job's artifacts archive. GitLab "
    "streams the binary archive directly rather than a JSON body, so this "
    "returns the URL to fetch rather than the archive itself.",
    action_type="read",
    chain_callable=True,
    data_model=ArtifactsInfo,
)
async def get_job_artifacts_url(ctx, params: GetJobArtifactsParams) -> ActionResult:
    """Get the signed download URL for a job's artifacts archive. GitLab streams the binary archive directly rather than a JSON body, so this returns the URL to fetch rather than the archive itself."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, _token = resolved
    url = gc.download_job_artifacts_url(base_url, params.project_id, params.job_id)
    return ActionResult.success(ArtifactsInfo(
        job_id=params.job_id, download_url=url,
        note="Authenticate with your GitLab Personal Access Token (PRIVATE-TOKEN header) when fetching this URL.",
    ), summary="Job artifacts url retrieved.")


@chat.function(
    "keep_job_artifacts",
    "Mark a job's artifacts as kept -- exempts them from the project's expiry policy so they are never automatically deleted.",
    action_type="write",
    chain_callable=True,
    data_model=JobActionResult,
    event="gitlab-cicd-connector.keep_job_artifacts",
    effects=["gitlab.job.artifacts_kept"],
)
async def keep_job_artifacts(ctx, params: KeepJobArtifactsParams) -> ActionResult:
    """Mark a job's artifacts as kept -- exempts them from the project's expiry policy so they are never automatically deleted."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        j = await gc.keep_job_artifacts(ctx, base_url, token, params.project_id, params.job_id)
    except gc.ProviderError as e:
        return _err("Could not keep job artifacts", e)
    return ActionResult.success(
        JobActionResult(id=j.get("id", params.job_id), status=j.get("status", ""), web_url=j.get("web_url", "")),
        summary=f"Artifacts for job #{params.job_id} will be kept.",
    )


@chat.function(
    "delete_job_artifacts",
    "Permanently delete a job's artifacts archive right now, ahead of its expiry policy. Cannot be undone.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="gitlab-cicd-connector.delete_job_artifacts",
    effects=["gitlab.job.artifacts_deleted"],
)
async def delete_job_artifacts(ctx, params: DeleteJobArtifactsParams) -> ActionResult:
    """Permanently delete a job's artifacts archive right now, ahead of its expiry policy. Cannot be undone."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        await gc.delete_job_artifacts(ctx, base_url, token, params.project_id, params.job_id)
    except gc.ProviderError as e:
        return _err("Could not delete job artifacts", e)
    return ActionResult.success(
        DeleteResult(deleted=True, id=str(params.job_id)),
        summary=f"Artifacts for job #{params.job_id} deleted.",
    )


# ──────────────────────────────────────────────────────────────────────────
# Environments
# ──────────────────────────────────────────────────────────────────────────

def _environment_entity(e: dict) -> Environment:
    return Environment(
        id=e.get("id", 0), name=e.get("name", ""), slug=e.get("slug", ""),
        external_url=e.get("external_url", "") or "", state=e.get("state", ""),
        tier=e.get("tier", "") or "",
    )


@chat.function(
    "list_environments",
    "List environments (deployment targets like staging/production) defined on a project.",
    action_type="read",
    chain_callable=True,
    data_model=EnvironmentList,
)
async def list_environments(ctx, params: ListEnvironmentsParams) -> ActionResult:
    """List environments (deployment targets like staging/production) defined on a project."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    filters = {k: v for k, v in {"name": params.name, "states": params.states}.items() if v}
    try:
        data = await gc.list_environments(ctx, base_url, token, params.project_id, **filters)
    except gc.ProviderError as e:
        return _err("Could not list environments", e)
    items = [_environment_entity(e) for e in (data if isinstance(data, list) else [])]
    return ActionResult.success(EnvironmentList(environments=items), summary="Environments listed.")


@chat.function(
    "get_environment",
    "Read one environment in full -- its state, external URL, and deployment tier.",
    action_type="read",
    chain_callable=True,
    data_model=Environment,
)
async def get_environment(ctx, params: GetEnvironmentParams) -> ActionResult:
    """Read one environment in full -- its state, external URL, and deployment tier."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        e = await gc.get_environment(ctx, base_url, token, params.project_id, params.environment_id)
    except gc.ProviderError as e2:
        return _err("Could not get environment", e2)
    return ActionResult.success(_environment_entity(e), summary="Environment retrieved.")


@chat.function(
    "create_environment",
    "Create a new environment (deployment target) on a project.",
    action_type="write",
    chain_callable=True,
    data_model=Environment,
    event="gitlab-cicd-connector.create_environment",
    effects=["gitlab.environment.created"],
)
async def create_environment(ctx, params: CreateEnvironmentParams) -> ActionResult:
    """Create a new environment (deployment target) on a project."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    fields = {k: v for k, v in {"external_url": params.external_url, "tier": params.tier}.items() if v}
    try:
        e = await gc.create_environment(ctx, base_url, token, params.project_id, params.name, **fields)
    except gc.ProviderError as e2:
        return _err("Could not create environment", e2)
    return ActionResult.success(_environment_entity(e), summary=f"Environment '{params.name}' created.")


@chat.function(
    "update_environment",
    "Update an existing environment's name or external URL.",
    action_type="write",
    chain_callable=True,
    data_model=Environment,
    event="gitlab-cicd-connector.update_environment",
    effects=["gitlab.environment.updated"],
)
async def update_environment(ctx, params: UpdateEnvironmentParams) -> ActionResult:
    """Update an existing environment's name or external URL."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    fields = {k: v for k, v in {"name": params.name, "external_url": params.external_url}.items() if v}
    try:
        e = await gc.update_environment(ctx, base_url, token, params.project_id, params.environment_id, **fields)
    except gc.ProviderError as e2:
        return _err("Could not update environment", e2)
    return ActionResult.success(_environment_entity(e), summary=f"Environment #{params.environment_id} updated.")


@chat.function(
    "delete_environment",
    "Permanently delete an environment. Cannot be undone.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="gitlab-cicd-connector.delete_environment",
    effects=["gitlab.environment.deleted"],
)
async def delete_environment(ctx, params: DeleteEnvironmentParams) -> ActionResult:
    """Permanently delete an environment. Cannot be undone."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        await gc.delete_environment(ctx, base_url, token, params.project_id, params.environment_id)
    except gc.ProviderError as e:
        return _err("Could not delete environment", e)
    return ActionResult.success(
        DeleteResult(deleted=True, id=str(params.environment_id)),
        summary=f"Environment #{params.environment_id} deleted.",
    )


@chat.function(
    "stop_environment",
    "Stop an environment -- ends its active deployment (e.g. tears down a review app).",
    action_type="write",
    chain_callable=True,
    data_model=EnvironmentActionResult,
    event="gitlab-cicd-connector.stop_environment",
    effects=["gitlab.environment.stopped"],
)
async def stop_environment(ctx, params: StopEnvironmentParams) -> ActionResult:
    """Stop an environment -- ends its active deployment (e.g. tears down a review app)."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        e = await gc.stop_environment(ctx, base_url, token, params.project_id, params.environment_id)
    except gc.ProviderError as ex:
        return _err("Could not stop environment", ex)
    return ActionResult.success(
        EnvironmentActionResult(id=e.get("id", 0), name=e.get("name", ""), state=e.get("state", "")),
        summary=f"Environment #{params.environment_id} stopped.",
    )


# ──────────────────────────────────────────────────────────────────────────
# Deployments
# ──────────────────────────────────────────────────────────────────────────

def _deployment_entity(d: dict) -> Deployment:
    env = d.get("environment") or {}
    user = d.get("user") or {}
    return Deployment(
        id=d.get("id", 0), iid=d.get("iid", 0),
        environment=(env.get("name") or "") if isinstance(env, dict) else "",
        status=d.get("status", ""), ref=d.get("ref", ""), sha=d.get("sha", ""),
        created_at=d.get("created_at", ""), updated_at=d.get("updated_at", "") or "",
        user=(user.get("username") or "") if isinstance(user, dict) else "",
    )


@chat.function(
    "list_deployments",
    "List deployments in a project, optionally filtered by environment or status.",
    action_type="read",
    chain_callable=True,
    data_model=DeploymentList,
)
async def list_deployments(ctx, params: ListDeploymentsParams) -> ActionResult:
    """List deployments in a project, optionally filtered by environment or status."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    filters = {k: v for k, v in {
        "environment": params.environment, "status": params.status,
        "order_by": params.order_by, "sort": params.sort,
    }.items() if v}
    try:
        data = await gc.list_deployments(ctx, base_url, token, params.project_id, **filters)
    except gc.ProviderError as e:
        return _err("Could not list deployments", e)
    items = [_deployment_entity(d) for d in (data if isinstance(data, list) else [])]
    return ActionResult.success(DeploymentList(deployments=items), summary="Deployments listed.")


@chat.function(
    "get_deployment",
    "Read one deployment in full -- its environment, status, ref, and who triggered it.",
    action_type="read",
    chain_callable=True,
    data_model=Deployment,
)
async def get_deployment(ctx, params: GetDeploymentParams) -> ActionResult:
    """Read one deployment in full -- its environment, status, ref, and who triggered it."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        d = await gc.get_deployment(ctx, base_url, token, params.project_id, params.deployment_id)
    except gc.ProviderError as e:
        return _err("Could not get deployment", e)
    return ActionResult.success(_deployment_entity(d), summary="Deployment retrieved.")


@chat.function(
    "approve_deployment",
    "Approve or reject a deployment awaiting manual approval (protected environments with approval rules configured).",
    action_type="write",
    chain_callable=True,
    data_model=Deployment,
    event="gitlab-cicd-connector.approve_deployment",
    effects=["gitlab.deployment.approved"],
)
async def approve_deployment(ctx, params: ApproveDeploymentParams) -> ActionResult:
    """Approve or reject a deployment awaiting manual approval (protected environments with approval rules configured)."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        d = await gc.approve_deployment(ctx, base_url, token, params.project_id, params.deployment_id,
                                         params.status, params.comment or None)
    except gc.ProviderError as e:
        return _err("Could not approve/reject deployment", e)
    return ActionResult.success(
        _deployment_entity(d),
        summary=f"Deployment #{params.deployment_id} {params.status}.",
    )


# ──────────────────────────────────────────────────────────────────────────
# Bulk operations + Project CI Audit (Tier 3 value-add)
# ──────────────────────────────────────────────────────────────────────────

@chat.function(
    "bulk_retry_pipelines",
    "Retry several pipelines in one call, by explicit pipeline ids. "
    "Continues past per-item failures and reports which succeeded.",
    action_type="write",
    chain_callable=True,
    data_model=BulkResult,
    event="gitlab-cicd-connector.bulk_retry_pipelines",
    effects=["gitlab.pipeline.bulk_retried"],
)
async def bulk_retry_pipelines(ctx, params: BulkPipelineIdsParams) -> ActionResult:
    """Retry several pipelines in one call, by explicit pipeline ids. Continues past per-item failures and reports which succeeded."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    data = await gc.bulk_pipeline_action(ctx, base_url, token, params.project_id, params.pipeline_ids, "retry")
    items = [BulkResultItem(**r) for r in data.get("results", [])]
    return ActionResult.success(
        BulkResult(results=items, succeeded=data.get("succeeded", 0), failed=data.get("failed", 0)),
        summary=f"Retried {data.get('succeeded', 0)} of {len(params.pipeline_ids)} pipelines.",
    )


@chat.function(
    "bulk_cancel_pipelines",
    "Cancel several running pipelines in one call, by explicit pipeline ids. "
    "Continues past per-item failures and reports which succeeded.",
    action_type="destructive",
    chain_callable=True,
    data_model=BulkResult,
    event="gitlab-cicd-connector.bulk_cancel_pipelines",
    effects=["gitlab.pipeline.bulk_cancelled"],
)
async def bulk_cancel_pipelines(ctx, params: BulkPipelineIdsParams) -> ActionResult:
    """Cancel several running pipelines in one call, by explicit pipeline ids. Continues past per-item failures and reports which succeeded."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    data = await gc.bulk_pipeline_action(ctx, base_url, token, params.project_id, params.pipeline_ids, "cancel")
    items = [BulkResultItem(**r) for r in data.get("results", [])]
    return ActionResult.success(
        BulkResult(results=items, succeeded=data.get("succeeded", 0), failed=data.get("failed", 0)),
        summary=f"Cancelled {data.get('succeeded', 0)} of {len(params.pipeline_ids)} pipelines.",
    )


@chat.function(
    "bulk_retry_jobs",
    "Retry several jobs in one call, by explicit job ids. Continues past per-item failures and reports which succeeded.",
    action_type="write",
    chain_callable=True,
    data_model=BulkJobResult,
    event="gitlab-cicd-connector.bulk_retry_jobs",
    effects=["gitlab.job.bulk_retried"],
)
async def bulk_retry_jobs(ctx, params: BulkJobIdsParams) -> ActionResult:
    """Retry several jobs in one call, by explicit job ids. Continues past per-item failures and reports which succeeded."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    data = await gc.bulk_job_action(ctx, base_url, token, params.project_id, params.job_ids, "retry")
    items = [BulkJobResultItem(**r) for r in data.get("results", [])]
    return ActionResult.success(
        BulkJobResult(results=items, succeeded=data.get("succeeded", 0), failed=data.get("failed", 0)),
        summary=f"Retried {data.get('succeeded', 0)} of {len(params.job_ids)} jobs.",
    )


@chat.function(
    "bulk_cancel_jobs",
    "Cancel several running jobs in one call, by explicit job ids. Continues past per-item failures and reports which succeeded.",
    action_type="destructive",
    chain_callable=True,
    data_model=BulkJobResult,
    event="gitlab-cicd-connector.bulk_cancel_jobs",
    effects=["gitlab.job.bulk_cancelled"],
)
async def bulk_cancel_jobs(ctx, params: BulkJobIdsParams) -> ActionResult:
    """Cancel several running jobs in one call, by explicit job ids. Continues past per-item failures and reports which succeeded."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    data = await gc.bulk_job_action(ctx, base_url, token, params.project_id, params.job_ids, "cancel")
    items = [BulkJobResultItem(**r) for r in data.get("results", [])]
    return ActionResult.success(
        BulkJobResult(results=items, succeeded=data.get("succeeded", 0), failed=data.get("failed", 0)),
        summary=f"Cancelled {data.get('succeeded', 0)} of {len(params.job_ids)} jobs.",
    )


@chat.function(
    "get_failed_jobs_summary",
    "Value-add report: scan the most recent pipelines' failed jobs so "
    "recurring flaky/broken jobs stand out, instead of scrolling through "
    "every pipeline individually.",
    action_type="read",
    chain_callable=True,
    data_model=FailedJobsSummary,
)
async def get_failed_jobs_summary(ctx, params: GetFailedJobsSummaryParams) -> ActionResult:
    """Value-add report: scan the most recent pipelines' failed jobs so recurring flaky/broken jobs stand out, instead of scrolling through every pipeline individually."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        data = await gc.get_failed_jobs_summary(ctx, base_url, token, params.project_id, params.recent_pipelines)
    except gc.ProviderError as e:
        return _err("Could not get failed jobs summary", e)
    rows = [FailedJobSummaryRow(**r) for r in data.get("rows", [])]
    return ActionResult.success(
        FailedJobsSummary(rows=rows, total_failed=data.get("total_failed", 0)),
        summary=f"{data.get('total_failed', 0)} failed job(s) found across the last {params.recent_pipelines} pipelines.",
    )


@chat.function(
    "audit_project_ci",
    "Value-add report: one-glance CI/CD health snapshot for a project -- "
    "pipeline success rate, failing pipelines, runner availability, and "
    "CI/CD variable documentation, as named check rows.",
    action_type="read",
    chain_callable=True,
    data_model=AuditReport,
)
async def audit_project_ci(ctx, params: AuditProjectCiParams) -> ActionResult:
    """Value-add report: one-glance CI/CD health snapshot for a project -- pipeline success rate, failing pipelines, runner availability, and CI/CD variable documentation, as named check rows."""
    resolved = await _resolve(ctx, params.connection_id)
    if not resolved:
        return _no_connection()
    base_url, token = resolved
    try:
        data = await gc.audit_project_ci(ctx, base_url, token, params.project_id, params.recent_pipelines)
    except gc.ProviderError as e:
        return _err("Could not audit project CI", e)
    rows = [AuditRow(**r) for r in data.get("rows", [])]
    return ActionResult.success(AuditReport(
        project_id=data.get("project_id", ""), generated_at=data.get("generated_at", ""), rows=rows,
        success_rate_pct=data.get("success_rate_pct", 0.0), failing_pipelines=data.get("failing_pipelines", 0),
        stale_variables_flagged=data.get("stale_variables_flagged", False),
        offline_runners=data.get("offline_runners", 0),
    ), summary="Project ci audit ready.")

