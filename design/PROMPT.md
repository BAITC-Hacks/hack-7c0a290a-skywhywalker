# Визуальный референс MoneyMap

Сгенерирован встроенным ImageGen; `reference.png` — макет, а не скриншот работающего приложения. Вымышленные имена, пользователи и значения на макете не являются данными проекта и не переносятся в интерфейс.

## Что перенесено в код

Белая навигация, зелёный акцент Freedom-inspired, компактные показатели, граф и карточка проверки в одной строке, очередь узлов и три шага работы. Реализация: `app.py` и `ui.css`. Цвета ролей остаются различными, чтобы не смешивать координатора, транзит и получателя. Все числа берутся из расчёта, все идентификаторы — из набора данных. Крупнейшие прямые связи отбираются отдельно с обеих сторон; интерфейс явно обозначает, что показывает фрагмент сети.

Макет переносится по структуре, а не вставляется картинкой вместо интерфейса. Нет вымышленного профиля пользователя, уведомлений или названий компаний.

## Финальный запрос генератору

```text
Use case: ui-mockup
Asset type: high fidelity desktop web application design reference, 1600x1000 landscape screenshot, flat front view, no device frame.
Primary request: Design MoneyMap, a Russian-language financial transaction network investigation workspace for AML analysts. A clear usable product screen, NOT a landing page. Freedom-inspired fresh green #51AF3D with forest #153724, ivory #F5F8F3, white cards, charcoal ink. Restrained polished bank-grade dashboard, precise readable typography, generous spacing, thin borders, 12px rounded corners, no gradients, no stock photos.
Composition: narrow white left navigation (220px) with green MoneyMap symbol/name, subtitle "Граф денег", active pale-green item "Обзор дела", followed by "Расследование", "Приоритеты", "Кластеры", "Методика". Bottom small "HackAlem AI / Финансы".
Main workspace top small breadcrumb "Рабочее место AML-аналитика", title "Кого проверить следующим?", one sentence "Находим значимые узлы и объясняем движение денег." Small badge "Июль 2026 · 4 колена".
Below four compact white metric cards: "81 / Исходных клиентов", "2 248 / Узлов в сети", "4 840 / Переводов", "50 / В очереди проверки".
Main content row two panels, left 65% width: heading "Как движутся деньги", supporting caption "Пример: первый узел в очереди". Beautiful highly readable left-to-right directed transaction graph on subtle dotted white canvas: 3 green source circles at left, central selected dark forest rounded node labelled "…603629100" and tag "Координатор", 4 small teal/green receiver nodes on right. Curved thin connectors with arrowheads, only a few short labels. Lanes titled "Плательщики", "Выбранный узел", "Получатели". Tiny role legend. Right panel: kicker "ПРИОРИТЕТ № 1", title "Проверить связи узла", large "0.980" labelled "Приоритет проверки", three evidence rows with check icons: "19 плательщиков", "61 получатель", "Связь с 4 исходными клиентами". Full-width vivid green button "Открыть расследование →". Soft amber footnote "Гипотеза, не доказательство нарушения".
Bottom white panel "Очередь проверки" with clean 3-row compact table: rank, shortened gid, role chip, score, arrow. Bottom subtle 3-step strip "1. Выберите узел → 2. Изучите связи → 3. Проверьте основания".
Constraints: Russian Cyrillic legible, no fake analytics charts, no invented financial amounts, no red threat or guilt labels, no giant hero heading. Primary action unmistakable. Buildable dashboard, hierarchy and clarity paramount.
```
