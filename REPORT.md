# Практична робота 1. Проєктування і розгортання CRUD-сервісу

Варіант 7 — запис про вакцинацію. Виконала: Дьяченко Валерія, група ЗК-61мп.

Дисципліна: «Високопродуктивні розподілені обчислювальні системи».

## Стан і метод обробки

Стан збереженої серії: `complete`. Цей звіт заново обчислює показники з rows у JSON, не змінюючи сирі записи або старі summary. Тому старі summary версії 2 можуть відрізнятися від таблиці: у них achieved_rps включав транспортні помилки. Виправлена методика — версія 3. Для повторного формування достатньо `python -X utf8 scripts/report.py`.

## Етап 1. Проєктування

## Проєктування сервісу вакцинацій

### Схема таблиці vaccinations

| Поле | PostgreSQL тип | Обов’язковість | Призначення |
|---|---|---|---|
| id | BIGINT GENERATED ALWAYS AS IDENTITY | PK | Ідентифікатор генерує PostgreSQL; запас діапазону |
| patient_code | VARCHAR(200) | NOT NULL | Знеособлений код, не персональні дані |
| vaccine | VARCHAR(200) | NOT NULL | Назва вакцини, точний фільтр |
| batch | VARCHAR(200) | NOT NULL | Серія, рядок зберігає літери та початкові нулі |
| dose_number | SMALLINT | NOT NULL | Ціла доза від 1 до 4 |
| administration_date | DATE | NOT NULL | Календарна дата без зайвої точності часу |
| facility | VARCHAR(200) | NOT NULL | Заклад вакцинації |

Первинний ключ автоматично індексує `id`. B-tree `(vaccine,id)` підтримує точний фільтр та стабільне сортування. CHECK повторює правила як захист цілісності; API перевіряє їх **до** SQL і повертає 400. Унікальність patient_code або batch не накладається: той самий пацієнт може мати кілька введень, серія містить багато доз.

### Контракт API

Тіло B — JSON з усіма шістьма полями: `{"patient_code":"P007","vaccine":"MMR","batch":"B007","dose_number":1,"administration_date":"2026-01-10","facility":"Clinic 7"}`. Тіло R — B з доданим числовим `id`. Жодних часткових PUT, id від клієнта чи невідомих полів.

| Метод і шлях | Запит | Успішна відповідь | Помилки |
|---|---|---|---|
| POST /vaccinations | B | 201 R | 400 поле/формат; 503 база |
| GET /vaccinations | limit, offset, vaccine | 200 {items:[R],total,limit,offset} | 400 пагінація; 503 база |
| GET /vaccinations/{id} | без тіла | 200 R | 404 відсутній запис/нечисловий шлях; 503 база |
| PUT /vaccinations/{id} | B повністю | 200 R | 400 поле/формат; 404 відсутній; 503 база |
| DELETE /vaccinations/{id} | без тіла | 204 без тіла | 404 відсутній, зокрема повторно; 503 база |
| GET /healthz | без тіла | 200 {status:ready} | 503 {status:not_ready} |

Метод, що не підтримується, дає 405. Невідомий маршрут — 404. JSON-помилка: `{"errors":{"dose_number":"Ціле число від 1 до 4"}}`. Для healthz інший формат описано вище. Для PUT валідація передує перевірці існування: якщо одночасно невалідне тіло та відсутній id, повертається 400.

`limit=20` за замовчуванням, діапазон 1–100; `offset=0`, діапазон 0–2147483647. `total` рахує всі записи після фільтра, до пагінації. `vaccine` — точне, чутливе до регістру порівняння. Сортування `id ASC`. Підрахунок і сторінка читаються в одній REPEATABLE READ транзакції.

Порожні рядки, рядки понад 200 символів, нецілі дози, булеві дози, дата не у YYYY-MM-DD, неіснуюча календарна дата та майбутня дата дають 400. Обмеження розміру тіла — 16 КіБ, перевищення повертає 400 з поясненням. Поточна дата визначається часовою зоною Europe/Kyiv у контейнері.

### Стенд

