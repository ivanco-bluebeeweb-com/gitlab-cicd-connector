# GitLab CI/CD Connector — Connector Discovery

**Дата discovery:** 2026-08-21
**Статус:** Ярусы 1-3 пройдены (свежее чтение официальной документации
docs.gitlab.com, 2026-08-21). Задача #2212 явно заявляла "делай это
приложение в максимальной комплектации с максимальным функционалом" —
это ЯВНОЕ заранее заявленное решение объёма ("максимум"), поэтому §7
(решение по объёму) не требует повторного вопроса Владу — как и в
Power Automate/Automation Anywhere/UiPath/Blue Prism коннекторах, где
объём был явно указан в исходной задаче.

---

## 1. Целевой сервис и источники

GitLab REST API (`docs.gitlab.com/api/rest/`) — **единая** поверхность,
в отличие от MuleSoft/Tray (несколько разрозненных API-семейств).
Base URL = `<instance>/api/v4`, работает одинаково и для gitlab.com SaaS,
и для self-managed/self-hosted инстансов — значит `base_url` обязан быть
параметризуемым полем подключения, а не захардкожен на `gitlab.com`
(тот же паттерн, что n8n/UiPath/MuleSoft/Automation Anywhere/Blue Prism —
у всех есть self-hosted вариант).

Источники (прочитаны 2026-08-21):
- `docs.gitlab.com/api/rest/` — общая механика REST API (пагинация, auth, форматы)
- `docs.gitlab.com/api/pipelines/` — Pipelines API (полный CRUD над пайплайнами)
- `docs.gitlab.com/api/jobs/` — Jobs API (список/детали/retry/cancel/play/erase)
- `docs.gitlab.com/api/runners/` — Runners API (управление раннерами, регистрация)
- `docs.gitlab.com/api/project_level_variables/` — Project-level CI/CD Variables API
- `docs.gitlab.com/api/group_level_variables/` — Group-level CI/CD Variables API
- `docs.gitlab.com/ci/triggers/` — Trigger pipelines with the API (Pipeline Trigger Tokens)
- `docs.gitlab.com/api/pipeline_schedules/` — Pipeline Schedules API (cron-задачи)
- `docs.gitlab.com/api/lint/` — CI Lint API (валидация `.gitlab-ci.yml`)
- `docs.gitlab.com/api/job_artifacts/` — Job Artifacts API (скачивание/удаление артефактов)
- `docs.gitlab.com/api/environments/` — Environments API
- `docs.gitlab.com/api/deployments/` — Deployments API
- `docs.gitlab.com/security/tokens/access_token_scopes/`, `docs.gitlab.com/user/profile/personal_access_tokens/` — модель токенов и их scope

## 2. Карта возможностей (направление на каждую)

