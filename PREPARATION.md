# GitLab CI/CD Connector — Preparation

**Статус:** Фаза 1 (Discovery + архитектурные решения) завершена. Объём
релиза заявлен пользователем явно в исходном запросе задачи #2212 —
"делай это приложение в максимальной комплектации с максимальным
функционалом" — трактуется как "максимум" (Ярус 1+2+3), по прецеденту
Power Automate/MuleSoft/Automation Anywhere/UiPath/Blue Prism, где такая
же явная формулировка в задаче уже освобождала от повторного вопроса.

**Владелец продукта:** vlad@bluebeeweb.com
**Дата подготовки:** 2026-08-21, v0.1
**Vikunja task:** #2212 (BBW Imperal Apps), [App Development].

**Почему сейчас:** GitLab — один из двух доминирующих DevOps-платформ,
со встроенным CI/CD как ключевым дифференциатором (в отличие от GitHub,
где CI/CD — отдельный продукт Actions, и уже есть сторонний GitHub
Connector в портфеле). Self-hosted вариант делает GitLab особенно
распространённым в regulated/enterprise-командах — родственная аудитория
UiPath/Blue Prism/Automation Anywhere/MuleSoft.

---

## 1. Паспорт приложения

**Название в Marketplace (display_name): «GitLab CI/CD»**. Внутренний
app_id/папка: `gitlab-cicd-connector`.

**GitLab CI/CD Connector** — коннектор к GitLab REST API (`/api/v4`),
сфокусированный на CI/CD-домене: pipelines, jobs, runners, CI/CD
variables (project + group level), pipeline trigger tokens, pipeline
schedules, CI Lint, environments, deployments. BYOK: пользователь
подключает свой собственный Personal Access Token (PAT) к своему
собственному GitLab-инстансу (gitlab.com SaaS ИЛИ self-managed). Imperal
ничего не хостит и не проксирует помимо самого запроса.

**Сознательно вне охвата:** repository-функционал (файлы/коммиты/ветки),
merge requests, issues, wiki, project/group administration (участники,
права доступа), Container/Package Registry. Это домен полноценного
"репозиторного" GitLab-коннектора — отдельный будущий заход, не тихое
расширение этого. Название задачи и запрос явно про CI/CD.

---

## 2. Ключевые факты о GitLab REST API (см. `CONNECTOR_DISCOVERY.md`)

### 2.1 Единая REST-поверхность, параметризуемый base_url

В отличие от MuleSoft/Tray (несколько разрозненных API-семейств), GitLab
имеет **один** REST API (`docs.gitlab.com/api/rest/`) под базовым путём
`<instance>/api/v4`. Инстанс может быть `gitlab.com` (SaaS) или
self-managed доменом клиента — значит `base_url` обязан быть полем
подключения, не константой (тот же паттерн, что n8n/UiPath/MuleSoft/
Automation Anywhere/Blue Prism).

### 2.2 Auth — Personal Access Token, заголовок `PRIVATE-TOKEN`

Подтверждено `docs.gitlab.com/api/rest/authentication/`,
`docs.gitlab.com/user/profile/personal_access_tokens/`: GitLab API
принимает PAT через HTTP-заголовок **`PRIVATE-TOKEN: <token>`** — НЕ
`Authorization: Bearer <token>` (важное отличие от большинства уже
сделанных коннекторов вроде n8n/Workato). Скоупы: `api` (полный доступ)
или `read_api` (только чтение) — пользователю нужен `api` для write/
destructive функций этого коннектора. Есть также Project/Group Access
Tokens (тот же заголовок, тот же механизм, просто иной уровень выдачи) и
новые Fine-grained PATs (2026) — не требуют отдельной архитектуры,
принимаются идентично.

Нет курицы-и-яйца: PAT создаётся немедленно самим пользователем в
`User Settings > Access Tokens`, без внешнего ревью.

### 2.3 Адресация — project_id как id ИЛИ URL-encoded path