Три сервіси: db, web, lb. Один іменований том pgdata. Внутрішня backend мережа; лише lb додатково підключений до public і публікує 18080 на хост (8080 всередині lb). Пароль лише через .env / змінну середовища. PostgreSQL автоматично застосовує schema.sql на порожньому томі. Подальші зміни схеми потребуватимуть міграцій; для цієї початкової схеми достатньо init-файла.

db readiness → web readiness → lb. Пул кожного Gunicorn worker чекає базу до 60 с. Nginx 1.28 підтримує resolve для DNS Compose і оновлює адреси web при масштабуванні. Немає container_name та прив’язки web до хостового порту. Кожна репліка: cpus 1.5, mem_limit 1g, 2 worker по 8 потоків, пул до 16 з’єднань на worker. Дві репліки можуть використати до 64 з’єднань PostgreSQL.

Фінальна стадія Debian 12 slim з дайджестом, Python із Debian, без компіляторів і pip; пакети встановлюються в builder. Користувач uid 10001. Дайджест фіксує базовий шар, але не робить весь образ бітово відтворюваним: apt-репозиторії та транзитивні залежності можуть оновлюватися. Повторна збірка порівнює саме базові RootFS layers та зберігає BuildKit лог.

## Етап 2. Реалізація

Шість ендпоінтів реалізовано у app.py. SQL параметризований, дані зберігаються у PostgreSQL. Валідація виконується до SQL. GET /healthz перевіряє базу запитом SELECT 1. PUT потребує всіх полів; повторний DELETE повертає 404.

## Етап 3. Образ

```dockerfile
# Verified through the official Docker Registry on 2026-10-06.
FROM debian:12-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587 AS builder
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 python3-venv ca-certificates && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/venv
COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt && /opt/venv/bin/pip uninstall -y pip setuptools wheel

FROM debian:12-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587 AS runtime
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 ca-certificates tzdata && rm -rf /var/lib/apt/lists/* && useradd --uid 10001 --create-home app
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY app.py /app/app.py
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=Europe/Kyiv
USER 10001
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "8", "--access-logfile", "-", "app:create_app()"]
```

## Контекст збірки

```text
.git
.env
.venv
__pycache__
results
tests
scripts
*.md
*.zip
*.docx

history
correction-checks.txt
```

## Етап 4. Стенд

```yaml
name: vaccinations-pr1
services:
  db:
    image: postgres:16.10-bookworm
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-vaccinations}
      POSTGRES_USER: ${POSTGRES_USER:-vaccinations}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}
      TZ: Europe/Kyiv
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./schema.sql:/docker-entrypoint-initdb.d/001-schema.sql:ro
    networks: [backend]
    healthcheck:
      test: [CMD-SHELL, 'pg_isready -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}"']
      interval: 2s
      timeout: 3s
      retries: 30
    restart: unless-stopped
  web:
    build: .
    image: vaccinations-pr1:local
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER:-vaccinations}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB:-vaccinations}
    networks: [backend]
    depends_on:
      db:
        condition: service_healthy
    cpus: 1.5
    mem_limit: 1g
    healthcheck:
      test: [CMD, /opt/venv/bin/python, -c, 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=2)']
      interval: 2s
      timeout: 3s
      retries: 30
    restart: unless-stopped
  lb:
    image: nginx:1.28.0-alpine
    ports: ['${PORT:-18080}:8080']
    volumes: ['./nginx.conf:/etc/nginx/nginx.conf:ro']
    networks: [backend, public]
    depends_on:
      web:
        condition: service_healthy
    restart: unless-stopped
networks:
  backend:
    internal: true
  public: {}
volumes:
  pgdata: {}
```

## Балансувальник

```nginx
events { worker_connections 4096; }
http {
    resolver 127.0.0.11 valid=2s ipv6=off;
    log_format instances '$time_iso8601 $request $status upstream=$upstream_addr';
    access_log /dev/stdout instances;
    upstream api {
        zone api 64k;
        server web:8000 resolve;
        keepalive 64;
    }
    server {
        listen 8080;
        location / {
            proxy_pass http://api;
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_connect_timeout 3s;
            proxy_read_timeout 60s;
        }
    }
}
```

## Автоматична схема

