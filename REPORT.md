# Практична робота 1 Проєктування і розгортання CRUD сервісу

Варіант 7 Запис про вакцинацію

Виконала: Дьяченко Валерія. Група: ЗК-61мп.

КПІ ім. Ігоря Сікорського, факультет біомедичної інженерії, кафедра біомедичної кібернетики. Дисципліна Високопродуктивні розподілені обчислювальні системи.

Стан поточної серії: `complete`. Перевірте завершення всіх етапів перед здачею.

## Стан виконання

Файли всіх прогонів наявні; коректність open-loop оцінюється окремо за фактичними відправками та lag.

## Етап 1 Проєктування

### Проєктування сервісу вакцинацій

## Схема таблиці vaccinations

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

## Контракт API

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

## Стенд

Три сервіси: db, web, lb. Один іменований том pgdata. Внутрішня backend мережа; лише lb додатково підключений до public і публікує 18080 на хост (8080 всередині lb). Пароль лише через .env / змінну середовища. PostgreSQL автоматично застосовує schema.sql на порожньому томі. Подальші зміни схеми потребуватимуть міграцій; для цієї початкової схеми достатньо init-файла.

db readiness → web readiness → lb. Пул кожного Gunicorn worker чекає базу до 60 с. Nginx 1.28 підтримує resolve для DNS Compose і оновлює адреси web при масштабуванні. Немає container_name та прив’язки web до хостового порту. Кожна репліка: cpus 1.5, mem_limit 1g, 2 worker по 8 потоків, пул до 16 з’єднань на worker. Дві репліки можуть використати до 64 з’єднань PostgreSQL.

Фінальна стадія Debian 12 slim з дайджестом, Python із Debian, без компіляторів і pip; пакети встановлюються в builder. Користувач uid 10001. Дайджест фіксує базовий шар, але не робить весь образ бітово відтворюваним: apt-репозиторії та транзитивні залежності можуть оновлюватися. Повторна збірка порівнює саме базові RootFS layers та зберігає BuildKit лог.

## Етап 2 Реалізація

Flask реалізує шість ендпоінтів. SQL параметризований, стан лише в PostgreSQL, транзакції комітяться пулом після успішного виходу. Валідація має повідомлення за полями. Окрема перевірка виправлень: correction-checks.txt (11 тестів; це не журнал Docker-серії). Перевірка справжнього SQL CRUD виконується scripts/experiment.py.

## Етап 3 Образ

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

## Етап 4 Стенд

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

## Балансування

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

## Схема

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

## Розмір образу та час запуску

Розмір: 211.266 МБ (docker image inspect Size, десяткові MB).

Три старти: [10.728709299990442, 9.146035899990238, 7.6340090999729] с. Медіана: 9.146 с.

## Етапи 5 і 6 Навантаження

Власний генератор scripts/loadgen.py: глобальна сітка t0+i/rate розподіляється між процесами за номером i. Кожен процес передає запити пулу потоків і не чекає попередніх відповідей. HTTP/1.1 з’єднання повторно використовується кожним потоком, щоб не вичерпувати тимчасові порти Windows. У цій серії хост має 8 логічних ядер; генератор використовував 8 процесів і 512 потоків на процес. Генератор і Docker працювали на одному хості. Для кожного рівня 10 с прогріву, потім 30 с вимірювання, три повтори. У базі перед серією 100 записів, читання одного id. Прогрів окремий, у дані не входить.

Команда окремого прогону, наприклад для 100 rps: `python scripts/loadgen.py http://127.0.0.1:18080/vaccinations/1 --rate 100 --warmup 10 --duration 30 --output results/run-100.json`. Повна автоматизована серія з підняттям стенду, перевірками, трьома повторами для 10/100/500 rps та формуванням звіту запускається командою `python -X utf8 scripts/experiment.py --reset-lab-data --threads 512`.

Досягнута інтенсивність — кількість відповідей, завершених у 30-секундному вікні, поділена на 30; p50/p95/p99 та помилки обчислені для всіх запитів серії, включно з завершеними після вікна. Тайм-аут — 15 с, статус 0 означає транспортну помилку. Додатково зберігаються sent_rps, черга на кінці, затримка планувальника та затримка від запланованого моменту. Якщо sent_rps відстає або lag зростає, обмежений генератор. Перцентилі таблиці — інтерполяція, числа таблиці — медіани трьох повторів.