GitLab API принимает `:id` как числовой ID проекта ИЛИ URL-encoded полный
путь (`group%2Fsubgroup%2Fproject`) — оба равнозначны везде, где встречается
`:id`. Каждый вызов коннектора принимает `project_id: str` (принимает и то,
и другое, кодирование делает клиент), а не хранит "текущий проект" на
уровне подключения — один GitLab-аккаунт управляет множеством проектов,
поэтому project_id передаётся explicit на каждый вызов (аналог
MuleSoft's `domain` на каждый вызов, а не в connection record).

### 2.4 Pipeline Trigger Token — ОТДЕЛЬНЫЙ токен, не PAT

`docs.gitlab.com/ci/triggers/`: чтобы вызвать
`POST /projects/:id/trigger/pipeline`, нужен отдельный `trigger_token`
(создаётся через Pipeline Trigger Tokens API/UI), НЕ тот же PAT, что
аутентифицирует остальные вызовы. `trigger_pipeline` в этом коннекторе
принимает `trigger_token` как явный параметр вызова (не секрет
подключения) — он специфичен для конкретного проекта/интеграции, не для
всего аккаунта.

### 2.5 Job Trace — потоковый текстовый лог, не JSON

`GET /projects/:id/jobs/:job_id/trace` возвращает **сырой текст** (не
JSON) — лог джобы целиком. Клиент должен читать это как текст, не
пытаться парсить как JSON.

---

## 3. Решённые архитектурные вопросы

| # | Вопрос | Решение | Обоснование |
|---|---|---|---|
| 1 | BYOK или центральный брокер? | **BYOK** | Пользователь управляет своим GitLab-инстансом/аккаунтом; Imperal не хостит и не проксирует. |
| 2 | Auth механизм? | **Personal Access Token**, заголовок `PRIVATE-TOKEN` | Официальный, немедленно доступный механизм — без внешнего ревью. |
| 3 | Сколько секретов? | **Три + label**: `base_url`, `private_token`, опционально `label` | `base_url` обязателен (SaaS ИЛИ self-managed), `private_token` — единственный креденшел. |
| 4 | Как адресовать проект? | **`project_id` explicit на каждый вызов** (numeric ID или path), не в connection record | Один аккаунт управляет множеством проектов — тот же принцип, что `domain` у MuleSoft. |
| 5 | Что входит в охват? | **Pipelines, Jobs, Runners, CI/CD Variables (project+group), Pipeline Triggers, Pipeline Schedules, CI Lint, Environments, Deployments** | Прямой периметр "CI/CD" из названия задачи. |
| 6 | Что НЕ входит в охват? | Repository/MR/Issues/Wiki/project admin/Registry | Отдельный, более широкий "GitLab connector" — не смешивать с CI/CD-фокусом этой задачи. |
| 7 | Объём релиза? | **«Максимум» = Ярус 1+2+3** | Явная формулировка пользователя в исходном запросе задачи #2212. |
| 8 | Pipeline Trigger Token — секрет подключения или параметр вызова? | **Параметр вызова** `trigger_pipeline`, не секрет аккаунта | Специфичен для проекта/интеграции, не для всего GitLab-аккаунта; хранение как секрет создало бы путаницу с PAT. |

---

## 4. Функциональный охват («максимум» = Ярус 1+2+3)

### Ярус 1 (P0 — ключевые функции)
- `connect_gitlab` (base_url, private_token, label) — проверка + сохранение
- `disconnect_gitlab`
- `list_connections`
- `list_pipelines`, `get_pipeline`
- `retry_pipeline`, `cancel_pipeline`
- `list_jobs`, `list_pipeline_jobs`, `get_job`
- `get_job_trace`
- `list_runners`, `get_runner`

### Ярус 2 (полное покрытие CI/CD-домена)
- `create_pipeline`, `delete_pipeline` (destructive)
- `get_pipeline_variables`, `get_pipeline_test_report`
- `retry_job`, `cancel_job`, `play_job`, `erase_job` (destructive)
- `get_job_artifacts_download_url`, `delete_job_artifacts` (destructive)
- `list_project_runners`, `update_runner`, `pause_runner`, `resume_runner`,
  `delete_runner` (destructive), `list_runner_jobs`
- `list_project_variables`, `get_project_variable`,
  `create_project_variable`, `update_project_variable`,
  `delete_project_variable`
- `list_group_variables`, `create_group_variable`,
  `update_group_variable`, `delete_group_variable`
- `list_pipeline_triggers`, `create_pipeline_trigger`,
  `update_pipeline_trigger`, `delete_pipeline_trigger`, `trigger_pipeline`
- `list_pipeline_schedules`, `get_pipeline_schedule`,
  `create_pipeline_schedule`, `update_pipeline_schedule`,
  `delete_pipeline_schedule` (destructive), `run_pipeline_schedule`
- `lint_ci_config`
- `list_environments`, `get_environment`, `create_environment`,
  `stop_environment`, `delete_environment` (destructive)
- `list_deployments`, `get_deployment`

### Ярус 3 (наш value-add)
- `bulk_retry_jobs`, `bulk_cancel_jobs` (explicit job id list, 1-100)
- `bulk_cancel_pipelines` (explicit pipeline id list, 1-100)
- `audit_project_pipelines` — агрегирующий отчёт: последние N пайплайнов
  + статус + failed job count + средняя длительность
- `get_flaky_jobs` — джобы с чередующимся success/failed на одной ветке
  за последние N пайплайнов
- `get_stale_runners` — раннеры online, но без активности дольше N дней

Итого: **~63 функции** — сопоставимо по масштабу с UiPath/Blue Prism/
Automation Anywhere ("максимум" для этой линейки коннекторов).

---

## 5. Открытые вопросы для Влада

Нет открытых вопросов по объёму — заявлено явно в исходном запросе.
Один явно зафиксированный архитектурный выбор (repository/MR/issues вне
охвата) — задокументирован выше, не тихое решение.

---

## 6. Журнал проверки дублей

`search_marketplace` по «GitLab» — дублей не найдено в существующем
портфеле Imperal на момент 2026-08-21 (есть сторонний "GitHub Connector"
от другого разработчика — другой сервис, не конфликт).