```sql
CREATE TABLE IF NOT EXISTS vaccinations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_code VARCHAR(200) NOT NULL CHECK (length(trim(patient_code)) > 0),
    vaccine VARCHAR(200) NOT NULL CHECK (length(trim(vaccine)) > 0),
    batch VARCHAR(200) NOT NULL CHECK (length(trim(batch)) > 0),
    dose_number SMALLINT NOT NULL CHECK (dose_number BETWEEN 1 AND 4),
    administration_date DATE NOT NULL CHECK (administration_date <= CURRENT_DATE),
    facility VARCHAR(200) NOT NULL CHECK (length(trim(facility)) > 0)
);
CREATE INDEX IF NOT EXISTS vaccinations_vaccine_id_idx ON vaccinations(vaccine, id);
```

## Інструкція запуску

Windows: `powershell -ExecutionPolicy Bypass -File .\start.ps1`. Для двох реплік додати `-Replicas 2`. Linux/macOS: `sh start.sh` або `sh start.sh 2` (потрібен Python 3 для створення пароля). Потрібні Docker із Linux containers, Compose v2 та доступ до реєстрів образів. Скрипт створює некомітований .env із випадковим паролем і виконує збірку та запуск. Зовнішня точка входу — http://localhost:18080; порт можна змінити у .env.

## Розмір образу і запуск

Розмір за docker image inspect: 211.266 MB. Три старти на порожньому томі з готовими образами: 10.729, 9.146, 7.634 с; медіана 9.146 с.

## Етапи 5–6. Навантаження

Власний scripts/loadgen.py планує моменти t0+i/rate незалежно від відповідей. Процеси ділять сітку, HTTP-запити виконує пул потоків. Перед серією створюється 100 записів, вимірюється GET /vaccinations/{id}. Для кожної конфігурації: 10 с прогріву, окремі 30 с вимірювання, три повтори; рівні 10/100/500 rps, одна і дві репліки. Прогрів не входить у результати.

Повна серія: `python -X utf8 scripts/experiment.py --reset-lab-data --threads 512`. Ця команда видаляє дані лабораторної для перевірок порожньої бази. Окремий прогін: `python -X utf8 scripts/loadgen.py http://127.0.0.1:18080/vaccinations/1 --rate 100 --warmup 10 --duration 30 --threads 512 --output results/run-100.json`.

Машина: Windows-10-10.0.26200-SP0; логічних ядер: 8. Процесів генератора: 8; потоків на процес: 512. Генератор на тому самому хості: True. Конкуренція за CPU впливає на верхній рівень.

### Визначення метрик

- Досягнута швидкість achieved_rps: отримані HTTP-відповіді (статуси 100–599), завершені у 30-секундному вікні, / 30. HTTP 500/504 враховуються як відповіді, але не як успішні.
- success_rps: відповіді 2xx у тому самому вікні / 30.
- status=0: HTTP-відповідь не отримано. Тайм-аут чи обрив з’єднання виключено з achieved_rps і перцентилів HTTP-відповідей.
- p50/p95/p99: час від фактичного початку HTTP-запиту до повного читання відповіді для всіх отриманих відповідей прогону, включно із завершеними після вікна.
- Не 2xx: частка неуспішних HTTP-статусів серед отриманих відповідей. Транспортні помилки та загальні неуспішні спроби наведено окремо.
- completed_rps: завершені спроби будь-якого результату / 30; лише діагностичний показник.
- У таблицях наведено медіани трьох повторів; вони не обов’язково належать одному повтору.
- Тайм-аут HTTP — 15 с; затримка від планового моменту та час до завершення всіх спроб збережені у rows.

| Репліки | Ціль rps | HTTP-відповіді rps | p50 мс | p95 мс | p99 мс | Не 2xx, % |
|---|---|---|---|---|---|---|
| 1 | 10 | 10.000 | 5.588 | 15.475 | 26.471 | 0.000 |
| 1 | 100 | 99.933 | 5.135 | 7.916 | 13.154 | 0.000 |
| 1 | 500 | 172.867 | 3556.525 | 9215.823 | 14336.278 | 2.137 |
| 2 | 10 | 10.000 | 5.339 | 10.347 | 18.278 | 0.000 |
| 2 | 100 | 99.967 | 4.886 | 7.311 | 11.336 | 0.000 |
| 2 | 500 | 402.433 | 313.844 | 6370.662 | 7786.701 | 0.000 |

### Фактична відправка і помилки