| Домен API | Возможность | Ingress/Egress/Both | Комментарий |
|---|---|---|---|
| **Pipelines** | List/get project pipelines, фильтры (status/ref/sha/scope/source) | Ingress | Основной "что сейчас происходит" экран, аналог "сценариев"/"workflows" у других коннекторов |
| **Pipelines** | Create/retry/cancel/delete pipeline | Both/Egress | Прямое управление пайплайном |
| **Pipelines** | Pipeline variables (list variables, использованные конкретным запуском) | Ingress | Диагностика конкретного запуска |
| **Pipelines** | Pipeline test report / test report summary | Ingress | JUnit-агрегация по пайплайну — полезно как diagnostics |
| **Jobs** | List all jobs (project-wide и per-pipeline), get job | Ingress | Детальный уровень ниже pipeline |
| **Jobs** | Retry/cancel/play (manual job)/erase job | Egress | Основные операционные действия над джобой |
| **Jobs** | Job trace (лог одной джобы, потоковый или полный) | Ingress | Диагностика — критично важная функция (аналог CloudHub `get_application_logs`) |
| **Jobs** | Job artifacts (download/keep/delete) | Both | Скачивание/управление собранными артефактами |
| **Runners** | List all/available runners (instance/group/project scope) | Ingress | Реестр раннеров — кто исполняет джобы |
| **Runners** | Get/update/delete runner, pause (`paused=true`)/resume | Both | Управление конкретным раннером |
| **Runners** | Register new runner (`POST /user/runners`), reset auth token | Egress | Регистрация нового раннера — инфраструктурная операция |
| **Runners** | Runner's jobs (`GET /runners/:id/jobs`) | Ingress | История джобов конкретного раннера |
| **CI/CD Variables** | List/get/create/update/delete project-level variables | Both | Управление секретами/конфигом пайплайна на уровне проекта |
| **CI/CD Variables** | List/get/create/update/delete group-level variables | Both | То же на уровне группы (наследуется дочерними проектами) |
| **Pipeline Triggers** | List/create/update/delete trigger tokens | Both | Управление токенами, которыми ВНЕШНИЕ системы запускают пайплайны (например миграция с Jenkins) |
| **Pipeline Triggers** | Trigger a pipeline run via trigger token (`POST /projects/:id/trigger/pipeline`) | Egress | Реальный запуск пайплайна извне — использует `trigger_token`, НЕ PAT |
| **Pipeline Schedules** | List/get/create/update/delete/take-ownership schedule | Both | Управление cron-расписаниями пайплайнов |
| **Pipeline Schedules** | Play a scheduled pipeline now, manage schedule variables | Egress | Принудительный запуск расписания + его переменные |
| **CI Lint** | Validate `.gitlab-ci.yml` content (project-aware and standalone) | Ingress | Value-add диагностика ДО коммита — уникальная и ценная функция, которой нет у большинства других CI-платформ в портфеле |
| **Environments** | List/get/create/update/delete environment, stop environment/stale environments | Both | Управление deployment environments (staging/production и т.п.) |
| **Deployments** | List/get/create/update/delete deployment, approve/reject deployment | Both | Записи о конкретных деплойментах, approval gates |
| **Group/Project registry** | List projects/groups accessible to the token (для выбора project_id) | Ingress | Нужно как навигационная функция — без неё пользователь не узнает валидный `project_id` |

## 3. Классификация по типу функционала (Шаг 1 стандарта)

- **Ingress (сильный):** список/детали пайплайнов и джобов, job trace (логи),
  список раннеров, список переменных, список triggers/schedules,
  environments/deployments, CI Lint (валидация конфига) — то, что коннектор
  должен уметь *показывать* в первую очередь.
- **Egress (сильный):** retry/cancel/play/erase job, create/cancel/retry/delete
  pipeline, register/pause/delete runner, create/update/delete variable,
  создать/удалить trigger token, запустить пайплайн через trigger, run
  schedule now, approve/reject deployment, stop environment.
- **Both:** переменные и schedules (список = чтение, CRUD = запись),
  runners (список = чтение, pause/delete = запись).

## 4. Ярус 1 — Ключевые функции (P0-кандидаты)

Ближайший операционный аналог "список сценариев + запустить/остановить/лог",
по образцу уже существующих коннекторов (MuleSoft/Automation Anywhere/UiPath):

1. `connect_gitlab` / `disconnect_gitlab` — PAT + base_url (SaaS или self-hosted)
2. `list_projects` — доступные проекты (нужно для указания `project_id` во всех остальных вызовах)
3. `list_pipelines` — список пайплайнов проекта со статусом/веткой/датой
4. `get_pipeline` — детали одного пайплайна
5. `retry_pipeline` / `cancel_pipeline`
6. `list_jobs` — список джобов (проекта или конкретного пайплайна)
7. `get_job`
8. `retry_job` / `cancel_job` / `play_job` (manual job)
9. `get_job_trace` — лог джобы (аналог CloudHub `get_application_logs`)
10. `list_runners` — раннеры, доступные проекту/группе
11. `list_project_variables` — CI/CD переменные проекта

## 5. Ярус 2 — Полное покрытие

