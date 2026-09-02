# Задача для Codex
## ReqPilot Engineering Workbench

**Версия:** 1.0  
**Дата:** 2 сентября 2026 года  
**Назначение:** небольшой рабочий инженерный web-workbench поверх StrictDoc и Eclipse Capella  
**Демонстрационная система:** мониторинг насосной станции  
**Интерфейс:** русский  
**Лицензия создаваемого кода:** MIT  

---

# 1. Идея продукта

Создать не новую RMS с собственной базой и форматом требований, а единый современный интерфейс над существующими инженерными инструментами:

- **StrictDoc** хранит, проверяет и экспортирует требования;
- **Eclipse Capella** хранит архитектурную модель;
- **ReqPilot** объединяет требования, архитектуру и тесты в одном web-интерфейсе.

Целевая цепочка трассировки:

```text
Потребность
  -> системное требование
  -> программное / интерфейсное / safety-требование
  -> функция Capella
  -> компонент Capella
  -> тест
```

Главная ценность ReqPilot: общий граф, матрицы покрытия, анализ влияния и удобная навигация. Он не должен повторять весь StrictDoc или превращаться в браузерный редактор Capella. Человечество уже написало достаточно универсальных платформ, которые умеют всё, кроме работы.

# 2. Цели пилота

Пилот должен подтвердить:

1. требования можно хранить в `.sdoc`, но показывать и редактировать через понятную форму;
2. модель Capella можно читать headless и отображать в web;
3. межсистемные связи можно хранить отдельно и проверять автоматически;
4. переименование элемента Capella не ломает связь по UUID;
5. удаление элемента обнаруживается как broken link;
6. общий граф и матрицы дают практическую пользу;
7. штатные экспорты StrictDoc остаются основным каналом публикации и ReqIF.

# 3. Источники истины

| Данные | Единственный источник истины |
|---|---|
| Текст и атрибуты требований | управляемые файлы StrictDoc `.sdoc` |
| Связи между требованиями | StrictDoc |
| Тестовые случаи | StrictDoc |
| Архитектурные элементы и отношения | Capella |
| Диаграммы | Capella `.aird` |
| Связи «требование ↔ архитектура» | `trace-links.yaml` |
| Кеши, JSON-индексы | производные данные |

Обязательные правила:

- P0 не записывает `.capella`, `.aird`, `.melodymodeller` и `.bridgetraces`;
- Capella в P0 читается только через `capellambse`;
- ReqIF формируется штатным StrictDoc, собственный конвертер запрещён;
- канонические требования нельзя хранить в `localStorage`, SQLite или JSON-кеше;
- ссылки на Capella используют UUID, а не имя;
- ссылки на требования используют MID и дублируют UID для удобства;
- mock/fixture не выдаётся за реальную Capella.

# 4. Целевые версии

| Компонент | Версия | Роль |
|---|---:|---|
| StrictDoc | `0.29.0` | требования, валидация, HTML/PDF/XLSX/JSON/ReqIF |
| capellambse | `0.8.0` | headless-чтение модели и SVG/PNG |
| Eclipse Capella | `7.1.0` | ручная архитектурная модель |
| Requirements Viewpoint | `0.14.0` | ручной импорт ReqIF |
| Python4Capella | `1.4.1`, P1 | контролируемое зеркалирование связей |

Backend: Python 3.12, FastAPI, Pydantic v2, Uvicorn, ruamel.yaml, filelock, lxml, pytest.  
Frontend: React, TypeScript, Vite, Tailwind, Radix/shadcn, TanStack Query/Table, React Flow, ELK/Dagre, Zod, React Hook Form, Vitest, Playwright.

Зависимости фиксируются в `uv.lock` и `package-lock.json`. Плавающие версии запрещены.

# 5. Объём

## P0, обязательно

- локальное однопользовательское приложение;
- CRUD управляемых требований;
- атомарная запись `.sdoc` и rollback;
- дерево, таблица, карточка, поиск и фильтры;
- чтение реальной Capella-модели;
- дерево архитектуры, свойства и SVG-диаграммы;
- `trace-links.yaml`;
- CRUD межсистемных связей;
- общий граф;
- четыре матрицы;
- impact analysis;
- broken-link detection;
- штатные экспорты StrictDoc;
- комбинированный автономный HTML;
- fixture mode только для тестов;
- автоматические тесты и CI;
- инструкция ручной проверки Capella.

## P1, только после полного P0