| Репліки | Ціль rps | Відправлено rps | p95 lag мс | 2xx rps | Транспортні помилки, % | Усі неуспішні спроби, % |
|---|---|---|---|---|---|---|
| 1 | 10 | 10.000 | 16.389 | 10.000 | 0.000 | 0.000 |
| 1 | 100 | 100.000 | 15.565 | 99.933 | 0.000 | 0.000 |
| 1 | 500 | 499.800 | 23.408 | 168.633 | 60.373 | 61.220 |
| 2 | 10 | 10.000 | 16.268 | 10.000 | 0.000 | 0.000 |
| 2 | 100 | 99.967 | 15.571 | 99.967 | 0.000 | 0.000 |
| 2 | 500 | 499.767 | 20.776 | 402.433 | 7.667 | 7.667 |

Контроль відправки: sent_rps ≥ 98% цілі та p95 lag ≤ 100 мс. Усі наявні основні прогони пройшли контроль. Це час запуску HTTP-запиту на клієнті; момент прибуття на сервер окремо не вимірювався.

### Калібрування no-op

| Ціль rps | Відправлено rps | HTTP rps | 2xx rps | p95 lag мс |
|---|---|---|---|---|
| 10 | 10.000 | 10.000 | 10.000 | 15.688 |
| 100 | 100.000 | 100.000 | 100.000 | 15.685 |
| 500 | 499.767 | 499.767 | 499.767 | 16.551 |

### Розподіл і розкид

Два інстанси у відповідях: ['5550c1dd8121', 'e55a63c72535']. Логи upstream: results/lb-2.log.

| Репліки | Ціль rps | Діапазон HTTP rps | Діапазон усіх неуспіхів, % |
|---|---|---|---|
| 1 | 10 | 10.000–10.000 | 0.000–0.000 |
| 1 | 100 | 99.933–99.967 | 0.000–0.000 |
| 1 | 500 | 136.433–177.367 | 60.713–68.313 |
| 2 | 10 | 10.000–10.000 | 0.000–0.000 |
| 2 | 100 | 99.967–100.000 | 0.000–0.000 |
| 2 | 500 | 339.100–494.700 | 0.000–24.447 |

Зафіксовані транспортні помилки (усі основні прогони):

- `RemoteDisconnected('Remote end closed connection without response')`: 24038.
- `TimeoutError('timed out')`: 8952.
- `OSError(10048, 'Обычно разрешается только одно использование адреса сокета (протокол/сетевой адрес/порт)', None, 10048, None)`: 2.

## Етап 7. Розрахунки

### Прискорення і Карп–Флатт

X — медіанна швидкість отриманих HTTP-відповідей, включно з неуспішними HTTP-статусами. Транспортні помилки виключено. S=X₂/X₁; N=2; e=(1/S−0.5)/0.5=2/S−1.

При 10 rps: S=10.000/10.000=1.00000; e=2/1.00000−1=1.00000.

При 100 rps: S=99.967/99.933=1.00033; e=2/1.00033−1=0.99933.

При 500 rps: S=402.433/172.867=2.32800; e=2/2.32800−1=-0.14089.

Спільні компоненти — одна PostgreSQL, Nginx, мережа і ресурси хоста. На малому попиті S≈1 не означає повну серійність. Якщо e від’ємне, воно не є від’ємною часткою коду: це ознака непридатності простої моделі до цього вимірювання. При великій частці помилок і розкиді S описує зміну HTTP-швидкості, але не доводить частку послідовної роботи. Окремо наведено швидкість 2xx.

### Закон Літтла

L=λW. L вимірюється як площа (sent−completed) за вікно / тривалість. Для узгодженості W — середній час завершення всіх спроб, а λ — фактичні відправки. На рівні 100 rps без помилок це одночасно середній час HTTP-відповіді.

λ=100.00000 rps; W=0.0073204 с; λW=0.7320418; L виміряне=0.7319295; розбіжність=|0.7319295−0.7320418|/0.7320418×100%=0.015%.

Обрано один повтор із медіанною HTTP-швидкістю; незалежні медіани не змішуються. Скінченне вікно обрізає незавершені запити при обчисленні L, а W включає їх повний час. Закон застосовний до стабільного потоку; при наростанні черги його стаціонарна інтерпретація обмежена.

