"""Panel UI -- connections list/connect form for GitLab CI/CD Connector.

SIDEBAR CONTENT -- NO CARDS ANYWHERE, per ~/UI_INTERFACE_STANDARD.md's
"left sidebar, no decorated cards" rule (same convention as MuleSoft
Connector's / n8n Connector's panels.py).

Every section (connections, connect form) is a plain ui.Stack, content
stacked vertically and left-aligned, sections separated by ui.Divider() --
no Card border/background/shadow anywhere in this slot. Disconnect lives
only in the "App settings" screen (panels_settings.py). The one secondary
"App settings" button is always the LAST element at the bottom of the
sidebar.

WHY A FULL FORM (base_url + token + label), NOT A SINGLE TOKEN.

GitLab's REST API is served at `<instance>/api/v4/...` for both gitlab.com
SaaS and any self-managed instance -- there is no fixed host to assume, so
the form asks for the base URL explicitly (defaulting to
https://gitlab.com for the common case) alongside the Personal Access
Token, plus an optional friendly label -- same shape as app.py's module
docstring reasoning.

Per Vlad's standing rule: every input carries its own label (not just a
placeholder), placeholders are contextually specific, and the form
container is stretched to the full width of the left sidebar with its
contents stretched to fill it.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
import handlers as h


def _settings_button() -> ui.UINode:
    """The one required secondary entry point into the settings screen --
    always the last element at the bottom of the sidebar."""
    return ui.Button(
        "App settings", variant="secondary", size="sm", full_width=True,
        icon="settings", on_click=ui.Call("__panel__gitlab_settings"),
    )


def _connection_row(c: dict) -> ui.UINode:
    return ui.Stack(direction="v", gap=1, children=[
        ui.Text(c.get("title") or c.get("base_url", ""), variant="body"),
        ui.Text(c.get("detail", ""), variant="caption"),
    ])


def _connections_section(connections: list[dict]) -> ui.UINode:
    if not connections:
        return ui.Text("No GitLab instances connected yet.", variant="caption")
    children: list[ui.UINode] = []
    for i, c in enumerate(connections):
        if i > 0:
            children.append(ui.Divider())
        children.append(_connection_row(c))
    return ui.Stack(direction="v", gap=2, children=children)


def _connect_section() -> ui.UINode:
    """Plain content, no Card wrapper. Stretched full-width per
    UI_INTERFACE_STANDARD.md (2026-08-20). No intro heading/description
    text here -- the Personal Access Token walkthrough lives ONLY in
    gitlab_connect_help's modal (button below opens it); repeating it
    here would duplicate that instruction."""
    return ui.Stack(direction="v", gap=3, align="stretch", children=[
        ui.Button("How do I set this up?", variant="ghost", size="sm",
                  icon="HelpCircle",
                  on_click=ui.Call("__panel__gitlab_connect_help")),
        ui.Form(
            action="connect_gitlab",
            submit_label="Verify and connect",
            children=[
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Instance base URL", variant="caption"),
                    ui.Input(param_name="base_url",
                             placeholder="https://gitlab.com or https://gitlab.example.com",
                             value="https://gitlab.com"),
                ]),
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Personal Access Token", variant="caption"),
                    ui.Password(param_name="access_token",
                                 placeholder="glpat-xxxxxxxxxxxxxxxxxxxx"),
                ]),
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Label (optional)", variant="caption"),
                    ui.Input(param_name="label", placeholder="e.g. Production instance"),
                ]),
            ],
        ),
    ])


@ext.panel("gitlab_connect", slot="left", title="GitLab CI/CD", icon="🦊",
           default_width=320, min_width=260, max_width=420)
async def gitlab_connect_panel(ctx, **kwargs) -> object:
    connections = await h._load_connections(ctx)
    connected = bool(connections)

    header = ui.Header(text="GitLab CI/CD", level=2,
                        subtitle="Manage your GitLab pipelines, jobs, runners and more from Imperal")

    if not connected:
        return ui.Stack(direction="v", gap=4, align="stretch", children=[
            header,
            _connect_section(),
            ui.Divider(),
            _settings_button(),
        ])

    return ui.Stack(direction="v", gap=4, align="stretch", children=[
        header,
        ui.Text("Connected instances", variant="subtitle"),
        _connections_section(connections),
        ui.Divider(),
        ui.Button("Open a project", variant="primary", size="sm", full_width=True,
                  icon="GitBranch", on_click=ui.Call("__panel__gitlab_center")),
        ui.Divider(),
        _connect_section(),
        ui.Divider(),
        _settings_button(),
    ])


@ext.panel("gitlab_connect_help", slot="center",
           title="How to connect GitLab", center_overlay=True)
async def gitlab_connect_help(ctx, **kwargs) -> object:
    content = ui.Stack(direction="v", gap=3, children=[
        ui.Text("1. Sign in to your GitLab instance (gitlab.com or your own self-managed instance)."),
        ui.Text("2. Open User Settings > Access Tokens."),
        ui.Text("3. Create a new Personal Access Token with the 'api' scope (or 'read_api' if you only want read access)."),
        ui.Text("4. Copy the token -- GitLab shows it only once."),
        ui.Text("5. Paste your instance's base URL (e.g. https://gitlab.com) and the token into the form, then Verify and connect."),
        ui.Divider(),
        ui.Alert(
            title="CI/CD only",
            message=(
                "This connects pipelines, jobs, runners, CI/CD variables, "
                "trigger tokens, schedules, CI Lint, artifacts, environments "
                "and deployments. Repository files, merge requests, issues "
                "and project administration are out of scope here."
            ),
            type="warning",
        ),
        ui.Divider(),
        ui.Link(
            label="Open GitLab's official Personal Access Tokens guide",
            href="https://docs.gitlab.com/user/profile/personal_access_tokens/",
        ),
    ])
    return ui.Dialog(
        title="How to connect GitLab",
        content=content,
        confirm_label="",
        cancel_label="Close",
    )


@ext.panel("gitlab_center", slot="center", title="GitLab CI/CD", icon="🦊", center_overlay=True)
async def gitlab_center_panel(ctx, project_id: str = "", **kwargs) -> object:
    """Post-connect main screen: a project CI/CD health dashboard.

    GitLab CI/CD Connector has no fleet-wide "list every project" tool
    (every audit/pipeline/runner call is scoped to one project_id/path),
    so unlike Shopify/Stripe/HubSpot (which have a natural top-level
    list), this screen asks for a project path once via a plain Input +
    Button, then renders audit_project_ci's real health report for it."""
    connections = await h._load_connections(ctx)
    if not connections:
        return ui.Empty(
            message="Connect a GitLab instance from the sidebar to audit a project here.",
            icon="🦊",
        )
    if not project_id:
        return ui.Stack(direction="v", gap=3, align="stretch", children=[
            ui.Text("Open a project", variant="subtitle"),
            ui.Text(
                "Enter a GitLab project ID or URL-encoded path (e.g. "
                "\"mygroup/myproject\") to see its pipeline health here.",
                variant="caption",
            ),
            ui.Form(
                action="__panel__gitlab_center",
                submit_label="Open project",
                children=[
                    ui.Stack(direction="v", gap=1, align="stretch", children=[
                        ui.Text("Project ID or path", variant="caption"),
                        ui.Input(param_name="project_id", placeholder="mygroup/myproject"),
                    ]),
                ],
            ),
        ])
    return await _project_dashboard(ctx, project_id)