- очередь Python4Capella для зеркалирования links в Capella;
- Git diff/history;
- baseline;
- context diagrams;
- DOCX/M2Doc;
- тёмная тема;
- авторизация.

## Не входит

- собственная RMS-база;
- собственный ReqIF;
- редактирование архитектуры из браузера;
- многопользовательская работа;
- OSLC;
- Jira/DOORS/Polarion/Jama/Codebeamer;
- публичный облачный сервис.

---

# 6. Архитектура

```text
┌─────────────────────────────────────────────────────────────┐
│ ReqPilot Frontend                                           │
│ Обзор | Требования | Архитектура | Граф | Матрицы | Impact │
└────────────────────────────┬────────────────────────────────┘
                             │ REST / JSON / SVG
┌────────────────────────────▼────────────────────────────────┐
│ ReqPilot Backend / FastAPI                                  │
│ StrictDocAdapter | CapellaAdapter | TraceLinkRepository     │
│ GraphService | MatrixService | ImpactService | ExportService│
└──────────────┬──────────────────┬──────────────────┬─────────┘
               │                  │                  │
               ▼                  ▼                  ▼
     requirements/*.sdoc   trace-links.yaml    Capella model
       StrictDoc CLI          MID ↔ UUID       read-only P0
```

Собранный frontend должен отдаваться FastAPI. Сервер слушает только `127.0.0.1`. Произвольный CORS не включать.

# 7. Структура репозитория

```text
reqpilot-workbench/
├─ README.md
├─ CODEX_TASK_ReqPilot_Engineering_Workbench.md
├─ LICENSE
├─ pyproject.toml
├─ uv.lock
├─ project.yaml
├─ trace-links.yaml
├─ requirements/
│  ├─ strictdoc_config.py
│  ├─ grammar.sgra
│  ├─ 01_stakeholder.sdoc
│  ├─ 02_system.sdoc
│  ├─ 03_software_interface.sdoc
│  ├─ 04_safety.sdoc
│  ├─ 05_tests.sdoc
│  └─ assets/
├─ backend/
│  ├─ reqpilot/
│  │  ├─ main.py
│  │  ├─ api/
│  │  ├─ domain/
│  │  ├─ adapters/
│  │  │  ├─ strictdoc_adapter.py
│  │  │  ├─ strictdoc_writer.py
│  │  │  ├─ capella_adapter.py
│  │  │  ├─ trace_link_repository.py
│  │  │  └─ git_adapter.py
│  │  ├─ services/
│  │  └─ schemas/
│  └─ tests/
├─ frontend/
│  ├─ package.json
│  ├─ package-lock.json
│  ├─ src/
│  │  ├─ app/
│  │  ├─ api/
│  │  ├─ components/
│  │  └─ features/
│  │     ├─ dashboard/
│  │     ├─ requirements/
│  │     ├─ architecture/
│  │     ├─ traceability/
│  │     ├─ matrices/
│  │     ├─ impact/
│  │     └─ diagnostics/
│  └─ e2e/
├─ fixtures/
│  ├─ architecture-fixture.json
│  └─ README.md
├─ capella/
│  ├─ README_REAL_MODEL.md
│  ├─ MODEL_BLUEPRINT.md
│  ├─ ACCEPTANCE_CHECKLIST.md
│  ├─ operations/{pending,applied,failed}/
│  └─ python4capella/
├─ tools/
│  └─ reqpilot.py
├─ exports/
├─ evidence/
│  ├─ environment.md
│  ├─ strictdoc-spike.md
│  ├─ capella-spike.md
│  ├─ automated-tests.md
│  ├─ real-capella-test.md
│  └─ known-limitations.md
└─ .github/workflows/ci.yml
```

# 8. Конфигурация

`project.yaml`:

```yaml
schema_version: 1

project:
  id: pump-station-pilot
  title: Система мониторинга насосной станции

server:
  host: 127.0.0.1
  port: 8080

strictdoc:
  root: requirements
  config: requirements/strictdoc_config.py
  managed_documents:
    - requirements/01_stakeholder.sdoc
    - requirements/02_system.sdoc
    - requirements/03_software_interface.sdoc
    - requirements/04_safety.sdoc
    - requirements/05_tests.sdoc
  export_root: exports/strictdoc

capella:
  mode: disabled  # disabled | live | fixture
  model_path: null
  entrypoint: null
  read_only: true
  cache_path: .reqpilot/cache/capella-index.json

trace_links:
  path: trace-links.yaml

fixture:
  enabled: false
  path: fixtures/architecture-fixture.json
```