### Відкритий і закритий контури

У закритому контурі фіксовано round(L) одночасних потоків, мінімум 1; наступний запит потоку лише після завершення попереднього. Новий сценарій обирає перевантажений рівень за HTTP-швидкістю, не за кількістю завершених помилок.

Рівень 500 rps; конкуренція 1744=round(1743.6429892).

| Режим | HTTP rps | 2xx rps | p95 HTTP, мс | p95 усіх спроб, мс |
|---|---|---|---|---|
| Відкритий | 177.367 | 171.767 | 9469.813 | 15015.074 |
| Закритий | 182.667 | 182.667 | 7825.975 | 15062.864 |

У цій серії p95 HTTP-відповідей у закритому контурі нижчий за відкритий. Теоретично зворотний зв’язок закритого контуру зменшує надходження при сповільненні відповідей і стримує наростання черги. Цей механізм не гарантує менший виміряний p95: закритий генератор має один процес і багато потоків; значні помилки змінюють склад отриманих відповідей. p95 HTTP виключає запити без відповіді, тому для контролю цензурування поруч наведено p95 усіх спроб. Висновок про меншу затримку робиться лише за фактичними числами.

## Етап 8. Додаткова вимога варіанта

Обидві стадії Dockerfile використовують Debian 12 slim із digest. Ліміти web: 1.5 CPU, 1 GB. results/build-first.log і build-second.log зберігають збірки, image.json — базові RootFS-шари. Порівняння однакових базових шарів: True. Digest: `debian:12-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587`.

## Етап 9. Журнал перевірки

Сценарій перевіряє CRUD, валідацію, збереження після down/up, порожню базу після down -v/up і healthz=503 при зупиненій базі. Фактичні відповіді нижче; повні дані — results/checks.json.

| Метод | Шлях | Код |
|---|---|---|
| POST | `/vaccinations` | 201 |
| GET | `/vaccinations` | 200 |
| GET | `/vaccinations/1` | 200 |
| PUT | `/vaccinations/1` | 200 |
| DELETE | `/vaccinations/1` | 204 |
| DELETE | `/vaccinations/1` | 404 |
| GET | `/vaccinations/1` | 404 |
| POST | `/vaccinations` | 400 |
| POST | `/vaccinations` | 400 |
| POST | `/vaccinations` | 400 |
| PUT | `/vaccinations/1` | 400 |
| GET | `/vaccinations?limit=101` | 400 |
| GET | `/vaccinations/2` | 200 |
| GET | `/vaccinations` | 200 |
| GET | `/vaccinations?vaccine=MMR&limit=10&offset=5` | 200 |
| GET | `/healthz` | 503 |

```json
{
  "method": "POST",
  "path": "/vaccinations",
  "status": 201,
  "body": {
    "administration_date": "2026-10-14",
    "batch": "B007",
    "dose_number": 1,
    "facility": "Clinic 7",
    "id": 1,
    "patient_code": "P000",
    "vaccine": "MMR"
  },
  "instance": "735cae6fa216"
}
```

```json
{
  "method": "GET",
  "path": "/vaccinations",
  "status": 200,
  "body": {
    "items": [
      {
        "administration_date": "2026-10-14",
        "batch": "B007",
        "dose_number": 1,
        "facility": "Clinic 7",
        "id": 1,
        "patient_code": "P000",
        "vaccine": "MMR"
      }
    ],
    "limit": 20,
    "offset": 0,
    "total": 1
  },
  "instance": "735cae6fa216"
}
```

```json
{
  "method": "GET",
  "path": "/vaccinations/1",
  "status": 200,
  "body": {
    "administration_date": "2026-10-14",
    "batch": "B007",
    "dose_number": 1,
    "facility": "Clinic 7",
    "id": 1,
    "patient_code": "P000",
    "vaccine": "MMR"
  },
  "instance": "735cae6fa216"
}
```

```json
{
  "method": "PUT",
  "path": "/vaccinations/1",
  "status": 200,
  "body": {
    "administration_date": "2026-10-14",
    "batch": "B007",
    "dose_number": 1,
    "facility": "Clinic 7",
    "id": 1,
    "patient_code": "P001",
    "vaccine": "HepB"
  },
  "instance": "735cae6fa216"
}
```