| Возможность | Статус | Причина/триггер |
|---|---|---|
| Create/delete pipeline | included | Прямое продолжение Ярус 1 lifecycle |
| Erase job (стереть артефакты+лог) | included | Естественное расширение Job lifecycle |
| Job artifacts: download/keep/delete | included | Частый operational use-case ("скачай сборку") |
| Get/update/delete runner, pause/resume | included | Полное управление реестром раннеров |
| Register new runner (`POST /user/runners`) | included | Явно запрошен максимум — покрывает полный runner lifecycle |
| Project variables: create/update/delete | included | Полный CRUD над конфигурацией пайплайна |
| Group variables: list/get/create/update/delete | included | Те же операции на уровне группы — прямое расширение того же домена |
| Pipeline Trigger tokens: list/create/update/delete | included | Управление внешними интеграциями (миграция с Jenkins/CircleCI, multi-project triggers) |
| Trigger a pipeline via trigger token | included | Egress-функция, напрямую относящаяся к "CI/CD", максимум обязывает включить |
| Pipeline Schedules: list/get/create/update/delete/run now | included | Явный operational use-case ("включи/выключи/запусти джобу по расписанию") — прямая аналогия CloudHub schedules |
| CI Lint (validate `.gitlab-ci.yml`) | included | Уникальная value-add диагностика, специфичная для GitLab, максимум явно требует |
| Environments: list/get/create/update/delete/stop | included | Полное покрытие deployment-инфраструктуры уровня проекта |
| Deployments: list/get/create/update/delete/approve/reject | included | Полное покрытие deployment-записей и approval workflow |
| Pipeline test report summary | included | Value-add диагностика (агрегация JUnit) — прямое расширение уже нужного HTTP-клиента |
| Access token scopes / fine-grained PAT management | not applicable | Управление СОБСТВЕННЫМИ токенами пользователя в GitLab UI — не относится к CI/CD-операциям через API; вне охвата даже при "максимуме" (аналог: MuleSoft Access Management users/roles тоже был вне охвата) |
| Repository/merge request/issue management (обычный Git-функционал GitLab) | not applicable | Это домен полноценного "GitHub/GitLab connector" (репозитории, MR, issues) — данный коннектор целенаправленно фокусируется на CI/CD (задача #2212 названа "GitLab CI/CD"), не на repository management |

## 6. Ярус 3 — Функции на нашей стороне (value-add)

- **`bulk_retry_jobs`** / **`bulk_cancel_jobs`** — retry/cancel нескольких
  джобов одним вызовом (Jobs API отдаёт только по одной джобе за раз)
- **`bulk_stop_pipelines`** (cancel несколько pipeline id разом)
- **`audit_project_pipelines`** — агрегирующий отчёт по проекту: последние
  N пайплайнов + их статус + failed job count + средняя длительность одним
  вызовом, вместо ручного обхода `list_pipelines`+`list_jobs` по каждому
  (аналог `audit_cloudhub_environment` у MuleSoft)
- **`get_flaky_jobs`** — находит джобы с чередующимся success/failed на
  одной и той же ветке за последние N пайплайнов (сервис не даёт готового
  "какие джобы у меня нестабильны" отчёта)
- **`get_stale_runners`** — раннеры, которые online, но не брали джобы
  дольше N дней, или offline дольше N дней — сервис отдаёт `contacted_at`,
  но не готовый "who is stale" отчёт

## 7. Решение по объёму этого захода

Задача #2212 (и прямой запрос пользователя "делай это приложение в
максимальной комплектации с максимальным функционалом") — это явное
заранее заявленное "делаем максимум". Берём **Ярус 1 + Ярус 2 + Ярус 3**
целиком, без вопроса, по прецеденту Power Automate/MuleSoft/Automation
Anywhere/UiPath/Blue Prism, где аналогичная явная формулировка в задаче
уже освобождала от обязательного вопроса в §7 (это ИСКЛЮЧЕНИЕ Шага 5
стандарта discovery, а не игнорирование правила).

**Явный вопрос (не про объём, а про архитектуру), требующий подтверждения:**
Repository-функционал (репозитории, merge requests, issues, wiki) сознательно
исключён из охвата этого коннектора — название задачи и текущий запрос явно
про "CI/CD". Если позже понадобится полноценный GitLab (не только CI/CD) —
это отдельный заход/расширение, не тихое добавление сюда.
