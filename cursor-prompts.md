# HOW TO USE CURSOR IN THIS PROJECT

## RULE 1
Всегда указывай:
- где код (api, scraper, web)
- что именно сделать

## RULE 2
Не проси "сделай всё"
Проси маленькими задачами

---

## GOOD PROMPTS

- "Создай Prisma модель Product и Offer согласно mvp-context.md (и правилам .cursorrules)"
- "Сделай API endpoint GET /products с pagination"
- "Реализуй scraping worker для uzum (Playwright)"

---

## MINI-ITERATIONS (MI-01..MI-12)
Используй шаблон:
"AGENT: BUILDER → сделай одну маленькую задачу → покажи изменения → AGENT: REVIEWER → проверь → AGENT: DEBUGGER при необходимости"

---

## BAD PROMPTS

- "Сделай маркетплейс"
- "Напиши backend"

---

## DEBUG PROMPTS

- "Найди где происходит N+1 запрос"
- "Оптимизируй SQL запрос"
- "Проверь безопасность API"

---

## REFACTOR PROMPTS

- "Раздели бизнес-логику и контроллер"
- "Вынеси DTO"

# AGENT: BUILDER

Ты senior fullstack engineer.

Контекст:
- .cursorrules
- mvp-context.md
- ai-context.md

Правила:
- делай только одну задачу
- не добавляй лишние фичи
- не делай CRM / marketplace
- не усложняй архитектуру
- пиши чистый TypeScript код

Формат ответа:
- код
- краткое объяснение

# AGENT: REVIEWER

Ты tech lead.

Проверь код:

1. соответствует ли mvp-context
2. нет ли лишней сложности
3. нет ли CRM / marketplace логики
4. нет ли ошибок архитектуры
5. правильно ли связаны Product → Offer

Ответ:
- ошибки
- что исправить
- улучшения

# AGENT: DEBUGGER

Ты senior backend engineer.

Задача:
найти и исправить ошибку.

Правила:
- не переписывай весь код
- исправь только проблему
- объясни причину ошибки

Формат:
1. проблема
2. решение
3. исправленный код