```json
{
  "method": "DELETE",
  "path": "/vaccinations/1",
  "status": 204,
  "body": null,
  "instance": "735cae6fa216"
}
```

```json
{
  "method": "DELETE",
  "path": "/vaccinations/1",
  "status": 404,
  "body": {
    "errors": {
      "id": "Запис не знайдено"
    }
  },
  "instance": "735cae6fa216"
}
```

```json
{
  "method": "GET",
  "path": "/vaccinations/1",
  "status": 404,
  "body": {
    "errors": {
      "id": "Запис не знайдено"
    }
  },
  "instance": "735cae6fa216"
}
```

```json
{
  "method": "POST",
  "path": "/vaccinations",
  "status": 400,
  "body": {
    "errors": {
      "dose_number": "Ціле число від 1 до 4"
    }
  },
  "instance": "735cae6fa216"
}
```

```json
{
  "method": "POST",
  "path": "/vaccinations",
  "status": 400,
  "body": {
    "errors": {
      "dose_number": "Ціле число від 1 до 4"
    }
  },
  "instance": "735cae6fa216"
}
```

```json
{
  "method": "POST",
  "path": "/vaccinations",
  "status": 400,
  "body": {
    "errors": {
      "administration_date": "Дата введення не може бути в майбутньому"
    }
  },
  "instance": "735cae6fa216"
}
```

```json
{
  "method": "PUT",
  "path": "/vaccinations/1",
  "status": 400,
  "body": {
    "errors": {
      "administration_date": "Обов’язкове поле",
      "batch": "Обов’язкове поле",
      "dose_number": "Обов’язкове поле",
      "facility": "Обов’язкове поле",
      "patient_code": "Обов’язкове поле"
    }
  },
  "instance": "735cae6fa216"
}
```

```json
{
  "method": "GET",
  "path": "/vaccinations?limit=101",
  "status": 400,
  "body": {
    "errors": {
      "limit": "Ціле число від 1 до 100"
    }
  },
  "instance": "735cae6fa216"
}
```

```json
{
  "method": "GET",
  "path": "/vaccinations/2",
  "status": 200,
  "body": {
    "administration_date": "2026-10-14",
    "batch": "B007",
    "dose_number": 1,
    "facility": "Clinic 7",
    "id": 2,
    "patient_code": "P099",
    "vaccine": "HepB"
  },
  "instance": "923dd6388e50"
}
```

```json
{
  "method": "GET",
  "path": "/vaccinations",
  "status": 200,
  "body": {
    "items": [],
    "limit": 20,
    "offset": 0,
    "total": 0
  },
  "instance": "5550c1dd8121"
}
```

```json
{
  "method": "GET",
  "path": "/vaccinations?vaccine=MMR&limit=10&offset=5",
  "status": 200,
  "body": {
    "items": [
      {
        "administration_date": "2026-10-14",
        "batch": "B007",
        "dose_number": 1,
        "facility": "Clinic 7",
        "id": 11,
        "patient_code": "P010",
        "vaccine": "MMR"
      },
      {
        "administration_date": "2026-10-14",
        "batch": "B007",
        "dose_number": 1,
        "facility": "Clinic 7",
        "id": 13,
        "patient_code": "P012",
        "vaccine": "MMR"
      },
      {
        "administration_date": "2026-10-14",
        "batch": "B007",
        "dose_number": 1,
        "facility": "Clinic 7",
        "id": 15,
        "patient_code": "P014",
        "vaccine": "MMR"
      },
      {
        "administration_date": "2026-10-14",
        "batch": "B007",
        "dose_number": 1,
        "facility": "Clinic 7",
        "id": 17,
        "patient_code": "P016",
        "vaccine": "MMR"
      },
      {
        "administration_date": "2026-10-14",
        "batch": "B007",
        "dose_number": 1,
        "facility": "Clinic 7",
        "id": 19,
        "patient_code": "P018",
        "vaccine": "MMR"
      },
      {
        "administration_date": "2026-10-14",
        "batch": "B007",
        "dose_number": 1,
        "facility": "Clinic 7",
        "id": 21,
        "patient_code": "P020",
        "vaccine": "MMR"
      },
      {
        "administration_date": "2026-10-14",
        "batch": "B007",
        "dose_number": 1,
        "facility": "Clinic 7",
        "id": 23,
        "patient_code": "P022",
        "vaccine": "MMR"
      },
      {
        "administration_date": "2026-10-14",
        "batch": "B007",
        "dose_number": 1,
        "facility": "Clinic 7",
        "id": 25,
        "patient_code": "P024",
        "vaccine": "MMR"
      },
      {
        "administration_date": "2026-10-14",
        "batch": "B007",
        "dose_number": 1,
        "facility": "Clinic 7",
        "id": 27,
        "patient_code": "P026",
        "vaccine": "MMR"
      },
      {
        "administration_date": "2026-10-14",
        "batch": "B007",
        "dose_number": 1,
        "facility": "Clinic 7",
        "id": 29,
        "patient_code": "P028",
        "vaccine": "MMR"
      }
    ],
    "limit": 10,
    "offset": 5,
    "total": 50
  },
  "instance": "5550c1dd8121"
}
```

