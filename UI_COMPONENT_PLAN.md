# GitLab CI/CD Connector — UI component plan

Источники: `Docs/session-notes/UI_COMPONENT_VOCABULARY.md`, `UI_INTERFACE_STANDARD.md`,
`concepts/panels.md`. Основано на функционале `gitlab-cicd-connector`.

## 1. Компоненты

| Экран | Примитивы | Почему именно эти |
|---|---|---|
| Sidebar (left) | `ui.Column`(align="start") + `ui.Text`(instance) + `ui.Divider` + navigation `ui.ListItem`(Projects/Runners/Pipelines) + `ui.Button`("App settings") | Без карточек по стандарту. |
| Pipeline List (center, `center_overlay=True`) | `ui.Stats`(Success rate/Running/Failed today) + `ui.Select`(param_name="ref_filter", placeholder="Ветка") + `ui.DataTable`(pipeline#, ref, status Badge success/failed/running, duration, triggered_by; sortable) | `DataTable` — стандартный способ отслеживать историю прогонов пайплайна. |
| Pipeline Detail | Back-button + `ui.KeyValue`(ref/commit/duration/triggered_by) + `ui.Timeline`(jobs: stage→job→status, в порядке выполнения) + `ui.Row`(Button "Retry", "Cancel") | `Timeline` отражает последовательность стадий/джобов пайплайна. |
| Job Log Viewer | `ui.Code`(language="text", content=job trace, readonly) | `Code` — единственный примитив с моноширинным отображением/подсветкой, подходит для консольного вывода джобы. |
| CI Lint Result | `ui.TextArea`(param_name="yaml_content", placeholder="Вставьте .gitlab-ci.yml...") + `ui.Alert`(variant="success"/"error" — результат валидации) | `Alert` — прямое попадание для показа результата валидации (ок/ошибка с описанием). |
| Variables Manager | `ui.DataTable`(key, protected Badge, masked Badge, environment_scope) + `ui.Button`("Добавить переменную") + `ui.Dialog`(форма: `ui.Input`(key) + `ui.Password`(value) + `ui.Toggle`(protected) + `ui.Toggle`(masked)) | `Password` — обязателен для значения переменной (может быть секретом), не `Input`. |
| Runner List | `ui.DataTable`(description, status Badge online/offline, tags via `ui.TagInput` read-only, ip_address) | Обзор доступных self-hosted раннеров. |
| Schedule List | `ui.List`(schedules: description, cron, next run) + `ui.Button`("Запустить сейчас") | Список запланированных пайплайнов с ручным триггером. |
| App Settings | `ui.Accordion`([Connections+Disconnect, Group Variables, Webhooks CRUD]) | Централизованные настройки по стандарту. |

## 2. User flow (валидно по panel lifecycle)

1. **SESSION INIT** → `__panel__gitlab_sidebar` рендерит instance + разделы;
   `auto_action` открывает Pipeline List для последнего активного проекта, если
   `not active_view`.
2. Pipeline List: Select ветки → DataTable → клик на строку →
   `ui.Call("__panel__gitlab_center", pipeline_id=...)` → Pipeline Detail.
3. Pipeline Detail: Timeline джобов → клик на джобу → `ui.Call(job_id=...)` →
   Job Log Viewer (Code блок с трейсом).
4. Pipeline Detail: Button "Retry" → `retry_pipeline` → `refresh_panels=["gitlab_center"]`.
   Button "Cancel" → без Dialog (не деструктивно, пайплайн можно перезапустить).
5. Раздел "Variables" → Variables Manager → Button "Добавить" → Dialog с формой
   (Input key + Password value + два Toggle) → `create_project_variable` →
   `refresh_panels=["gitlab_variables"]`.
6. "App settings" → отдельный center overlay с Accordion-секциями.

## 3. Конкретные экраны (screens)

### Screen: Pipeline List (`gitlab_center`, default)
- Stats row: Success rate / Running / Failed today.
- Select (ветка) сверху таблицы.
- DataTable: pipeline#, ref, status Badge, duration, triggered_by — row-click →
  Pipeline Detail.

### Screen: Pipeline Detail (`gitlab_center` + `pipeline_id`)
- Back-button "← К пайплайнам".
- KeyValue: ref, commit, duration, triggered_by.
- Timeline: stage→job→status.
- Row кнопок: Retry, Cancel.

### Screen: Job Log Viewer (`gitlab_center` + `pipeline_id` + `job_id`)
- Back-button "← К пайплайну".
- Code (readonly): полный трейс job'ы.

### Screen: Variables Manager (`gitlab_variables` + `project_id`)
- DataTable: key, protected Badge, masked Badge, scope.
- Button "Добавить переменную" → Dialog с формой.

### Screen: App settings (`gitlab_settings`)
- Accordion "Подключение": instance, Disconnect (Dialog-подтверждение).
- Accordion "Group Variables": DataTable.
- Accordion "Webhooks": List + Button "Добавить".
