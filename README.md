# ReqPilot Engineering Workbench

Локальный инженерный workbench поверх StrictDoc и Eclipse Capella. Он не
создаёт собственную RMS или базу требований: канонические требования остаются
в `.sdoc`, архитектура — в Capella, а межсистемные связи — в
`trace-links.yaml`.

Демонстрационный проект описывает систему мониторинга насосной станции. В P0
доступны CRUD требований, архитектурное дерево, трассировка, общий граф,
четыре матрицы покрытия, impact analysis и нативные экспорты StrictDoc.

> В поставляемой конфигурации включён явно обозначенный `fixture`-режим.
> Eclipse Capella 7.1.0, Requirements Viewpoint 0.14.0 и легальная реальная
> модель на машине сборки отсутствовали, поэтому **REAL CAPELLA TEST: NOT
> EXECUTED**. Fixture не считается доказательством реальной интеграции.

## Источники истины

| Данные | Канонический источник |
|---|---|
| Требования, тесты и связи между требованиями | `requirements/*.sdoc` |
| Архитектурные элементы, отношения и диаграммы | реальная Capella-модель, read-only в P0 |
| Связи «требование ↔ архитектура» | `trace-links.yaml` по MID и UUID |
| Удалённые UID | `deleted-uids.json` |
| JSON-индексы, кэши и HTML | только производные данные |

Backend не записывает `.capella`, `.aird`, `.melodymodeller` или
`.bridgetraces`. ReqIF создаётся штатным StrictDoc 0.29.0; собственного
конвертера в проекте нет.

## Зафиксированные версии

- Python 3.12;
- StrictDoc 0.29.0;
- capellambse 0.8.0 из официального тега, commit
  `2abba5cd8922a306cdb735a9c19bcfefdb74a7e8`;
- Node.js 24.18.1;
- React 18.3.1, TypeScript и Vite;
- целевой Eclipse Capella 7.1.0;
- целевой Requirements Viewpoint 0.14.0;
- Python4Capella 1.4.1 — только P1, **NOT IMPLEMENTED**.

StrictDoc 0.29.0 и capellambse 0.8.0 требуют несовместимые версии
`python-datauri`. Поэтому один `uv.lock` разворачивает два изолированных
окружения: `.venv` для приложения/StrictDoc и `.venv-capella` для read-only
Capella worker. Это намеренная граница совместимости, а не дублирование
зависимостей.

## Быстрый запуск

Требуются Python 3.12, Node.js 24.18.1, npm и доступ к сети только для
первоначальной установки зависимостей.

```bash
git clone https://github.com/dechernov-stack/reqpilot-workbench.git
cd reqpilot-workbench
python3.12 tools/reqpilot.py setup
python3.12 tools/reqpilot.py doctor
python3.12 tools/reqpilot.py serve
```

Откройте <http://127.0.0.1:8080>. Production frontend собирается и отдаётся
FastAPI с loopback-интерфейса. Произвольный CORS и telemetry не включены.

Для разработки с Vite HMR:

```bash
.venv/bin/python tools/reqpilot.py dev
```

Приложение будет доступно на <http://127.0.0.1:5173>, API — на
<http://127.0.0.1:8080>.

## Команды

```bash
.venv/bin/python tools/reqpilot.py doctor
.venv/bin/python tools/reqpilot.py validate
.venv/bin/python tools/reqpilot.py index-capella
.venv/bin/python tools/reqpilot.py export
.venv/bin/python tools/reqpilot.py test
.venv/bin/python tools/reqpilot.py build
.venv/bin/python tools/reqpilot.py package
.venv/bin/python tools/reqpilot.py clean
```

- `doctor` проверяет точные версии, конфигурацию и доступность окружений;
- `validate` запускает нативный JSON export StrictDoc и проверяет UID/MID и
  YAML links;
- `index-capella` читает выбранный fixture или реальную модель;
- `export` создаёт HTML, Excel, JSON, ReqIF и автономный combined HTML; PDF
  добавляется при заданном `REQPILOT_CHROMEDRIVER`;
- `test` запускает backend, frontend и Playwright fixture E2E;
- `build` проверяет Python bytecode, ESLint и production bundle;
- `package` повторяет release gates и создаёт детерминированный ZIP;
- `clean` удаляет только известные производные каталоги и отказывается
  следовать symlink.

Можно запросить только часть нативных форматов:

```bash
.venv/bin/python tools/reqpilot.py export --formats html excel json reqif
```

## PDF без внешней сети в штатной работе

StrictDoc использует `html2pdf4doc` и локальный Chromium/ChromeDriver. Runtime
не скачивает драйвер автоматически: один раз установите ChromeDriver версии,
совместимой с локальным Chrome, затем укажите существующий executable:

```bash
export REQPILOT_CHROMEDRIVER=/absolute/path/to/chromedriver
.venv/bin/python tools/reqpilot.py export --formats pdf
```

Без переменной общий `export` явно пишет `PDF export NOT EXECUTED` и продолжает
остальные форматы. Явно запрошенный `--formats pdf` с отсутствующим или
несовместимым драйвером завершается ошибкой; ошибка совместимости не
скрывается.

