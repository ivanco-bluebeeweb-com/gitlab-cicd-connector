"""Pydantic params models + SDL entity contracts for GitLab CI/CD Connector.

All params models are module-scope (V17 federal invariant, same rule as
n8n Connector / MuleSoft Connector's schemas.py).
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from imperal_sdk import sdl


class NoParams(BaseModel):
    """Explicit empty params model -- V17 disallows untyped handlers."""
    pass


# ──────────────────────────────────────────────────────────────────────────
# Connection
# ──────────────────────────────────────────────────────────────────────────


class ConnectGitlabParams(BaseModel):
    base_url: str = Field(
        "https://gitlab.com",
        description="Base URL of your GitLab instance, e.g. https://gitlab.com or your self-managed https://gitlab.example.com",
    )
    access_token: str = Field(
        "",
        description="Personal Access Token with 'api' or 'read_api' scope -- create it in User Settings > Access Tokens.",
    )
    allow_private_http: bool = Field(
        False,
        description=(
            "Set true to allow a plain http:// base_url for a self-managed "
            "instance on localhost or a private network. HTTPS is required otherwise."
        ),
    )
    label: str = Field("", description="Optional friendly name for this instance connection.")


class ProviderConnection(sdl.Entity):
    id: str = ""
    title: str = ""
    connected: bool = False
    detail: str = ""
    base_url: str = ""


class ProviderConnectionList(sdl.Entity):
    id: str = ""
    title: str = ""
    connections: list[ProviderConnection] = []


class DisconnectGitlabParams(BaseModel):
    connection_id: str = Field("", description="ID of the connection to disconnect.")


class DeleteResult(sdl.Entity):
    title: str = ""
    deleted: bool = False
    id: str = ""


# ──────────────────────────────────────────────────────────────────────────
# Pipelines
# ──────────────────────────────────────────────────────────────────────────


class ListPipelinesParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path (e.g. 'group/project').")
    ref: str = Field("", description="Filter by branch or tag name. Leave empty for all.")
    status: str = Field(
        "",
        description="Filter by status: created, waiting_for_resource, preparing, pending, running, success, failed, canceled, skipped, manual, scheduled. Leave empty for all.",
    )
    scope: str = Field("", description="Filter by scope: running, pending, finished, branches, tags. Leave empty for all.")
    source: str = Field("", description="Filter by trigger source, e.g. push, web, trigger, schedule, api, merge_request_event.")
    username: str = Field("", description="Filter by the username who triggered the pipeline.")
    order_by: str = Field("id", description="Field to order by: id, status, ref, updated_at, user_id.")
    sort: str = Field("desc", description="Sort order: asc or desc.")
    page: int = Field(1, ge=1, description="Page number.")
    per_page: int = Field(20, ge=1, le=100, description="Results per page (max 100).")


class Pipeline(sdl.Entity):
    title: str = ""
    id: int = 0
    iid: int = 0
    project_id: int = 0
    status: str = ""
    source: str = ""
    ref: str = ""
    sha: str = ""
    web_url: str = ""
    created_at: str = ""
    updated_at: str = ""
    user: str = ""


class PipelineList(sdl.Entity):
    id: str = ""
    title: str = ""
    pipelines: list[Pipeline] = []
    page: int = 1
    per_page: int = 20


class GetPipelineParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    pipeline_id: int = Field(..., description="Pipeline ID to retrieve.")


class PipelineDetail(sdl.Entity):
    title: str = ""
    id: int = 0
    iid: int = 0
    project_id: int = 0
    status: str = ""
    source: str = ""
    ref: str = ""
    sha: str = ""
    before_sha: str = ""
    web_url: str = ""
    created_at: str = ""
    updated_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration: int = 0
    queued_duration: int = 0
    coverage: str = ""
    user: str = ""


class CreatePipelineParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    ref: str = Field(..., description="Branch or tag to run the pipeline on, e.g. 'main'.")
    variables_json: str = Field(
        "",
        description='Optional JSON array of {"key": "...", "value": "..."} objects to pass as pipeline variables, e.g. [{"key":"DEPLOY_ENV","value":"staging"}]',
    )


class RetryPipelineParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    pipeline_id: int = Field(..., description="Pipeline ID to retry failed/canceled jobs for.")


class CancelPipelineParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    pipeline_id: int = Field(..., description="Pipeline ID to cancel.")


class DeletePipelineParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    pipeline_id: int = Field(..., description="Pipeline ID to delete permanently.")


class PipelineActionResult(sdl.Entity):
    title: str = ""
    id: int = 0
    status: str = ""
    web_url: str = ""


class GetPipelineVariablesParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    pipeline_id: int = Field(..., description="Pipeline ID.")


class PipelineVariable(sdl.Entity):
    id: str = ""
    title: str = ""
    key: str = ""
    value: str = ""
    variable_type: str = ""


class PipelineVariableList(sdl.Entity):
    id: str = ""
    title: str = ""
    variables: list[PipelineVariable] = []


class GetPipelineTestReportParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    pipeline_id: int = Field(..., description="Pipeline ID.")


class TestSuiteSummary(sdl.Entity):
    id: str = ""
    title: str = ""
    name: str = ""
    total_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    error_count: int = 0


class PipelineTestReport(sdl.Entity):
    id: str = ""
    title: str = ""
    total_time: float = 0.0
    total_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    test_suites: list[TestSuiteSummary] = []


# ──────────────────────────────────────────────────────────────────────────
# Jobs
# ──────────────────────────────────────────────────────────────────────────


class ListProjectJobsParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    scope: str = Field(
        "",
        description="Filter by job status: created, pending, running, failed, success, canceled, skipped, waiting_for_resource, manual. Leave empty for all.",
    )
    page: int = Field(1, ge=1, description="Page number.")
    per_page: int = Field(20, ge=1, le=100, description="Results per page (max 100).")


class ListPipelineJobsParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    pipeline_id: int = Field(..., description="Pipeline ID to list jobs for.")
    scope: str = Field("", description="Filter by job status. Leave empty for all.")
    include_retried: bool = Field(False, description="Include retried jobs in the response.")


class Job(sdl.Entity):
    title: str = ""
    id: int = 0
    name: str = ""
    stage: str = ""
    status: str = ""
    ref: str = ""
    tag: bool = False
    allow_failure: bool = False
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration: float = 0.0
    web_url: str = ""
    runner: str = ""


class JobList(sdl.Entity):
    id: str = ""
    title: str = ""
    jobs: list[Job] = []


class GetJobParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    job_id: int = Field(..., description="Job ID to retrieve.")


class GetJobTraceParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    job_id: int = Field(..., description="Job ID to fetch the log/trace for.")
    tail_lines: int = Field(200, ge=1, le=5000, description="Return only the last N lines of the trace (trace can be very large).")


class JobTrace(sdl.Entity):
    id: str = ""
    title: str = ""
    job_id: int = 0
    trace: str = ""
    truncated: bool = False


class JobActionParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    job_id: int = Field(..., description="Job ID to act on.")


class JobActionResult(sdl.Entity):
    title: str = ""
    id: int = 0
    status: str = ""
    web_url: str = ""


class ListPipelineBridgesParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    pipeline_id: int = Field(..., description="Pipeline ID whose bridge (trigger) jobs you want to list.")
    scope: str = Field("", description="Filter by status scope, e.g. 'success', 'failed'. Leave empty for all.")


class PipelineBridge(sdl.Entity):
    title: str = ""
    id: int = 0
    name: str = ""
    stage: str = ""
    status: str = ""
    downstream_pipeline_id: int = 0
    downstream_project_id: int = 0
    web_url: str = ""


class PipelineBridgeList(sdl.Entity):
    id: str = ""
    title: str = ""
    bridges: list[PipelineBridge] = []


# ──────────────────────────────────────────────────────────────────────────
# Job Artifacts
# ──────────────────────────────────────────────────────────────────────────


class GetJobArtifactsParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    job_id: int = Field(..., description="Job ID whose artifacts archive URL you want.")


class ArtifactsInfo(sdl.Entity):
    id: str = ""
    title: str = ""
    job_id: int = 0
    download_url: str = ""
    note: str = ""


class KeepJobArtifactsParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    job_id: int = Field(..., description="Job ID whose artifacts should be kept (exempted from expiry).")


class DeleteJobArtifactsParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    job_id: int = Field(..., description="Job ID whose artifacts archive should be permanently deleted.")


# ──────────────────────────────────────────────────────────────────────────
# Runners
# ──────────────────────────────────────────────────────────────────────────


class ListRunnersParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    scope: str = Field(
        "",
        description="Filter by scope: active, paused, online, offline, never_contacted. Leave empty for all runners visible to you.",
    )
    runner_type: str = Field("", description="Filter by type: instance_type, group_type, project_type. Leave empty for all.")
    tag_list: str = Field("", description="Comma-separated tags to filter by, e.g. 'docker,linux'.")
    all_runners: bool = Field(False, description="If true, list all runners on the instance (requires admin access) instead of only those available to you.")


class Runner(sdl.Entity):
    title: str = ""
    id: int = 0
    description: str = ""
    active: bool = False
    paused: bool = False
    is_shared: bool = False
    runner_type: str = ""
    status: str = ""
    online: bool = False
    tag_list: list[str] = []


class RunnerList(sdl.Entity):
    id: str = ""
    title: str = ""
    runners: list[Runner] = []


class GetRunnerParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    runner_id: int = Field(..., description="Runner ID to retrieve details for.")


class RunnerDetail(sdl.Entity):
    title: str = ""
    id: int = 0
    description: str = ""
    active: bool = False
    paused: bool = False
    is_shared: bool = False
    runner_type: str = ""
    status: str = ""
    online: bool = False
    tag_list: list[str] = []
    run_untagged: bool = False
    locked: bool = False
    access_level: str = ""
    version: str = ""
    ip_address: str = ""
    maximum_timeout: int = 0
    contacted_at: str = ""


class UpdateRunnerParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    runner_id: int = Field(..., description="Runner ID to update.")
    description: str = Field("", description="New description. Leave empty to keep unchanged.")
    active: bool | None = Field(None, description="Set active/inactive (deprecated alias for paused).")
    paused: bool | None = Field(None, description="Pause (true) or resume (false) the runner. Leave unset to keep unchanged.")
    tag_list: str = Field("", description="Comma-separated new tag list, replaces existing tags. Leave empty to keep unchanged.")
    run_untagged: bool | None = Field(None, description="Whether the runner should pick up untagged jobs.")
    locked: bool | None = Field(None, description="Whether the runner is locked to its current projects.")
    access_level: str = Field("", description="Access level: not_protected or ref_protected. Leave empty to keep unchanged.")
    maximum_timeout: int | None = Field(None, description="Maximum timeout in seconds for jobs this runner can run.")


class DeleteRunnerParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    runner_id: int = Field(..., description="Runner ID to permanently delete/unregister.")


class ListRunnerJobsParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    runner_id: int = Field(..., description="Runner ID to list jobs for.")
    status: str = Field("", description="Filter by job status. Leave empty for all.")
    page: int = Field(1, ge=1, description="Page number.")
    per_page: int = Field(20, ge=1, le=100, description="Results per page (max 100).")


class ListProjectRunnersParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")


class EnableProjectRunnerParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path to enable the runner for.")
    runner_id: int = Field(..., description="Runner ID to enable (assign) for this project.")


class DisableProjectRunnerParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path to disable the runner for.")
    runner_id: int = Field(..., description="Runner ID to disable (unassign) from this project.")


# ──────────────────────────────────────────────────────────────────────────
# CI/CD Variables (project + group level)
# ──────────────────────────────────────────────────────────────────────────


class ListProjectVariablesParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    page: int = Field(1, ge=1, description="Page number.")
    per_page: int = Field(20, ge=1, le=100, description="Results per page (max 100).")


class Variable(sdl.Entity):
    id: str = ""
    title: str = ""
    key: str = ""
    value: str = ""
    variable_type: str = ""
    protected: bool = False
    masked: bool = False
    hidden: bool = False
    raw: bool = False
    environment_scope: str = ""
    description: str = ""


class VariableList(sdl.Entity):
    id: str = ""
    title: str = ""
    variables: list[Variable] = []


class GetProjectVariableParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    key: str = Field(..., description="Variable key to retrieve.")
    environment_scope: str = Field("", description="If multiple variables share this key, disambiguate by environment scope.")


class CreateProjectVariableParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    key: str = Field(..., description="Variable key (A-Z, a-z, 0-9, _ only, max 255 chars).")
    value: str = Field(..., description="Variable value.")
    variable_type: str = Field("env_var", description="env_var or file.")
    protected: bool = Field(False, description="Only exposed to pipelines running on protected branches/tags.")
    masked: bool = Field(False, description="Masked in job logs. Value must meet GitLab's masking requirements (no whitespace, min length, etc).")
    hidden: bool = Field(False, description="Masked and hidden -- value cannot be revealed once set (Premium/Ultimate).")
    raw: bool = Field(False, description="If true, disables variable expansion/interpolation of $ references in the value.")
    environment_scope: str = Field("*", description="Environment scope this variable applies to, '*' for all environments.")
    description: str = Field("", description="Optional human-readable description.")


class UpdateProjectVariableParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    key: str = Field(..., description="Variable key to update.")
    value: str = Field("", description="New value. Leave empty to keep unchanged.")
    protected: bool | None = Field(None, description="Leave unset to keep unchanged.")
    masked: bool | None = Field(None, description="Leave unset to keep unchanged.")
    raw: bool | None = Field(None, description="Leave unset to keep unchanged.")
    environment_scope: str = Field("", description="New environment scope. Leave empty to keep unchanged.")
    description: str = Field("", description="New description. Leave empty to keep unchanged.")
    filter_environment_scope: str = Field("", description="If multiple variables share this key, disambiguate which one to update by its current environment scope.")


class DeleteProjectVariableParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    key: str = Field(..., description="Variable key to delete.")
    environment_scope: str = Field("", description="If multiple variables share this key, disambiguate by environment scope.")


class ListGroupVariablesParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    group_id: str = Field("", description="Group ID or URL-encoded path.")
    page: int = Field(1, ge=1, description="Page number.")
    per_page: int = Field(20, ge=1, le=100, description="Results per page (max 100).")


class GetGroupVariableParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    group_id: str = Field("", description="Group ID or URL-encoded path.")
    key: str = Field(..., description="Variable key to retrieve.")


class CreateGroupVariableParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    group_id: str = Field("", description="Group ID or URL-encoded path.")
    key: str = Field(..., description="Variable key (A-Z, a-z, 0-9, _ only, max 255 chars).")
    value: str = Field(..., description="Variable value.")
    variable_type: str = Field("env_var", description="env_var or file.")
    protected: bool = Field(False, description="Only exposed to pipelines running on protected branches/tags.")
    masked: bool = Field(False, description="Masked in job logs.")
    environment_scope: str = Field("*", description="Environment scope (Premium/Ultimate only), '*' for all environments.")
    description: str = Field("", description="Optional human-readable description.")


class UpdateGroupVariableParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    group_id: str = Field("", description="Group ID or URL-encoded path.")
    key: str = Field(..., description="Variable key to update.")
    value: str = Field("", description="New value. Leave empty to keep unchanged.")
    protected: bool | None = Field(None, description="Leave unset to keep unchanged.")
    masked: bool | None = Field(None, description="Leave unset to keep unchanged.")
    environment_scope: str = Field("", description="New environment scope. Leave empty to keep unchanged.")
    description: str = Field("", description="New description. Leave empty to keep unchanged.")


class DeleteGroupVariableParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    group_id: str = Field("", description="Group ID or URL-encoded path.")
    key: str = Field(..., description="Variable key to delete.")


# ──────────────────────────────────────────────────────────────────────────
# Pipeline Trigger Tokens
# ──────────────────────────────────────────────────────────────────────────


class ListTriggersParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")


class Trigger(sdl.Entity):
    title: str = ""
    id: int = 0
    description: str = ""
    token: str = ""
    owner: str = ""
    created_at: str = ""
    last_used: str = ""


class TriggerList(sdl.Entity):
    id: str = ""
    title: str = ""
    triggers: list[Trigger] = []


class CreateTriggerParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    description: str = Field(..., description="Human-readable description for this trigger token, e.g. 'Jenkins migration trigger'.")


class UpdateTriggerParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    trigger_id: int = Field(..., description="Trigger token ID to update.")
    description: str = Field(..., description="New description.")


class DeleteTriggerParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    trigger_id: int = Field(..., description="Trigger token ID to revoke/delete.")


class RunPipelineTriggerParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    trigger_token: str = Field(..., description="The pipeline trigger token itself (from create_trigger's result), not a connection ID.")
    ref: str = Field(..., description="Branch or tag to trigger the pipeline on.")
    variables_json: str = Field(
        "",
        description='Optional JSON object of {"VAR_NAME": "value"} pairs to pass as pipeline variables.',
    )


# ──────────────────────────────────────────────────────────────────────────
# Pipeline Schedules
# ──────────────────────────────────────────────────────────────────────────


class ListPipelineSchedulesParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")


class PipelineSchedule(sdl.Entity):
    title: str = ""
    id: int = 0
    description: str = ""
    ref: str = ""
    cron: str = ""
    cron_timezone: str = ""
    next_run_at: str = ""
    active: bool = False
    owner: str = ""


class PipelineScheduleList(sdl.Entity):
    id: str = ""
    title: str = ""
    schedules: list[PipelineSchedule] = []


class GetPipelineScheduleParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    schedule_id: int = Field(..., description="Pipeline schedule ID.")


class CreatePipelineScheduleParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    description: str = Field(..., description="Human-readable description, e.g. 'Nightly build'.")
    ref: str = Field(..., description="Branch or tag to run on.")
    cron: str = Field(..., description="Cron expression, e.g. '0 2 * * *' for daily at 2am.")
    cron_timezone: str = Field("UTC", description="Timezone for the cron expression, e.g. 'America/New_York'.")
    active: bool = Field(True, description="Whether the schedule is active immediately.")


class UpdatePipelineScheduleParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    schedule_id: int = Field(..., description="Pipeline schedule ID to update.")
    description: str = Field("", description="New description. Leave empty to keep unchanged.")
    ref: str = Field("", description="New branch/tag. Leave empty to keep unchanged.")
    cron: str = Field("", description="New cron expression. Leave empty to keep unchanged.")
    cron_timezone: str = Field("", description="New timezone. Leave empty to keep unchanged.")
    active: bool | None = Field(None, description="Leave unset to keep unchanged.")


class DeletePipelineScheduleParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    schedule_id: int = Field(..., description="Pipeline schedule ID to delete.")


class RunPipelineScheduleParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    schedule_id: int = Field(..., description="Pipeline schedule ID to trigger immediately (subject to a rate limit of once per minute).")


class ScheduleVariableParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    schedule_id: int = Field(..., description="Pipeline schedule ID.")
    key: str = Field(..., description="Variable key.")
    value: str = Field("", description="Variable value (required when creating).")
    variable_type: str = Field("env_var", description="env_var or file.")


class DeleteScheduleVariableParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    schedule_id: int = Field(..., description="Pipeline schedule ID.")
    key: str = Field(..., description="Variable key to delete.")


# ──────────────────────────────────────────────────────────────────────────
# CI Lint
# ──────────────────────────────────────────────────────────────────────────


class LintCiYamlParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    content: str = Field(..., description="Full raw YAML content of a .gitlab-ci.yml file to validate.")
    include_merged_yaml: bool = Field(False, description="Include the fully merged/expanded YAML (with includes/extends resolved) in the response.")
    include_jobs: bool = Field(False, description="Include a breakdown of individual jobs the config would produce.")


class ProjectLintCiYamlParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    content: str = Field("", description="Raw YAML to validate. Leave empty to validate the project's current .gitlab-ci.yml on the given ref.")
    dry_run: bool = Field(False, description="If true, actually creates the pipeline (as a dry run) to fully evaluate rules/includes -- requires a real ref.")
    ref: str = Field("", description="Branch/tag to validate against, used with dry_run or when content is empty.")


class LintResult(sdl.Entity):
    id: str = ""
    title: str = ""
    valid: bool = False
    errors: list[str] = []
    warnings: list[str] = []
    merged_yaml: str = ""
    job_names: list[str] = []


# ──────────────────────────────────────────────────────────────────────────
# Job Artifacts
# ──────────────────────────────────────────────────────────────────────────


class GetJobArtifactsParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    job_id: int = Field(..., description="Job ID whose artifacts archive metadata to check.")


class ArtifactsInfo(sdl.Entity):
    id: str = ""
    title: str = ""
    job_id: int = 0
    available: bool = False
    filename: str = ""
    size_bytes: int = 0
    file_type: str = ""
    download_url: str = ""


class DeleteJobArtifactsParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    job_id: int = Field(..., description="Job ID whose artifacts should be deleted.")


class KeepJobArtifactsParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    job_id: int = Field(..., description="Job ID whose artifacts should be marked to never expire.")


# ──────────────────────────────────────────────────────────────────────────
# Environments
# ──────────────────────────────────────────────────────────────────────────


class ListEnvironmentsParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    name: str = Field("", description="Return the environment with this exact name. Mutually exclusive with search.")
    search: str = Field("", description="Search environments by name (min 3 chars). Mutually exclusive with name.")
    states: str = Field("", description="Filter by state: available, stopping, stopped. Leave empty for all.")


class Environment(sdl.Entity):
    title: str = ""
    id: int = 0
    name: str = ""
    slug: str = ""
    state: str = ""
    external_url: str = ""
    tier: str = ""
    created_at: str = ""
    updated_at: str = ""


class EnvironmentList(sdl.Entity):
    id: str = ""
    title: str = ""
    environments: list[Environment] = []


class GetEnvironmentParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    environment_id: int = Field(..., description="Environment ID to retrieve.")


class CreateEnvironmentParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    name: str = Field(..., description="Environment name, e.g. 'staging' or 'production'.")
    external_url: str = Field("", description="Optional URL where this environment is reachable.")
    tier: str = Field("", description="Deployment tier: production, staging, testing, development, other. Leave empty to let GitLab infer it from the name.")


class UpdateEnvironmentParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    environment_id: int = Field(..., description="Environment ID to update.")
    name: str = Field("", description="New name. Leave empty to keep unchanged.")
    external_url: str = Field("", description="New URL. Leave empty to keep unchanged.")
    tier: str = Field("", description="New tier. Leave empty to keep unchanged.")


class DeleteEnvironmentParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    environment_id: int = Field(..., description="Environment ID to delete.")


class StopEnvironmentParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    environment_id: int = Field(..., description="Environment ID to stop.")


class EnvironmentActionResult(sdl.Entity):
    title: str = ""
    id: int = 0
    name: str = ""
    state: str = ""


# ──────────────────────────────────────────────────────────────────────────
# Deployments
# ──────────────────────────────────────────────────────────────────────────


class ListDeploymentsParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    environment: str = Field("", description="Filter by environment name.")
    status: str = Field("", description="Filter by status: created, running, success, failed, canceled, blocked. Leave empty for all.")
    order_by: str = Field("id", description="Field to order by: id, iid, created_at, updated_at, finished_at, ref.")
    sort: str = Field("asc", description="Sort order: asc or desc.")
    page: int = Field(1, ge=1, description="Page number.")
    per_page: int = Field(20, ge=1, le=100, description="Results per page (max 100).")


class Deployment(sdl.Entity):
    title: str = ""
    id: int = 0
    iid: int = 0
    ref: str = ""
    sha: str = ""
    status: str = ""
    environment: str = ""
    created_at: str = ""
    updated_at: str = ""
    finished_at: str = ""
    user: str = ""


class DeploymentList(sdl.Entity):
    id: str = ""
    title: str = ""
    deployments: list[Deployment] = []


class GetDeploymentParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    deployment_id: int = Field(..., description="Deployment ID to retrieve.")


class ApproveDeploymentParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    deployment_id: int = Field(..., description="Deployment ID awaiting approval.")
    status: str = Field(..., description="approved or rejected.")
    comment: str = Field("", description="Optional comment explaining the decision.")
    represented_as: str = Field("", description="If you belong to multiple approval groups, which one you are approving as.")


# ──────────────────────────────────────────────────────────────────────────
# Bulk operations (Tier 2/3 value-add)
# ──────────────────────────────────────────────────────────────────────────


class BulkPipelineIdsParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    pipeline_ids: list[int] = Field(..., description="List of pipeline IDs to act on together.")


class BulkResultItem(sdl.Entity):
    id: str = ""
    title: str = ""
    pipeline_id: int = 0
    ok: bool = False
    status: str = ""
    error: str = ""


class BulkResult(sdl.Entity):
    id: str = ""
    title: str = ""
    results: list[BulkResultItem] = []
    succeeded: int = 0
    failed: int = 0


class BulkJobIdsParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    job_ids: list[int] = Field(..., description="List of job IDs to act on together.")


class BulkJobResultItem(sdl.Entity):
    id: str = ""
    title: str = ""
    job_id: int = 0
    ok: bool = False
    status: str = ""
    error: str = ""


class BulkJobResult(sdl.Entity):
    id: str = ""
    title: str = ""
    results: list[BulkJobResultItem] = []
    succeeded: int = 0
    failed: int = 0


# ──────────────────────────────────────────────────────────────────────────
# Audit / value-add (Tier 3)
# ──────────────────────────────────────────────────────────────────────────


class AuditProjectCiParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    recent_pipelines: int = Field(20, ge=1, le=100, description="How many of the most recent pipelines to include in the audit.")


class AuditRow(sdl.Entity):
    id: str = ""
    title: str = ""
    check: str = ""
    status: str = ""
    detail: str = ""


class AuditReport(sdl.Entity):
    id: str = ""
    title: str = ""
    project_id: str = ""
    generated_at: str = ""
    rows: list[AuditRow] = []
    success_rate_pct: float = 0.0
    failing_pipelines: int = 0
    stale_variables_flagged: bool = False
    offline_runners: int = 0


class GetFailedJobsSummaryParams(BaseModel):
    connection_id: str = Field("", description="ID of the GitLab connection to use.")
    project_id: str = Field("", description="Project ID or URL-encoded path.")
    recent_pipelines: int = Field(10, ge=1, le=50, description="How many of the most recent pipelines to scan for failed jobs.")


class FailedJobSummaryRow(sdl.Entity):
    id: str = ""
    title: str = ""
    pipeline_id: int = 0
    job_id: int = 0
    job_name: str = ""
    stage: str = ""
    failure_reason: str = ""
    web_url: str = ""


class FailedJobsSummary(sdl.Entity):
    id: str = ""
    title: str = ""
    rows: list[FailedJobSummaryRow] = []
    total_failed: int = 0
