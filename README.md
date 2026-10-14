
# Практична робота 1 Варіант 7

CRUD сервіс записів про вакцинацію. Реалізація: Python 3.11 у Debian 12, Flask, Gunicorn, PostgreSQL 16, Nginx. Дані знеособлені.

## Запуск

Передумови: Docker Engine / Docker Desktop із Linux containers і Docker Compose v2. Для Windows запускайте з PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Це одна команда: генерує випадковий пароль у некомітованому `.env`, збирає образ та піднімає всі три сервіси. API: http://localhost:18080/healthz.

Дві репліки без редагування конфігурації:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -Replicas 2
```

Linux/macOS (Docker Compose v2 і Python 3): `sh start.sh` або `sh start.sh 2`. Пароль створюється автоматично. Публікується лише порт балансувальника.

## Повна перевірка та реальний звіт

На машині з Docker і Python 3.10+ без додаткових Python пакетів:

```powershell
python -X utf8 scripts/experiment.py --reset-lab-data --threads 512
```

Параметр явно дозволяє видалити том **лише цієї практичної** для передбачених умовою перевірок порожньої бази. Серія триває щонайменше 15 хвилин плюс час збірки. Не запускайте паралельно інші навантаження. Скрипт зберігає сирі запити, логи, відомості про машину, журнал CRUD, результати стартів і образу в `results/` та формує `REPORT.md`. Для меншої кількості процесів можна додати `--processes 4`; зазначайте це у звіті. За замовчуванням використовується 256 потоків на процес. Збережена завершена серія виконана з --threads 512. Якщо потік не досягає 98% цілі або p95 затримки відправки перевищує 100 мс, сценарій зупиняється з помилкою та зберігає діагностику. Повторіть із `--threads 512` або на менш завантаженому хості. Старі результати автоматично переміщуються у `history/`, тому різні серії не змішуються.

Docker Desktop встановлено для виконання роботи. Фактичні вимірювання та журнал перевірок збережено у `results/`; `REPORT.md` формує висновки з цих файлів. Для відтворення виконайте сценарій на своїй машині. Порт 18080 обрано через зайнятий іншою службою порт 8080 на машині експерименту.

## Приклад запиту

```powershell
$body = @{patient_code='P007'; vaccine='MMR'; batch='B007'; dose_number=1; administration_date='2026-01-10'; facility='Clinic 7'} | ConvertTo-Json
Invoke-RestMethod http://localhost:18080/vaccinations -Method Post -ContentType application/json -Body $body
Invoke-RestMethod 'http://localhost:18080/vaccinations?vaccine=MMR&limit=10&offset=0'
```

Дата введення має бути не пізніше поточної дати сервісу. Заголовок `X-Instance-ID` і upstream у логах Nginx підтверджують розподіл між контейнерами.

## Файли

- `DESIGN.md` — схема й контракт API.
- `app.py`, `schema.sql` — реалізація й автоматична ініціалізація таблиці.
- `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `nginx.conf` — стенд.
- `scripts/loadgen.py` — власний відкритий і закритий генератор.
- `scripts/noop.py` — незалежна перевірка генератора.
- `scripts/experiment.py` — усі прогони та перевірки.
- `scripts/report.py`, `REPORT.md` — формування звіту.
- `tests/` — перевірки правил валідації та обчислення метрик.

## Локальні тести

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m unittest discover -s tests -v
```

Зупинка без втрати даних: `docker compose down`. Видалення даних лабораторної: `docker compose down -v`.

## Перевірений час запуску

Три вимірювання запуску виконано з порожнім томом та вже зібраними образами. Готовність перевірялася паралельно з `docker compose up` через `/healthz` з інтервалом 0.1 с. Отримано 10.116, 7.469 та 7.477 с; медіана — **7.477 с**. Чинні результати — `results/startup.json`. 

За потреби повторити лише ці три вимірювання можна командою:

```powershell
python -X utf8 scripts/experiment.py --reset-lab-data --startup-only
```

Команда видаляє дані бази цієї лабораторної та оновлює час запуску і звіт; результати навантаження залишаються. За наявними даними точний компонент, який обмежив роботу на 500 rps, не встановлено; це пояснено у звіті.