При `fixture` в UI постоянно показывать баннер: **«Демо-архитектура, не загруженная из Capella»**.

# 9. Доменная модель

## 9.1. Requirement

```ts
type RequirementType =
  | "Stakeholder" | "System" | "Interface"
  | "Software" | "Safety" | "TestCase";

type Requirement = {
  mid: string;
  uid: string;
  type: RequirementType;
  status: "Draft" | "Review" | "Approved" | "Deprecated";
  priority: "Low" | "Medium" | "High" | "Critical";
  verificationMethod:
    | "Inspection" | "Analysis" | "Demonstration"
    | "Test" | "NotApplicable";
  owner: string;
  source: string | null;
  tags: string[];
  title: string;
  statement: string;
  rationale: string;
  acceptanceCriteria: string;
  documentPath: string;
  sectionPath: string[];
  relations: RequirementRelation[];
  revision: string;
};
```

`revision` используется для optimistic concurrency.

## 9.2. Внутренняя связь

```ts
type RequirementRelation = {
  role: "Refines" | "Derives" | "Verifies" | "DependsOn";
  targetUid: string;
};
```

## 9.3. CapellaElement

```ts
type CapellaElement = {
  uuid: string;
  modelId: string;
  type: string;
  layer: "OA" | "SA" | "LA" | "PA" | "EPBS" | "OTHER";
  name: string;
  description: string | null;
  path: string[];
  parentUuid: string | null;
  relatedElementUuids: string[];
  diagramUuids: string[];
};
```

Индексировать минимум capabilities, activities, functions, components, actors, exchanges, chains, missions и scenarios.

## 9.4. TraceLink

```yaml
schema_version: 1

links:
  - id: TL-0001
    requirement:
      uid: SYS-001
      mid: 443a1acfe5e741838d7a6dc8a3c82111
    architecture:
      model_id: pump-station
      uuid: eff8d0b0-84df-431e-aec8-66150a0b1365
      type: SystemFunction
      name_snapshot: Publish HMI State
    relation: satisfied_by
    rationale: Функция публикует состояние насоса оператору.
    created_at: 2026-09-02T10:00:00Z
    updated_at: 2026-09-02T10:00:00Z
```

Типы links:

```text
satisfied_by
allocated_to
implemented_by
constrains
verified_by
related_to
```

`name_snapshot` не участвует в разрешении ссылки.

---

# 10. Демонстрационные данные

Создать не менее 22 объектов:

| UID | Тип | Название |
|---|---|---|
| STK-001 | Stakeholder | Отображение состояния насосов |
| STK-002 | Stakeholder | Предупреждение о превышении давления |
| STK-003 | Stakeholder | Просмотр истории событий |
| SYS-001 | System | Обновление состояния не позднее 2 секунд |
| SYS-002 | System | Формирование аварии при превышении порога |
| SYS-003 | System | Сохранение аварии до подтверждения |
| SYS-004 | System | Хранение журнала не менее 30 суток |
| SYS-005 | System | Обнаружение потери связи не позднее 3 секунд |
| IF-001 | Interface | Приём телеметрии по Modbus TCP |
| IF-002 | Interface | Синхронизация времени по NTP |
| SW-001 | Software | Опрос телеметрии каждые 500 мс |
| SW-002 | Software | Сравнение давления с порогом |
| SW-003 | Software | Автомат состояний аварии |
| SW-004 | Software | Запись события с меткой UTC |
| SAF-001 | Safety | Недостоверные данные не снимают аварию |
| SAF-002 | Safety | Потеря связи формирует фиксируемую аварию |
| TST-001 | TestCase | Проверка задержки отображения |
| TST-002 | TestCase | Проверка порога давления |
| TST-003 | TestCase | Проверка подтверждения аварии |
| TST-004 | TestCase | Проверка хранения журнала |
| TST-005 | TestCase | Проверка потери связи |
| TST-006 | TestCase | Проверка временных меток |

Создать минимум 20 внутренних отношений. Каждое System и Safety требование покрыть хотя бы одним TestCase.

# 11. Blueprint реальной Capella-модели

## Operational Analysis

Actors:

- Operator;
- Maintenance Engineer.

Capabilities:

- Monitor Pump Station;
- Respond to Pressure Alarm;
- Review Event History.

## System Analysis

System: `Pump Station Monitoring System`.

External actors:

- Sensor Gateway;
- Pump Controller;
- Operator.

Functions:

- Acquire Telemetry;
- Validate Measurements;
- Determine Pump State;
- Evaluate Pressure Threshold;
- Manage Alarm Lifecycle;
- Store Event;
- Publish HMI State.

Functional exchanges:

- Raw Telemetry;
- Validated Measurement;
- Pump State;
- Alarm Event;
- Acknowledgement;
- Event Record;
- HMI Update.

Functional chain: `Pressure Alarm Handling`.

## Logical Architecture

Components:

- Telemetry Adapter;
- State Processor;
- Alarm Manager;
- Event Store;
- HMI Service.

Начальные links:

| Требование | Архитектурный объект |
|---|---|
| STK-001 | Monitor Pump Station |
| STK-002 | Respond to Pressure Alarm |
| SYS-001 | Publish HMI State |
| SYS-002 | Evaluate Pressure Threshold |
| SYS-003 | Manage Alarm Lifecycle |
| SYS-004 | Store Event |
| IF-001 | Raw Telemetry |
| SW-003 | Alarm Manager |
| SAF-001 | Validate Measurements |
| SAF-002 | Pressure Alarm Handling |

# 12. StrictDocAdapter

## 12.1. Чтение

Требования читать через штатный StrictDoc JSON export во временный каталог.

Алгоритм:

1. взять файловую блокировку;
2. вызвать StrictDoc через `subprocess.run([...], shell=False)`;
3. проверить return code;
4. прочитать JSON;
5. нормализовать данные;
6. вычислить revision;
7. обновить только производный кеш;
8. вернуть структурированную диагностику.

Запрещено читать `.sdoc` регулярными выражениями или считать JSON новым источником истины.

## 12.2. Compatibility spike записи

До разработки основного UI Codex обязан доказать:

1. `.sdoc` разбирается средствами закреплённого StrictDoc либо его grammar/model API;
2. поле одного требования изменяется;
3. многострочный Unicode-текст сохраняется;
4. UID, MID и relations сохраняются;
5. StrictDoc повторно валидирует проект;
6. при искусственной ошибке исходный файл не повреждается.

Предпочтительный порядок:

1. использовать parser/model API StrictDoc;
2. при отсутствии пригодного write API сделать узкий детерминированный writer только для файлов из `managed_documents`;
3. не редактировать произвольные сторонние `.sdoc`;
4. не использовать regex patching.

Фактическое решение записать в `docs/adr/0002-strictdoc-write-strategy.md`.

## 12.3. Сохранение

1. проверить `If-Match`/revision;
2. получить эксклюзивную блокировку;
3. изменить управляемый узел;
4. записать временный файл;
5. проверить временный проект StrictDoc;
6. при ошибке вернуть диагностику и удалить временный файл;
7. при успехе создать backup;
8. выполнить `os.replace`;
9. перестроить индекс;
10. вернуть новый revision.

Инварианты:

- UID и MID существующего требования не меняются;
- неизвестные поля не теряются молча;
- новое требование получает новый MID;
- удалённый UID не переиспользуется;
- порядок секций стабилен;
- два параллельных сохранения не перетирают данные;
- ошибка не оставляет проект в невалидном состоянии.

# 13. CapellaAdapter

## 13.1. P0 read-only

- использовать `capellambse==0.8.0`;
- загрузить модель из `project.yaml`;
- индексировать UUID, тип, слой, имя, описание, parent и отношения;
- перечислять диаграммы;
- рендерить SVG по запросу;
- вычислять fingerprint модели;
- кешировать только производный индекс;
- не вызывать save и не мутировать модель.

Состояния:

```text
disabled
not_configured
loading
ready
stale
error
fixture
```

## 13.2. Доказательство read-only

Автотест:

1. SHA-256 всех файлов модели до чтения;
2. индексирование и рендеринг;
3. SHA-256 после чтения;
4. полное совпадение.

## 13.3. Fixture mode

Fixture:

- включается только явной настройкой;
- нужен для UI и CI;
- повторяет blueprint насосной станции;
- не создаёт Capella-файлы;
- не засчитывается как реальный интеграционный тест;
- постоянно обозначается в UI и отчётах.

---

# 14. TraceLinkRepository

- использовать `ruamel.yaml`;
- сохранять порядок и читаемый diff;
- применять lock и атомарную запись;
- ID связи уникален;
- дубликат пары `MID + model_id + UUID + relation` запрещён;
- UID/MID требования должны разрешаться;
- UUID должен разрешаться в live/fixture индексе;
- битая ссылка не удаляется автоматически.

