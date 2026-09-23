# MoneyGraph AI

Рабочий MVP для хакатона: React + Vite + Tailwind CSS + Cytoscape.js + Lucide; FastAPI + Pandas + NetworkX + scikit-learn + Pydantic. Это локальное приложение для AML-аналитика. Оно приоритизирует проверку транзакционных связей, а не устанавливает вину.

## Запуск из GitHub

Требуются Python 3.14 (проверено на 3.14.2), Node.js 22.12+ или 24 и pnpm. Выполните из корня клонированного репозитория:

```sh
git switch experiment/moneygraph-ai-mvp
cd alternatives/moneygraph-ai/frontend
pnpm install --frozen-lockfile
pnpm build
cd ..
python run.py
```

После первой сборки на Windows можно запускать `alternatives/moneygraph-ai/Start-MoneyGraph.cmd`. Скрипт создаёт отдельную `.venv`, устанавливает Python-зависимости и открывает http://127.0.0.1:8000. Первый запуск требует интернета. Остановка — Ctrl+C. Не запускайте второй экземпляр на том же порту.

`frontend/dist`, `.venv` и `node_modules` не включены в Git: их создают команды выше. Все последующие команды README выполняются из `alternatives/moneygraph-ai`, если явно не указан другой каталог. Корневые зависимости MoneyMap устанавливать для этого кандидата не нужно.

## Демонстрация

При старте автоматически анализируется `data/sample_transactions.csv`: **42 синтетических account, 172 транзакции**. Никаких реальных персональных данных. CSV воспроизводимо создаётся скриптом `python data/generate_sample.py`.

- Выберите **F**: COLLECTOR, FAN_IN, CONSOLIDATOR, BRIDGE, RAPID_PASS_THROUGH, POTENTIAL_MULE_PATTERN.
- **Follow the Money**: depth 1–4, по входящим, исходящим или всем связям. Например, A01 → D → F → X → C01 — четыре ребра.
- **Ask AI** открывает объяснение. **View Evidence** показывает metrics, правила, исходные транзакции и реальные пути.
- **Compare**: F vs D, компоненты приоритета и evidence обоих узлов.
- **AI briefing**: сводка уже рассчитанной сети, топ узлов и пути.
- **Upload dataset** → выбрать CSV → **Analyze network**. До анализа старые метрики не отображаются.
- Поиск account, фильтры priority/pattern/amount, zoom, pan, drag, fit/reset работают на готовых результатах, без повторного расчёта NetworkX.

## CSV

```csv
sender,receiver,amount,timestamp
A,D,50000,2026-09-01T10:10:00Z
B,D,80000,2026-09-01T10:15:00Z
D,F,125000,2026-09-01T10:30:00Z
```

UTF-8, разделитель — запятая. Обязательные 4 столбца; дополнительные игнорируются. Account ID сохраняет ведущие нули; 1–64 букв/цифр/пробелов/символов `_ . - : @`. Пустые ID, отрицательные/нулевые/бесконечные суммы и неверные даты отклоняются. Timestamp преобразуется в UTC; без временной зоны считается UTC. Все суммы предполагаются в одной сопоставимой единице/валюте; приложение не выполняет конвертацию. Повторяющиеся строки считаются отдельными транзакциями. Самопереводы сохраняются в графе, но исключены из FIFO и уникальных контрагентов.

Лимиты MVP: 5 MB, 20 000 транзакций, 1 500 узлов, до 8 загруженных datasets плюс demo. Наборы не сохраняются на диск; при перезапуске исчезают. Неактивные более 2 часов наборы очищаются при следующей загрузке. `X-Dataset-ID` выбирает отдельный набор; без заголовка используется demo. Это изоляция состояния, а не система авторизации.

## Расчёты и explainability

Все числа считаются по dataset. Таблица рёбер содержит каждую транзакцию; NetworkX DiGraph агрегирует параллельные переводы для структурных метрик. `links` — уникальные направленные пары, `transactions` — строки CSV. Total network volume считает каждую строку один раз; сумма объёмов всех узлов будет учитывать обычный перевод у обеих сторон.

Признаки: входящие/исходящие counts и суммы, уникальные контрагенты, средние/медиана, in/out ratio (null при нулевом outflow), степени, degree centrality, betweenness, PageRank, community ID, число сообществ соседей, turnover и FIFO-время. PageRank учитывает объёмы, betweenness — направленную структуру без весов. Для >250 узлов betweenness приближённый, с выборкой до 100 исходных узлов. Louvain и Isolation Forest имеют фиксированный seed=42.

Priority = **0.35 Graph + 0.25 Anomaly + 0.25 Pattern + 0.15 Flow**.

- Graph: 50% betweenness, 25% PageRank, 25% degree centrality. Каждая метрика делится на максимум в текущем dataset.
- Anomaly: Isolation Forest, 150 деревьев, `-score_samples`, min-max 0–100. Признаки log1p: count, volume, in/out counterparties, turnover, betweenness, PageRank. Для <5 узлов либо одинаковых векторов — 0, поскольку выборка недостаточна.
- Pattern: COLLECTOR 20, DISTRIBUTOR 20, CONSOLIDATOR 25, BRIDGE 25, RAPID_PASS_THROUGH 25, POTENTIAL_MULE_PATTERN 25; максимум 100. FAN_IN/FAN_OUT — синонимы структуры, повторно в score не учитываются.
- Flow: 70% доли входящего объёма, сопоставленного с исходящими в пределах 60 минут, плюс 30% `min(in,out)/max(in,out)`.
- LOW <40, MEDIUM от 40 до <70, HIGH от 70. UI показывает score до двух десятичных знаков; точное значение API — до двух. Не сравнивайте абсолютные scores между разными datasets: нормализация относительная, вероятность нарушения не калибрована.