```json
{
  "method": "GET",
  "path": "/healthz",
  "status": 503,
  "body": {
    "status": "not_ready"
  },
  "instance": "5550c1dd8121"
}
```

## Висновок

Для 1 реплік рівні з відставанням HTTP-швидкості понад 5%: [500].

Для 2 реплік рівні з відставанням HTTP-швидкості понад 5%: [500].

При 500 rps, 1 реплік: HTTP-швидкість 172.867 rps; 2xx 168.633 rps; p95 HTTP 9215.823 мс; транспортні помилки 60.373%; усі неуспіхи 61.220%.

При 500 rps, 2 реплік: HTTP-швидкість 402.433 rps; 2xx 402.433 rps; p95 HTTP 6370.662 мс; транспортні помилки 7.667%; усі неуспіхи 7.667%.

Наявність спільної бази та балансувальника не доводить конкретне вузьке місце. На верхньому рівні враховано помилки, розкид повторів і конкуренцію генератора зі стендом за ресурси. Без додаткових логів вебпроцесу та ресурсних вимірювань точний компонент обмеження не встановлено. Отримані числа не підмінюються очікуваним подвоєнням швидкості або очікуваним меншим p95.

## Відкинуті рішення

1. SQLite — умова вимагає спільну PostgreSQL.
2. Словник у пам’яті — дані губляться і не є спільними для реплік.
3. Копіювання web2 — суперечить масштабуванню параметром.
4. Лише фіксовані користувачі — це закритий контур, який зменшує потік під перевантаженням.
5. Базовий образ лише за тегом — не виконує вимогу digest.

## Використання генеративних моделей

Модель допомагала з проєктуванням, реалізацією, Docker, генератором і звітом. Після цього виконано локальні тести, CRUD і Docker-перевірки та фактичні навантажувальні прогони. При виправленні метрик сирі результати не змінювалися; додано тести відокремлення HTTP-відповідей від транспортних помилок і перевірки динамічної генерації звіту.

## Контрольні питання

1. PUT замінює всі поля; PATCH передавав би лише зміни.
2. Конфлікт із наявним ID зазвичай 409; це API забороняє клієнтський ID із 400 і генерує його у базі.
3. Шари зберігають файлові зміни; рання зміна інвалідує наступний кеш, тому залежності копіюються раніше коду.
4. down зберігає named volume; down -v видаляє його; видалення контейнера не видаляє named volume.
5. depends_on без service_healthy задає порядок, а не готовність бази.
6. EXPOSE документує порт, ports публікує його. База доступна за db:5432 у мережі Compose.
7. Відкритий контур планує потік незалежно від відповіді, закритий уповільнює надходження при зростанні затримки.
8. Зміни після другої репліки визначено таблицями; спільні база, Nginx і ресурси хоста.
9. e — оцінка за моделлю, не буквальна частка коду при помилках і суперлінійних ефектах. Окремі бази можуть змінити обмеження, але додають узгодження.
10. Біля насичення черга зростає нелінійно; для M/M/1 W=1/(μ−λ).

## Джерела

- https://docs.docker.com/reference/compose-file/services/
- https://nginx.org/en/docs/http/ngx_http_upstream_module.html
- https://www.psycopg.org/psycopg3/docs/advanced/pool.html