Переименование Capella-объекта:

- link остаётся валидным по UUID;
- старый `name_snapshot` показывается рядом с новым именем;
- отдельная команда обновляет snapshots;
- ID links не меняются.

Удалённый UUID:

- link получает статус `broken`;
- dashboard увеличивает счётчик;
- impact analysis показывает потерянный объект;
- пользователь может удалить или переназначить link.

# 15. REST API

## Система

```text
GET  /api/health
GET  /api/project
GET  /api/diagnostics
POST /api/reload
```

## Требования

```text
GET    /api/requirements
GET    /api/requirements/{uid}
POST   /api/requirements
PUT    /api/requirements/{uid}
DELETE /api/requirements/{uid}
POST   /api/requirements/validate
```

Для PUT/DELETE обязателен revision или `If-Match`.

## Capella

```text
GET  /api/capella/status
POST /api/capella/reload
GET  /api/capella/elements
GET  /api/capella/elements/{uuid}
GET  /api/capella/diagrams
GET  /api/capella/diagrams/{uuid}/svg
```

Фильтры: layer, type, text, parent UUID, related-to UUID.

## Trace links

```text
GET    /api/trace-links
POST   /api/trace-links
PUT    /api/trace-links/{id}
DELETE /api/trace-links/{id}
POST   /api/trace-links/validate
POST   /api/trace-links/refresh-snapshots
```

## Аналитика

```text
GET /api/dashboard
GET /api/graph
GET /api/matrices/requirements-tests
GET /api/matrices/requirements-functions
GET /api/matrices/requirements-components
GET /api/matrices/functions-components
GET /api/impact/requirement/{uid}
GET /api/impact/capella/{uuid}
```

## Экспорт

```text
POST /api/exports/strictdoc/html
POST /api/exports/strictdoc/pdf
POST /api/exports/strictdoc/excel
POST /api/exports/strictdoc/json
POST /api/exports/strictdoc/reqif
POST /api/exports/combined-html
GET  /api/exports/jobs/{id}
GET  /api/exports/files/{id}
```

Job может исполняться синхронно, но API возвращает статус, stdout/stderr, duration, created files и SHA-256. Не создавать фиктивный background worker.

# 16. Общий граф

Источники узлов:

- требования и TestCase;
- элементы Capella;
- placeholder битых UUID.

Источники рёбер:

- StrictDoc relations;
- отношения и allocations Capella;
- `trace-links.yaml`.

Функции:

- focus на выбранном connected component;
- depth 1–4;
- zoom/pan/fit;
- сворачивание групп;
- фильтры источника, типа и relation;
- поиск;
- path finder между двумя узлами;
- переход к карточке;
- легенда;
- различие типа не только цветом;
- экспорт текущего вида в SVG/PNG;
- без 3D и цирка анимаций.

При 300 требованиях, 1 000 архитектурных элементах и 2 000 рёбрах backend должен формировать отфильтрованный граф менее чем за 1 секунду на обычной рабочей станции. UI не рендерит всё по умолчанию.

# 17. Матрицы

Реализовать:

1. требования ↔ тесты;
2. требования ↔ функции;
3. требования ↔ компоненты;
4. функции ↔ компоненты.

Обязательно:

- sticky headers;
- виртуализация;
- поиск;
- фильтры;
- переход к объекту;
- просмотр конкретной связи;
- проценты покрытия;
- CSV текущей матрицы.

Тестовое покрытие:

```text
System и Safety с входящей Verifies от TestCase
/
все System и Safety
```

Архитектурное покрытие:

```text
System, Software, Interface и Safety
с валидным trace-link
/
все System, Software, Interface и Safety
```

# 18. Impact analysis

Для требования показывать:

- родители, дочерние и зависимые требования;
- тесты;
- функции;
- компоненты;
- exchanges;
- chains;
- диаграммы;
- битые ссылки;
- конкретные кратчайшие пути.

Для Capella-элемента:

- связанные требования;
- архитектурные соседи;
- allocations;
- диаграммы;
- тесты, достижимые через требования.

Алгоритм:

- обход unified graph;
- depth по умолчанию 3;
- защита от циклов;
- deterministic ordering;
- группировка по типу;
- отображение пути, а не безымянной кучи объектов.

---

# 19. Интерфейс

## 19.1. Навигация

Левое меню:

1. Обзор;
2. Требования;
3. Архитектура;
4. Трассировка;
5. Матрицы;
6. Impact;
7. Экспорт;
8. Диагностика.