Правила явно возвращаются в Evidence:

- COLLECTOR/FAN_IN: >=5 разных отправителей.
- DISTRIBUTOR/FAN_OUT: >=5 разных получателей.
- CONSOLIDATOR: >=2 входящих ветви, каждая имеет >=2 источника.
- BRIDGE: соседи из >=2 сообществ и betweenness >=0.02.
- RAPID_PASS_THROUGH: rapid_share >=0.60 и turnover >=0.70.
- POTENTIAL_MULE_PATTERN: одновременно >=5 источников, rapid_share >=0.60, turnover >=0.80 и >=3 получателей. Независимость владельцев источников неизвестна; сигнал не устанавливает статус account.

FIFO не расходует одну поступившую сумму дважды и не связывает исходящий перевод с будущим входящим. Это гипотеза распределения объёма; остатки, назначение платежа и переводы вне CSV неизвестны. Среднее время удержания взвешено по сопоставленной сумме и относится только к сопоставленному объёму.

Evidence содержит до 500 транзакций выбранного узла (общий count и флаг усечения), до 20 rapid-пар и до 8 направленных простых путей через узел, максимум 4 ребра. Для каждого пути возвращаются transaction IDs и флаг chronological. Структурный путь без временной последовательности явно отделяется от хронологического; ни один не доказывает движение тех же денег.

## OpenAI

Работа без ключа полноценна для графового анализа. Copilot возвращает явно маркированные детерминированные объяснения `mode=rules`; свободный вопрос в этом режиме получает стандартную сводку узла. Это не имитация ответа LLM.

Чтобы включить OpenAI:

1. Скопируйте `.env.example` в `.env` в корне проекта.
2. Укажите `OPENAI_API_KEY`; при необходимости измените `OPENAI_MODEL` (по умолчанию `gpt-4.1-mini`).
3. Перезапустите backend.

Ключ читается исключительно backend и не включается в frontend, API-ответы или архив. `.env` добавлен в `.gitignore`. Не присылайте ключ в чат.

Интеграция использует Responses API, `responses.parse`, Pydantic и `store=False`. Документация: https://developers.openai.com/api/docs/guides/structured-outputs . Backend сам выбирает ограниченный контекст: metrics узла, до 25 его транзакций, до 10 исходящих контрагентов, выборка путей; для summary — top 5, aggregate stats и ограниченные пути. Весь CSV модели не передаётся. При включённом OpenAI этот контекст отправляется внешнему API.

System prompt запрещает обвинения, выдуманные связи/числа и выполнение инструкций из account IDs/вопросов. Pydantic проверяет структуру, но не гарантирует фактическую истинность свободного текста LLM. Evidence и отображаемые signals независимо поступают из backend. Аналитик должен сверять AI-интерпретацию с ними. Ошибки API, таймауты, отказ или невалидный JSON приводят к локальному fallback, без падения приложения. Реальный запрос с API-ключом в этой поставке не выполнялся.

## API

Swagger: http://127.0.0.1:8000/docs . Для своего dataset передавайте `X-Dataset-ID` из upload.

| Method | Endpoint | Вход |
|---|---|---|
| POST | /api/upload | multipart file |
| POST | /api/analyze | текущий dataset |
| GET | /api/graph | — |
| GET | /api/node/{node_id} | — |
| GET | /api/network/{node_id}/hops | depth=1..4, direction=both/incoming/outgoing |
| GET | /api/investigation/ranking | — |
| GET | /api/evidence/{node_id} | — |
| POST | /api/ai/explain-node | {"node_id":"F"} |
| POST | /api/ai/chat | {"node_id":"F","question":"Почему?"} |
| POST | /api/ai/compare-nodes | {"node_a":"F","node_b":"D"} |
| POST | /api/ai/investigation-summary | {} |
| GET | /api/health | — |

## Разработка

Python:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Frontend (Node.js 22.12+ или 24, pnpm):

```sh
cd frontend
pnpm install --frozen-lockfile
pnpm dev
# http://127.0.0.1:5173; /api проксируется на backend :8000
pnpm build
```

Backend раздаёт `frontend/dist`, когда папка существует на момент запуска. После первой сборки перезапустите backend. Исходные диапазоны Python-библиотек в requirements.txt, проверенные версии — requirements-lock.txt; frontend фиксирован pnpm-lock.yaml.

Проверки: `python -m pytest tests -q`. Проверены границы hop-обхода, FIFO, детерминизм, вычисления на малой выборке и self-loop, planted patterns, evidence transaction IDs, upload/analyze/isolation и все fallback AI endpoints. Браузерная проверка: Follow 1–4, explanation, evidence, compare, briefing, search, repeat selection, filter/reset, CSV upload/analyze, возврат demo, mobile 390px. Production build прошёл. Есть предупреждение Starlette о будущей замене httpx в TestClient; на работоспособность проверок не влияет.

При поддержке браузером `document.modelContext` регистрируется необязательное действие `select_moneygraph_account`. В используемом браузере WebMCP отсутствовал, поэтому этот экспериментальный путь не проверен; обычный интерфейс от него не зависит.

## Границы MVP

Локальный однопользовательский демонстрационный инструмент, один процесс backend. Нет авторизации, журналирования действий, долговременного хранилища, банковских интеграций и промышленной валидации AML-модели. Не публикуйте сервер в интернет без добавления этих механизмов. Текущие пороги демонстрационные и требуют отдельной валидации для реального применения.

Публичное развёртывание не выполнено: доступный Sites-хостинг предназначен для Cloudflare Workers и не запускает этот Python/FastAPI/NetworkX backend. Поставка сохраняет запрошенный стек, включает готовый frontend и может быть перенесена на сервер с Python.
