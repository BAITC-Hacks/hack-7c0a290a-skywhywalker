# Проверка поставки MoneyGraph AI

Дата проверки исходной локальной поставки: 23 сентября 2026.

Этот файл фиксирует выполненные проверки. Git-версия находится в alternatives/moneygraph-ai и требует сборки frontend по README; локальные окружения и dist в коммит не входят.

- Backend: 19 tests passed, 1 предупреждение зависимости Starlette/TestClient.
- Production frontend: Vite build passed (React, Tailwind CSS, Cytoscape.js).
- Браузер: Microsoft Edge headless; 1600×1100 и 390×844. Ошибок JavaScript нет, горизонтального переполнения страницы нет.
- Проверены: demo, загрузка custom CSV, Analyze, поиск, повторный выбор account, priority filter/reset, Follow 1–4 hops, объяснение, Evidence, Compare F/D, AI briefing, переключение обратно на demo.
- Проверен вопрос «Почему F выше D?» и переход к Evidence D из ответа Copilot.
- Проверены fallback при отсутствии ключа, отказе клиента и невалидном structured response.
- OpenAI с реальным ключом не вызывался. Режим без ключа явно помечен как LOCAL EXPLANATION.
- WebMCP отсутствует в браузере проверки; экспериментальная регистрация select_moneygraph_account не проверена.
- На момент проверки приложение запускалось локально на http://127.0.0.1:8000. Публичный Python-хостинг не настраивался.

Готовый frontend/dist проверялся в исходной локальной поставке. В Git сохранены исходники и lockfiles; frontend/dist, .env, .venv, node_modules и загруженные пользователем данные исключены.