Верхняя панель:

- название проекта;
- глобальный поиск;
- состояние StrictDoc;
- состояние Capella;
- число broken links;
- reload;
- создание требования.

## 19.2. Обзор

Карточки:

- требования;
- Capella elements;
- внутренние relations;
- trace links;
- тестовое покрытие;
- архитектурное покрытие;
- broken links;
- время индексации;
- Git status;
- последний экспорт.

Показать списки непокрытых требований и последних ошибок.

## 19.3. Требования

Три панели:

- дерево документов/секций;
- таблица;
- карточка и редактор.

Колонки:

- UID;
- title;
- type;
- status;
- priority;
- owner;
- verification method;
- внутренние links;
- архитектурные links;
- revision.

Редактор:

- структурированная форма;
- preview;
- validation;
- conflict dialog при неверном revision;
- входящие/исходящие relations;
- Capella links;
- локальная ссылка «Открыть в штатном StrictDoc», если его сервер запущен.

## 19.4. Архитектура

- дерево по слоям;
- поиск и фильтры типов;
- breadcrumbs;
- карточка;
- UUID с copy;
- связанные требования;
- список диаграмм;
- SVG viewer;
- fit;
- onboarding при отсутствии модели;
- обязательный fixture banner.

## 19.5. Трассировка

- React Flow;
- focus mode;
- depth;
- filters;
- path finder;
- legend;
- переход к объектам;
- экспорт вида.

## 19.6. Матрицы

Tabs:

- Tests;
- Functions;
- Components;
- Allocations.

## 19.7. Диагностика

Отдельно показывать:

- StrictDoc errors;
- Capella load/render errors;
- broken UID;
- broken UUID;
- stale cache;
- revision conflicts;
- dirty Git tree;
- ChromeDriver/PDF status;
- фактические версии инструментов.

## 19.8. Визуальный стиль

- спокойный инженерный интерфейс;
- компактные таблицы;
- хорошая типографика;
- ясная иерархия;
- умеренные скругления;
- минимум анимации;
- статус обозначается цветом и текстом;
- выбранный объект хорошо различим;
- рабочая ширина от 1280 px;
- корректная клавиатурная навигация;
- contrast не ниже WCAG AA для основных элементов;
- никаких случайных градиентов «потому что SaaS».

# 20. Экспорт

StrictDoc formats вызываются только штатными командами:

- HTML;
- PDF;
- Excel;
- JSON;
- ReqIF.

Сохранять:

- безопасно сформированную команду;
- return code;
- stdout/stderr;
- duration;
- created files;
- SHA-256.

Дополнительно создать автономный combined HTML:

- project info;
- coverage;
- requirement table;
- trace-link table;
- uncovered requirements;
- broken links;
- выбранные матрицы;
- миниатюры доступных Capella diagrams;
- версии;
- встроенные CSS/images;
- без CDN.

Combined HTML является производным отчётом, а не новым источником истины.

# 21. Git и файловая безопасность

Запрещено:

- auto-commit без явного действия;
- reset/force checkout;
- удаление неизвестных файлов;
- shell string interpolation;
- выход путём за project root;
- запись Capella-файлов P0.

Обязательно:

- текущая ветка и dirty status;
- file lock;
- `os.replace`;
- backups в `.reqpilot/backups`;
- ограниченная ротация backups;
- path validation;
- кеши в `.gitignore`;
- subprocess только со списком аргументов и `shell=False`.

# 22. P1: Python4Capella queue

Выполнять только после завершения P0.

Web создаёт operation file:

```json
{
  "schemaVersion": 1,
  "operationId": "OP-0001",
  "modelFingerprint": "sha256:...",
  "createdAt": "2026-09-02T10:00:00Z",
  "operations": [
    {
      "type": "mirror_requirement_link",
      "requirementUid": "SYS-002",
      "requirementMid": "3aa994bb9e29407c87ea139f85ab4221",
      "capellaElementUuid": "8b0d19df-7446-4c3a-98e7-4a739c974059",
      "relation": "satisfied_by"
    }
  ]
}
```

Пользователь запускает `apply_trace_operations.py` внутри Capella/Python4Capella.

Требования:

- preview;
- dry-run;
- fingerprint check;
- idempotency;
- audit log;
- pending/applied/failed;
- запрет при неожиданной ревизии;
- сохранение после успешной транзакции;
- никакого автоматического запуска из FastAPI.

---

# 23. Командный интерфейс

Создать:

```bash
python tools/reqpilot.py <command>
```

Команды:

| Команда | Действие |
|---|---|
| `doctor` | Python, Node, StrictDoc, capellambse, config и paths |
| `setup` | установка зависимостей |
| `dev` | FastAPI + Vite |
| `serve` | production-like local build |
| `strictdoc-serve` | штатный UI StrictDoc |
| `validate` | требования, links и config |
| `index-capella` | индекс модели |
| `export` | StrictDoc formats + combined HTML |
| `test` | backend, frontend, e2e |
| `build` | production build |
| `clean` | только известные generated files |
| `package` | архив и итоговый отчёт |

Команды должны быть кроссплатформенными, без Bash-only сценариев.

# 24. Автоматические тесты

## 24.1. Backend unit

- нормализация StrictDoc JSON;
- UID/MID;
- допустимые значения;
- relations;
- graph traversal;
- cycle protection;
- matrices;
- impact paths;
- YAML round-trip;
- broken UUID;
- rename by UUID;
- path traversal rejection;
- subprocess без shell.

## 24.2. StrictDoc integration

- загрузка demo `.sdoc`;
- изменение title;
- multiline Unicode;
- неизменность MID;
- relations round-trip;
- создание требования;
- удаление;
- rollback;
- revision conflict;
- HTML;
- Excel;
- JSON;
- ReqIF;
- PDF либо явный environment skip.

## 24.3. Capella adapter

На реальной лицензионно допустимой тестовой модели:

- open model;
- поиск типов;
- UUID;
- paths;
- diagrams;
- SVG;
- отсутствие изменения файлов;
- отсутствие `.aird`;
- неверный path.

Fixture-тесты не заменяют реальные adapter tests.

## 24.4. API

- health;
- requirements CRUD;
- revision conflict;
- Capella status;
- links CRUD;
- graph filters;
- matrices;
- impact;
- export errors.

## 24.5. Frontend

- dashboard;
- requirements table/editor;
- architecture tree;
- fixture banner;
- trace-link dialog;
- graph;
- matrices;
- diagnostics.

## 24.6. Playwright

Fixture-mode сценарий:

1. открыть приложение;
2. выбрать `SYS-002`;
3. изменить rationale;
4. сохранить;
5. проверить новый revision;
6. выбрать `Evaluate Pressure Threshold`;
7. создать `satisfied_by`;
8. открыть граф;
9. увидеть link;
10. открыть requirements-functions matrix;
11. увидеть отмеченную ячейку;
12. запустить combined HTML;
13. проверить файл.

Покрытие:

- backend пользовательский код ≥ 85%;
- frontend бизнес-логика ≥ 75%.

# 25. CI

GitHub Actions:

1. Python 3.12;
2. закреплённая Node.js;
3. установка lock-файлов;
4. lint;
5. type check;
6. backend tests;
7. frontend tests;
8. fixture e2e;
9. StrictDoc validation;
10. HTML/JSON/Excel/ReqIF exports;
11. combined HTML;
12. production build;
13. artifacts;
14. PDF отдельным job при необходимости;
15. Capella GUI не запускать в обычном CI.

CI падает при:

- невалидном `.sdoc`;
- duplicate UID/MID;
- broken mandatory link;
- TypeScript error;
- failing test;
- failing build.

# 26. Ручная проверка реальной Capella

Создать `capella/ACCEPTANCE_CHECKLIST.md`.

Подготовка:

- Capella 7.1.0;
- Requirements Viewpoint 0.14.0;
- Python4Capella 1.4.1 только P1;
- модель по blueprint;
- `.aird`;
- `capella.mode: live`.

Проверки:

1. backend открывает модель;
2. UI показывает `live`;
3. видны ожидаемые elements;
4. доступны минимум три реальные diagrams;
5. UUID совпадают;
6. десять links сохраняются;
7. links переживают restart;
8. rename не ломает link;
9. delete создаёт broken link;
10. чтение не меняет SHA-256 файлов;
11. StrictDoc ReqIF импортируется через Requirements Viewpoint;
12. `.bridgetraces` сохранён;
13. повторный ReqIF проходит через Diff/Merge;
14. результат и ограничения документированы честно.

Если Capella недоступна:

```text
REAL CAPELLA TEST: NOT EXECUTED
```

Это не заменяется красивой картинкой из fixture.

# 27. Критерии приёмки P0

P0 считается завершённым, если одновременно:

1. `doctor` не показывает блокирующих проблем.
2. `dev`, `validate`, `test`, `build` успешны.
3. Требования читаются из `.sdoc`.
4. CRUD создаёт валидный `.sdoc`.
5. MID стабилен.
6. rollback работает.
7. revision conflict не перетирает изменения.
8. StrictDoc открывает изменённый проект.
9. HTML, Excel, JSON, ReqIF сформированы.
10. PDF сформирован либо есть честный environment skip.
11. Fixture mode обозначен.
12. Live mode читает модель через capellambse.
13. P0 не меняет Capella files.
14. Реальные SVG отображаются при наличии.
15. Links хранятся в YAML.
16. Rename не ломает link.
17. Delete UUID выявляется.
18. Unified graph работает.
19. Все четыре matrices работают.
20. Impact показывает paths.
21. Combined HTML автономен.
22. Нет вымышленных Capella assets.
23. README воспроизводим.
24. Финальный отчёт разделяет automated и manual tests.

# 28. Качество кода

- strict TypeScript;
- mypy или pyright;
- Ruff;
- ESLint;
- Prettier;
- dependency injection для adapters;
- domain logic не зависит от FastAPI/React;
- небольшие модули;
- structured logs;
- ясные исключения;
- отсутствие global mutable state;
- docstrings у public Python APIs;
- отсутствие secrets и telemetry;
- отсутствие внешней сети при штатной работе.

# 29. ADR

Создать:

```text
docs/adr/0001-sources-of-truth.md
docs/adr/0002-strictdoc-write-strategy.md
docs/adr/0003-capella-read-only-p0.md
docs/adr/0004-cross-tool-trace-links.md
docs/adr/0005-fixture-mode-boundaries.md
```

# 30. Порядок реализации Codex

## Этап 0. Spikes

До UI:

1. StrictDoc install и JSON export;
2. safe `.sdoc` write;
3. rollback;
4. capellambse install;
5. open legal test model;
6. UUID + SVG;
7. SHA-256 read-only proof;
8. результаты в `evidence`.

Не подменять неудачный spike fixture-данными.

## Этап 1. Каркас

Repository, locks, config, FastAPI, React, CI, `reqpilot.py`.

## Этап 2. StrictDoc

Grammar, demo data, adapter, writer, validation, CRUD, exports.

## Этап 3. Capella

Adapter, index, diagrams, status, fixture boundary.

## Этап 4. Trace links

YAML, validation, CRUD, broken/rename logic.

## Этап 5. Аналитика

Graph, matrices, impact, dashboard.

## Этап 6. UI

Все экраны, loading/error/empty states, accessibility, polished layout.

## Этап 7. Завершение

Tests, build, screenshots, README, evidence, package.

После каждого этапа:

```text
validate
backend tests
frontend tests
build
```

Не переходить дальше при failing tests.

# 31. Обязательные результаты

- рабочий код;
- demo `.sdoc`;
- `trace-links.yaml`;
- явно маркированный fixture;
- capellambse adapter;
- тесты;
- CI;
- README;
- ADR;
- Capella instructions;
- sample exports;
- combined HTML;
- реальные screenshots web UI;
- automated report;
- real Capella report либо `NOT EXECUTED`;
- known limitations.

# 32. Формат финального отчёта Codex

Таблица:

| Область | Статус | Доказательство | Ограничение |
|---|---|---|---|
| StrictDoc read | PASS/FAIL | | |
| StrictDoc write | PASS/FAIL | | |
| Rollback | PASS/FAIL | | |
| Native exports | PASS/FAIL | | |
| capellambse fixture | PASS/FAIL | | |
| real Capella read | PASS/FAIL/NOT EXECUTED | | |
| real diagrams | PASS/FAIL/NOT EXECUTED | | |
| trace links | PASS/FAIL | | |
| graph | PASS/FAIL | | |
| matrices | PASS/FAIL | | |
| impact | PASS/FAIL | | |
| Python4Capella P1 | PASS/FAIL/NOT IMPLEMENTED | | |

Дополнительно:

- фактические версии;
- команды запуска;
- результаты тестов;
- paths к exports;
- созданные файлы;
- пропущенные пункты и причины;
- SHA-256 Capella до/после;
- известные ограничения.

Фраза «всё работает» без доказательств не принимается.

---

# 33. Короткое позиционирование

```text
StrictDoc отвечает: что система должна делать.
Capella отвечает: из каких функций и компонентов она состоит.
ReqPilot показывает: как требования, архитектура и тесты связаны.
```