`package` обновляет curated samples после release gates. Если драйвер не
задан, он может повторно использовать только уже отслеживаемый PDF, чей размер,
SHA-256 и canonical revision совпадают с manifest; иначе упаковка требует
явного `REQPILOT_CHROMEDRIVER`.

Экспертный `package --skip-checks` не запускает gates и не обновляет samples.
Он упаковывает только существующий набор, если manifest относится к текущей
canonical revision, содержит все обязательные форматы, а размеры и SHA-256
каждого файла совпадают. Отчёты evidence и настоящие PNG screenshots также
проходят обязательный preflight.

## Интерфейс

В русскоязычном UI есть восемь рабочих разделов:

1. обзор состояния проекта и покрытия;
2. дерево/таблица требований, фильтры, карточка и безопасный CRUD;
3. архитектурное дерево, свойства и реальные SVG из выбранного adapter;
4. трассировка: CRUD межсистемных YAML links, broken-link diagnostics и
   интерактивный unified graph требований, архитектуры и тестов;
5. четыре матрицы: requirement→test, requirement→function,
   requirement→component и function→component;
6. impact analysis с направлением, глубиной и объяснимыми paths;
7. запуск и скачивание нативных/combined экспортов;
8. диагностика окружения, конфликтов и инструментов.

Запись требования использует optimistic revision. Перед заменой исходного
`.sdoc` выполняются повторная проверка revision, запись во временный файл,
нативная валидация StrictDoc, атомарный `os.replace`, `fsync` и rollback при
ошибке. UID/MID стабилизированы; удалённые UID сохраняются в отслеживаемом
`deleted-uids.json`.

## Конфигурация Capella

Начальная конфигурация в `project.yaml`:

```yaml
capella:
  mode: fixture
  model_path: null
  entrypoint: null
  read_only: true
```

Fixture содержит 37 архитектурных элементов, 41 отношение и три SVG, но в UI
и API всегда помечается как демонстрационный. Для реальной модели переключите
`mode: live`, задайте repository-local `model_path` и при необходимости
`entrypoint`, оставив `read_only: true`. Затем используйте отдельное окружение:

```bash
REQPILOT_CAPELLA_PYTHON=.venv-capella/bin/python \
  .venv/bin/python tools/reqpilot.py index-capella
```

Полная процедура создания модели, проверки SHA-256 и ручного ReqIF import/
Diff-Merge находится в `capella/README_REAL_MODEL.md` и
`capella/ACCEPTANCE_CHECKLIST.md`. Автоматическая часть не запускает GUI и не
фабрикует screenshots или `.bridgetraces`.

## Экспорты и доказательства

Нативные результаты StrictDoc помещаются в
`exports/strictdoc/<format>/<job-id>/`, автономный сводный отчёт — в
`exports/combined/reqpilot-combined.html`, release archive — в
`exports/packages/reqpilot-workbench-p0.zip`.

Проверяемые результаты сборки находятся в `evidence/`:

- `automated-tests.md` — точные команды и результаты automated gates;
- `acceptance-report.md` — 24 критерия P0 и итоговая таблица;
- `strictdoc-spike.md` — compatibility spike чтения/записи/rollback;
- `capella-spike.md` и `real-capella-test.md` — честная граница fixture/live;
- `known-limitations.md` — ограничения без маскировки ошибок;
- `screenshots/` — реальные screenshots локального web UI.

## Тестирование вручную

Быстрый автоматический gate без браузерного E2E:

```bash
.venv/bin/python tools/reqpilot.py validate
PYTHONPATH=backend .venv/bin/pytest backend/tests \
  --cov=reqpilot --cov-report=term-missing --cov-fail-under=85
npm --prefix frontend run test:coverage
npm --prefix frontend run lint
npm --prefix frontend run build
```

Полный fixture E2E выполняется командой `tools/reqpilot.py test`. Тест поднимает
одноразовый backend на `127.0.0.1:18080`, создаёт изолированную временную копию
проекта, редактирует требование, создаёт trace link, открывает граф и матрицу и
формирует combined export; канонические файлы рабочей копии не меняются.

## Безопасность файлов

- все изменяемые и экспортные пути должны находиться внутри корня проекта;
- symlink в state/export/package/clean paths отклоняется;
- backend управляет только allowlist документов из `project.yaml`;
- subprocess запускаются массивами аргументов с `shell=False`;
- пакетирование принимает только обычные repository-local файлы;
- Capella P0 остаётся read-only;
- сервер по умолчанию доступен только на `127.0.0.1`.

## Ограничения P0

- нет авторизации, многопользовательской работы или облачного сервиса;
- нет браузерного редактирования Capella;
- реальная Capella требует предоставленных пользователем GUI и модели;
- Python4Capella queue, зеркалирование links, Git history/baseline, M2Doc и
  тёмная тема относятся к P1 и **NOT IMPLEMENTED**;
- Git adapter в P0 только читает статус/diff и ничего не commit/reset/checkout.

Лицензия пользовательского кода — MIT. Лицензии StrictDoc, Eclipse Capella,
Requirements Viewpoint и остальных зависимостей действуют отдельно.
