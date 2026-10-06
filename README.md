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

Linux/macOS: скопіюйте `.env.example` у `.env`, задайте власний випадковий пароль, тоді `docker compose up -d --build --wait --scale web=1`. Для DATABASE_URL пароль має містити URI-безпечні символи, наприклад hex. Публікується лише порт балансувальника.

## Повна перевірка та реальний звіт

На машині з Docker і Python 3.11+ без додаткових Python пакетів:

```powershell
python scripts/experiment.py --reset-lab-data
```

Параметр явно дозволяє видалити том **лише цієї практичної** для передбачених умовою перевірок порожньої бази. Серія триває щонайменше 15 хвилин плюс час збірки. Не запускайте паралельно інші навантаження. Скрипт зберігає сирі запити, логи, відомості про машину, журнал CRUD, результати стартів і образу в `results/` та формує `REPORT.md`. Для меншої кількості процесів можна додати `--processes 4`; зазначайте це у звіті. За замовчуванням використовується 64 потоки на процес — саме ця конфігурація відповідає наявним у архіві вимірюванням. Для нового діагностичного перепрогону можна явно задати, наприклад, `--threads 256`; якщо `sent_rps` не досягає 98% цілі, генератор виведе попередження і такий прогін не слід трактувати як чисту межу лише вебсервісу.

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