async def _project_dashboard(ctx, project_id: str) -> ui.UINode:
    from schemas import AuditProjectCiParams
    result = await h.audit_project_ci(ctx, AuditProjectCiParams(project_id=project_id))
    if not result.success or not result.data:
        return ui.Stack(direction="v", gap=3, align="stretch", children=[
            ui.Button("← Choose a different project", variant="ghost", size="sm",
                      on_click=ui.Call("__panel__gitlab_center")),
            ui.Alert(title="Could not load this project",
                     message=result.error or "Check the project ID/path and your token's access.",
                     type="error"),
        ])
    r = result.data
    rows_ui: list[ui.UINode] = []
    for row in r.rows:
        color = {"ok": "green", "warn": "yellow", "error": "red"}.get(row.status, "gray")
        rows_ui.append(ui.Stack(direction="h", gap=2, align="center", children=[
            ui.Badge(label=row.status.upper(), color=color),
            ui.Text(f"{row.check} — {row.detail}", variant="caption"),
        ]))
    return ui.Stack(direction="v", gap=3, align="stretch", children=[
        ui.Button("← Choose a different project", variant="ghost", size="sm",
                  on_click=ui.Call("__panel__gitlab_center")),
        ui.Stats(children=[
            ui.Stat(label="Success rate", value=f"{r.success_rate_pct:.0f}%"),
            ui.Stat(label="Failing pipelines", value=str(r.failing_pipelines)),
            ui.Stat(label="Offline runners", value=str(r.offline_runners)),
        ]),
        ui.Divider(),
        ui.Text(f"Project: {r.project_id}", variant="subtitle"),
        *(rows_ui if rows_ui else [ui.Text("No audit checks returned.", variant="caption")]),
    ])
