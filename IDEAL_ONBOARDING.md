# GitLab CI/CD Connector — идеальный первый запуск

Источник: `ONBOARDING_FIRST_LAUNCH_STANDARD.md`. Целевой пользователь: DevOps-инженер/
тимлид разработки на GitLab (SaaS или self-managed).

## 1. Credential type
Self-hosted-capable: base_url (с явной SSRF-защитой, по POST_CONNECT уже реализовано)
+ access_token.

## 2. Идеальный флоу
1. **Первое открытие** — `Empty` с выбором SaaS/self-managed ДО ввода токена (влияет
   на то, что показывать в placeholder base_url — gitlab.com по умолчанию уже
   предзаполнен, это правильно) + ссылка на "User Settings > Access Tokens" для
   генерации PAT с нужным scope (api, read_repository).
2. **Форма** — base_url (уже с дефолтом https://gitlab.com) + access_token
   (password-type).
3. **После успеха** — `audit_pipeline_health` сразу: упавшие пайплайны + самое узкое
   место (самая долгая/часто падающая джоба) — actionable для тимлида с первого взгляда.
4. **Self-managed SSRF safety UX** — идеально: если base_url отклонён по SSRF-защите
   (внутренний IP/localhost) — конкретное объяснение ПОЧЕМУ отклонён (безопасность, не
   баг), с чёткой инструкцией что нужен публично доступный адрес.
5. **Ошибка "insufficient scope"** — если токен создан без `api` scope — конкретное
   объяснение, какой scope нужен добавить.

## 3. Разница с реализацией сейчас
См. `UI_COMPONENT_PLAN.md` §0.