| Репліки | Задано rps | Досягнуто rps | p50 мс | p95 мс | p99 мс | Не 2xx % |
|---|---|---|---|---|---|---|
| 1 | 10 | 10.000 | 5.588 | 15.475 | 26.471 | 0.000 |
| 1 | 100 | 99.933 | 5.135 | 7.916 | 13.154 | 0.000 |
| 1 | 500 | 431.567 | 1271.186 | 15015.074 | 15028.229 | 61.220 |
| 2 | 10 | 10.000 | 5.339 | 10.347 | 18.278 | 0.000 |
| 2 | 100 | 99.967 | 4.886 | 7.311 | 11.336 | 0.000 |
| 2 | 500 | 441.767 | 313.844 | 7243.417 | 7781.337 | 7.667 |

### Черга генератора та фактичні відправки

| Репліки | Ціль rps | Реально відправлено rps | p95 очікування відправки мс | p95 від планового моменту мс |
|---|---|---|---|---|
| 1 | 10 | 10.000 | 16.389 | 25.892 |
| 1 | 100 | 100.000 | 15.565 | 21.493 |
| 1 | 500 | 499.800 | 23.408 | 15027.190 |
| 2 | 10 | 10.000 | 16.268 | 24.922 |
| 2 | 100 | 99.967 | 15.571 | 20.927 |
| 2 | 500 | 499.767 | 20.776 | 7260.941 |

Усі 18 основних прогонів пройшли контроль відправки: фактична швидкість не нижча за 98% цілі, а p95 затримки відправки не перевищує 100 мс. На 500 rps медіани фактичної відправки — 499.800 rps для однієї репліки та 499.767 rps для двох. Отже, попереднє обмеження пулу генератора в цій серії не спостерігається за цими критеріями. Планове й фактичне відправлення відрізняються на десятки мілісекунд; черга не є буквально нульовою. Критерій застосовується до часу запуску HTTP-запиту на клієнті, а не до окремо виміряного моменту прибуття на сервер.

### Перевірка генератора

| Задано rps | Відправлено rps | Досягнуто rps | p95 lag мс |
|---|---|---|---|
| 10 | 10.000 | 10.000 | 15.688 |
| 100 | 100.000 | 100.000 | 15.685 |
| 500 | 499.767 | 499.767 | 16.551 |

Калібрування 10 rps: успішні відповіді 10.000 rps; помилки 0.000%; критерій 98% потоку та <1% помилок виконано: True.

Калібрування 100 rps: успішні відповіді 100.000 rps; помилки 0.000%; критерій 98% потоку та <1% помилок виконано: True.

Калібрування 500 rps: успішні відповіді 499.767 rps; помилки 0.000%; критерій 98% потоку та <1% помилок виконано: True.

Серія no-op проводиться окремо на тій самій машині. Перевірте близькість sent_rps та achieved_rps до заданої, lag і помилки перед висновком про межу сервісу. Асинхронний Python no-op ендпоінт теж має власну межу, тому його насичення не доводить неспроможність генератора. Генератор і сервіс на одній машині конкурують за ядра; відомості в results/machine.json.

Для 1 реплік рівні з відставанням понад 5%: [500]. Перевіряйте lag, помилки та outstanding_at_end, щоб відрізнити сервіс, генератор і нестабільний прогін.

Для 2 реплік рівні з відставанням понад 5%: [500]. Перевіряйте lag, помилки та outstanding_at_end, щоб відрізнити сервіс, генератор і нестабільний прогін.

Розподіл: results/lb-2.log містить upstream адреси. У сирих відповідях є X-Instance-ID.

Спостережені інстанси: ['5550c1dd8121', 'e55a63c72535']. Підтверджено дві репліки: True.

### Успішна пропускна здатність і розкид повторів

Основна achieved_rps рахує всі завершені спроби у 30-секундному вікні, включно з транспортними помилками (status=0). Тому це не швидкість успішних HTTP-відповідей. Нижче success_rps рахує тільки відповіді 2xx у тому самому вікні. Частка неуспіху в основній таблиці охоплює всі заплановані запити, зокрема завершені після вікна.

