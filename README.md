# MoneyMap — HackAlem AI

Веб-инструмент для исследования направленной сети внутрибанковских переводов. Он рассчитывает роли и приоритеты узлов, формирует три CSV-файла по схеме кейса «Граф денег» и показывает аналитику связи каждого `gid`.

## Данные

Положите выданные организаторами `nodes.parquet`, `edges.parquet` и `transactions.parquet` в папку `data/`. Сырые данные не хранятся в Git.

## План запуска

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python pipeline.py --data data --out out
streamlit run app.py
```

Пайплайн сформирует `out/nodes_roles.csv`, `out/clusters.csv`, `out/top_nodes.csv`. Веб-интерфейс позволит искать `gid`, изучать его связи и проверять обоснование присвоенной роли.

Выводы системы — гипотезы для AML-проверки, а не утверждения о виновности клиентов.