| Репліки | Ціль rps | Медіана 2xx rps | Діапазон achieved_rps | Діапазон неуспіхів, % |
|---|---|---|---|---|
| 1 | 10 | 10.000 | 10.000–10.000 | 0.000–0.000 |
| 1 | 100 | 99.933 | 99.933–99.967 | 0.000–0.000 |
| 1 | 500 | 168.633 | 431.567–433.100 | 60.713–68.313 |
| 2 | 10 | 10.000 | 10.000–10.000 | 0.000–0.000 |
| 2 | 100 | 99.967 | 99.967–100.000 | 0.000–0.000 |
| 2 | 500 | 402.433 | 440.767–494.700 | 0.000–24.447 |

На 500 rps для однієї репліки медіанна частка неуспіхів — 61.220%, для двох — 7.667%. У сирих даних є TimeoutError, RemoteDisconnected та окремі HTTP 500/504; у третьому прогоні однієї репліки також зафіксовано дві помилки Windows 10048. Без логів вебпроцесу, часових ресурсних вимірювань і окремого хоста генератора конкретне вузьке місце не встановлено. Спільними залишаються PostgreSQL, Nginx та ресурси хоста. Високі помилки під перевантаженням не підмінюються успішними відповідями.

## Етап 7 Розрахунки

### Прискорення та Карп Флатт

S = X₂ / X₁. Для N=2: e=(1/S−0,5)/0,5 = 2/S−1.

При 10 rps: S=10.000/10.000=1.00000; e=2/1.00000−1=1.00000.

При 100 rps: S=99.967/99.933=1.00033; e=2/1.00033−1=0.99933.

При 500 rps: S=441.767/431.567=1.02363; e=2/1.02363−1=0.95382.

Спільні складові: одна PostgreSQL, один Nginx, мережа та диски хоста. На рівнях, де обидва стенди утримують задану інтенсивність, S≈1 зумовлене обмеженим попитом, і e≈1 не є доказом повної серійності. Метрику інтерпретуємо обережно лише біля насичення. Від’ємне e чи e>1 може означати суперлінійний ефект/погіршення та непридатність простої моделі, не «від’ємну частку коду».

Значення S та e вище обчислено за achieved_rps, тобто швидкістю завершення всіх спроб. Через різну частку помилок на 500 rps вони не є чистою оцінкою прискорення успішного обслуговування і не визначають буквальну частку послідовного коду. Для 2xx медіани становлять 168.633 та 402.433 rps; їх відношення приблизно 2.386. Це описове порівняння за даними серії, а не доказ суперлінійного прискорення: три повтори двох реплік суттєво різняться.

### Закон Літтла

L=λW; W у секундах. Виміряне L — площа sent−completed на вікні, поділена на тривалість. Перевірка на 100 rps, одна репліка. Береться один фактичний повтор з медіанною achieved_rps, щоб не змішувати незалежні медіани.

λ=100.00000 rps; W=0.0073204 с; λW=0.7320418; L виміряне=0.7319295; розбіжність=|0.7319295−0.7320418|/0.7320418×100%=0.015%.

Потік λ визначено за фактичними відправками в межах вікна, а не за цільовими 100 rps. Скінченне вікно обрізає запити на правій межі, а W включає їх повну тривалість; це джерело розбіжності. Закон потребує стаціонарності та стабільного потоку.

### Відкритий і закритий контури

Закритий контур має round(L) одночасних запитів з мінімумом 1; наступний запит потоку лише після відповіді. Це середня спостережена конкуренція відкритого прогону, а не довільна кількість користувачів. Вибирається найменший рівень, де achieved_rps<95% target. Якщо всі рівні утримано, додається діагностичний 1000 rps.

Рівень 500 rps; конкуренція 1744. Відкритий: 431.567 rps, p95=15015.074 мс. Закритий: 217.200 rps, p95=15062.864 мс.

У фактичній серії p95 закритого контуру (15062.864 мс) вищий за p95 відкритого (15015.074 мс). Тому очікуване зменшення затримки не підтверджено. Закритий прогін створено з 1744 одночасними потоками: round(1743.6429892). Фактичні 2xx: відкритий 171.767 rps, закритий 182.667 rps. Перцентилі включають помилки й очікування до тайм-ауту 15 с; закритий генератор має один процес із великою кількістю потоків, тому порівняння також залежить від його ресурсів. Теоретично закритий контур стримує наростання черги, але на цих числах не можна стверджувати, що він дав менший p95.

## Етап 8 Вимога варіанта

Обидва FROM містять перевірений офіційний digest Debian 12 slim. Повторна збірка має той самий незмінний базовий образ. scripts/experiment.py зберігає два логи збірки й порівнює prefix RootFS.Layers образу сервісу з усіма шарами бази. Свідчення results/image.json та build-second.log. Порт хоста налаштовано як 18080, контейнерний порт Nginx — 8080. Дайджест отримано 2026-10-06 з registry-1.docker.io для library/debian:12-slim.

## Етап 9 Журнал перевірки

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

На 10 і 100 rps обидві конфігурації утримували потік без неуспішних спроб. На 500 rps генератор продовжував відправляти близько 500 запитів/с, але стенд у частині повторів відповідав із великими затримками та помилками. Для однієї й двох реплік медіанна achieved_rps становила 431.567 і 441.767 (зростання приблизно 2.36%), а медіанна успішна швидкість 2xx — 168.633 і 402.433 rps. Медіанний p95 зменшився з 15015.074 до 7243.417 мс, частка неуспішних спроб — з 61.220% до 7.667%. Друга репліка покращила успішне обслуговування, але на 500 rps результати нестабільні: один із трьох прогонів двох реплік мав 0% помилок, інші — 24.447% та 7.667%. Спільні компоненти й конкуренція за ресурси хоста обмежують інтерпретацію; точний компонент обмеження не доведено. Закон Літтла на 100 rps узгоджується з виміряним L. У закритому контурі менший p95 у цій серії не підтверджено. Додаткова вимога варіанта 7 підтверджена однаковими базовими шарами двох збірок.

## Відкинуті рішення

1. SQLite — умова вимагає PostgreSQL, потрібна спільна база реплік.
2. In-memory словник — записи губляться після restart, репліки розходяться.
3. Копіювання web2 у Compose — порушує масштабування одним параметром.
4. Навантаження лише фіксованими користувачами — закритий контур знижує надходження під перевантаженням.
5. FROM лише з тегом — тег може змінити базові шари, не виконує варіант 7.

## Використання генеративної моделі

Генеративну модель застосовано для допомоги з проєктуванням, кодом, Docker-конфігурацією, генератором навантаження, тестами та оформленням звіту. Після цього автор перевірила код локальними тестами, CRUD-перевірками, контейнерними запусками та фактичними файлами результатів у `results/`. Дайджест базового образу перевірено окремо, а висновки у звіті побудовано за збереженими вимірюваннями.

## Контрольні питання

1. PUT повністю замінює всі шість полів. PATCH передавав би лише зміни, не вимагав би решти полів.
2. Конфлікт створення з наявним id — 409 Conflict. У цьому API id клієнта заборонений і повертає 400; PostgreSQL генерує його сам.
3. Шари містять файлові зміни інструкцій. Зміна раннього COPY інвалідує пізніші кеші, тому requirements копіюється до app.py.
4. down зберігає іменований том; down -v видаляє його; видалення контейнера db не видаляє named volume.
5. Звичайний depends_on гарантує порядок старту, але не готовність; потрібні healthcheck і condition service_healthy.
6. EXPOSE документує порт; ports публікує його на хост. База доступна як db:5432 у мережі Compose.
7. Відкритий генератор планує надходження незалежно від відповіді. Фіксовані користувачі зменшують потік, коли відповіді повільні, приховуючи затримки.
8. Зміни після другої репліки визначаються лише фактичною таблицею вище. Спільні PostgreSQL та Nginx можуть обмежувати приріст.
9. e — ефективна частка роботи без виграшу від паралелізму за моделлю. Окрема база могла б зменшити спільну межу, але додала б узгодження та не гарантувала лінійне прискорення.
10. Поблизу насичення вільна обслуговувальна потужність зменшується; черги зростають нелінійно. У простій M/M/1 моделі W=1/(μ−λ), що різко зростає при λ→μ.

