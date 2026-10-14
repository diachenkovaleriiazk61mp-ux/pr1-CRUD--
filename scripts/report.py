import json
import statistics
from pathlib import Path
from collections import Counter
from loadgen import summarize, validity
from report_polish import polish

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results'

def read(name):
    path = OUT / name
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else None

def load_run(name):
    data = read(name)
    if data and data.get('rows'):
        old = data['summary']
        data['summary'] = summarize(data['rows'], old['duration'], old.get('target_rps'))
    return data

def fmt(value, places=3):
    return '—' if value is None else f'{value:.{places}f}'

def med(runs, key):
    values = [run['summary'].get(key) for run in runs]
    return statistics.median(values) if values and all(v is not None for v in values) else None

def compare_closed(closed, runs):
    """Locate the original open reference without changing the selected experiment."""
    if not closed or 'open_reference' not in closed:
        return None
    old = closed['open_reference']
    candidates = runs.get((1, closed['rate']), [])
    for run in candidates:
        s = run['summary']
        if abs(s['measured_L']-old['measured_L']) < 1e-7 and abs(s['mean_ms']-old['mean_ms']) < 1e-7:
            return s
    extra = load_run(f"open-extra-{closed['rate']}.json")
    return extra['summary'] if extra else None

def main():
    parts = []
    def add(text):
        parts.append(text)
    author = json.loads((ROOT/'author.json').read_text(encoding='utf-8-sig'))
    series = read('series.json')
    add('# Практична робота 1. Проєктування і розгортання CRUD-сервісу\n\n'
        f"Варіант 7 — запис про вакцинацію. Виконала: {author['student']}, група {author['group']}.\n\n"
        'Дисципліна: «Високопродуктивні розподілені обчислювальні системи».')
    add('## Стан і метод обробки\n\n'
        f"Стан збереженої серії: `{series['status'] if series else 'не визначено'}`. "
        'Цей звіт заново обчислює показники з rows у JSON, не змінюючи сирі записи або старі summary. '
        'Тому старі summary версії 2 можуть відрізнятися від таблиці: у них achieved_rps включав транспортні помилки. '
        'Виправлена методика — версія 3. Для повторного формування достатньо `python -X utf8 scripts/report.py`.')
    design = (ROOT/'DESIGN.md').read_text(encoding='utf-8-sig')
    design = '\n'.join('#'+line if line.startswith('#') else line for line in design.splitlines())
    add('## Етап 1. Проєктування\n\n'+design)
    add('## Етап 2. Реалізація\n\nШість ендпоінтів реалізовано у app.py. '
        'SQL параметризований, дані зберігаються у PostgreSQL. Валідація виконується до SQL. '
        'GET /healthz перевіряє базу запитом SELECT 1. PUT потребує всіх полів; повторний DELETE повертає 404.')
    for title, filename, language in (
        ('Етап 3. Образ','Dockerfile','dockerfile'),('Контекст збірки','.dockerignore','text'),
        ('Етап 4. Стенд','docker-compose.yml','yaml'),('Балансувальник','nginx.conf','nginx'),
        ('Автоматична схема','schema.sql','sql')):
        add(f'## {title}\n\n```{language}\n{(ROOT/filename).read_text(encoding="utf-8-sig").rstrip()}\n```')
    add('## Інструкція запуску\n\nWindows: '
        '`powershell -ExecutionPolicy Bypass -File .\\start.ps1`. Для двох реплік додати `-Replicas 2`. '
        'Linux/macOS: `sh start.sh` або `sh start.sh 2` (потрібен Python 3 для створення пароля). '
        'Потрібні Docker із Linux containers, Compose v2 та доступ до реєстрів образів. '
        'Скрипт створює некомітований .env із випадковим паролем і виконує збірку та запуск. '
        'Зовнішня точка входу — http://localhost:18080; порт можна змінити у .env.')
    image, startup = read('image.json'), read('startup.json')
    add('## Розмір образу і запуск\n\n'+
        (f"Розмір за docker image inspect: {fmt(image['size_bytes']/1_000_000)} MB. " if image else 'Розмір не виміряно. ')+
        (f"Три старти на порожньому томі з готовими образами: {', '.join(fmt(x) for x in startup['seconds'])} с; медіана {fmt(statistics.median(startup['seconds']))} с." if startup else 'Час не виміряно.'))
    if startup and startup.get('method') == 'concurrent_health_poll':
        add('Готовність перевірялася паралельно з docker compose up через /healthz з інтервалом 0.1 с. '
            'Виміряно час до першої зафіксованої відповіді 200, включно з виконанням команди запуску.')
    elif startup:
        add('У збереженій серії /healthz опитувався після завершення команди docker compose up. '
            'Це верхня оцінка часу готовності, а не точний час першої доступності. '
            'Для відповідності методиці потрібно повторити лише три вимірювання запуску: '
            '`python -X utf8 scripts/experiment.py --reset-lab-data --startup-only`. '
            'Команда видаляє дані цієї лабораторної; сирі результати навантаження зберігаються.')
    machine = read('machine.json')
    add('## Етапи 5–6. Навантаження\n\nВласний scripts/loadgen.py планує моменти t0+i/rate '
        'незалежно від відповідей. Процеси ділять сітку, HTTP-запити виконує пул потоків. '
        'Перед серією створюється 100 записів, вимірюється GET /vaccinations/{id}. '
        'Для кожної конфігурації: 10 с прогріву, окремі 30 с вимірювання, три повтори; '
        'рівні 10/100/500 rps, одна і дві репліки. Прогрів не входить у результати.\n\n'
        'Повна серія: `python -X utf8 scripts/experiment.py --reset-lab-data --threads 512`. '
        'Ця команда видаляє дані лабораторної для перевірок порожньої бази. '
        'Окремий прогін: `python -X utf8 scripts/loadgen.py http://127.0.0.1:18080/vaccinations/1 '
        '--rate 100 --warmup 10 --duration 30 --threads 512 --output results/run-100.json`.')
    if machine:
        add(f"Машина: {machine['platform']}; логічних ядер: {machine['cores']}. "
            f"Процесів генератора: {machine['generator_processes'] or machine['cores']}; "
            f"потоків на процес: {machine['generator_threads']}. "
            f"Генератор на тому самому хості: {machine['generator_same_host']}. Конкуренція за CPU впливає на верхній рівень.")
    add('### Визначення метрик\n\n'
        '- Досягнута швидкість achieved_rps: отримані HTTP-відповіді (статуси 100–599), завершені у 30-секундному вікні, / 30. HTTP 500/504 враховуються як відповіді, але не як успішні.\n'
        '- success_rps: відповіді 2xx у тому самому вікні / 30.\n'
        '- status=0: HTTP-відповідь не отримано. Тайм-аут чи обрив з’єднання виключено з achieved_rps і перцентилів HTTP-відповідей.\n'
        '- p50/p95/p99: час від фактичного початку HTTP-запиту до повного читання відповіді для всіх отриманих відповідей прогону, включно із завершеними після вікна.\n'
        '- Не 2xx: частка неуспішних HTTP-статусів серед отриманих відповідей. Транспортні помилки та загальні неуспішні спроби наведено окремо.\n'
        '- completed_rps: завершені спроби будь-якого результату / 30; лише діагностичний показник.\n'
        '- У таблицях наведено медіани трьох повторів; вони не обов’язково належать одному повтору.\n'
        '- Тайм-аут HTTP — 15 с; затримка від планового моменту та час до завершення всіх спроб збережені у rows.')
    runs = {}
    invalid = []
    add('| Репліки | Ціль rps | HTTP-відповіді rps | p50 мс | p95 мс | p99 мс | Не 2xx, % |\n|---|---|---|---|---|---|---|')
    for n in (1,2):
        for rate in (10,100,500):
            values = [load_run(f'open-{n}-{rate}-{i}.json') for i in (1,2,3)]
            if not all(values):
                add(f'| {n} | {rate} | не виміряно | — | — | — | — |')
                continue
            runs[n,rate] = values
            for i,v in enumerate(values,1):
                if validity(v['summary']): invalid.append(f'open-{n}-{rate}-{i}.json')
            keys=('achieved_rps','p50_ms','p95_ms','p99_ms')
            pct=med(values,'non_2xx_fraction')
            add(f'| {n} | {rate} | '+' | '.join(fmt(med(values,k)) for k in keys)+f' | {fmt(None if pct is None else pct*100)} |')
    add('### Фактична відправка і помилки\n\n| Репліки | Ціль rps | Відправлено rps | p95 lag мс | 2xx rps | Транспортні помилки, % | Усі неуспішні спроби, % |\n|---|---|---|---|---|---|---|')
    for (n,rate),vs in runs.items():
        add(f'| {n} | {rate} | '+ ' | '.join(fmt(med(vs,k)) for k in ('sent_rps','p95_scheduler_lag_ms','success_rps'))+
            f" | {fmt(med(vs,'transport_error_fraction')*100)} | {fmt(med(vs,'failure_fraction')*100)} |")
    add('Контроль відправки: sent_rps ≥ 98% цілі та p95 lag ≤ 100 мс. '+
        ('Не пройшли: '+', '.join(invalid)+'. Висновки про межу сервісу для них обмежені.' if invalid else
         ('Усі наявні основні прогони пройшли контроль.' if runs else 'Основних прогонів немає.'))+
        ' Це час запуску HTTP-запиту на клієнті; момент прибуття на сервер окремо не вимірювався.')
    add('### Калібрування no-op\n\n| Ціль rps | Відправлено rps | HTTP rps | 2xx rps | p95 lag мс |\n|---|---|---|---|---|')
    for rate in (10,100,500):
        v=load_run(f'noop-{rate}.json')
        add(f'| {rate} | '+(' | '.join(fmt(v['summary'][k]) for k in ('sent_rps','achieved_rps','success_rps','p95_scheduler_lag_ms')) if v else '— | — | — | —')+' |')
    instances=set()
    for (n,rate),vs in runs.items():
        if n==2:
            for v in vs: instances.update(v['summary']['instances'])
    add('### Розподіл і розкид\n\n'+f"Два інстанси у відповідях: {sorted(instances)}. Логи upstream: results/lb-2.log.\n\n"
        '| Репліки | Ціль rps | Діапазон HTTP rps | Діапазон усіх неуспіхів, % |\n|---|---|---|---|')
    for (n,rate),vs in runs.items():
        x=[v['summary']['achieved_rps'] for v in vs];e=[v['summary']['failure_fraction']*100 for v in vs]
        add(f'| {n} | {rate} | {fmt(min(x))}–{fmt(max(x))} | {fmt(min(e))}–{fmt(max(e))} |')
    errors=Counter()
    for vs in runs.values():
        for v in vs:
            errors.update(row.get('error') for row in v['rows'] if row.get('error'))
    if errors:
        add('Зафіксовані транспортні помилки (усі основні прогони):\n\n'+
            '\n'.join(f'- `{error}`: {count}.' for error,count in errors.most_common()))
    add('## Етап 7. Розрахунки\n\n### Прискорення і Карп–Флатт\n\n'
        'X — медіанна швидкість отриманих HTTP-відповідей, включно з неуспішними HTTP-статусами. '
        'Транспортні помилки виключено. S=X₂/X₁; N=2; e=(1/S−0.5)/0.5=2/S−1.')
    for rate in (10,100,500):
        if (1,rate) in runs and (2,rate) in runs:
            x1,x2=med(runs[1,rate],'achieved_rps'),med(runs[2,rate],'achieved_rps')
            if x1>0 and x2>0:
                speed=x2/x1
                add(f'При {rate} rps: S={fmt(x2)}/{fmt(x1)}={fmt(speed,5)}; e=2/{fmt(speed,5)}−1={fmt(2/speed-1,5)}.')
            else: add(f'При {rate} rps: S/e не визначено через нульову HTTP-швидкість.')
    add('Спільні компоненти — одна PostgreSQL, Nginx, мережа і ресурси хоста. '
        'На малому попиті S≈1 не означає повну серійність. Якщо e від’ємне, воно не є від’ємною часткою коду: '
        'це ознака непридатності простої моделі до цього вимірювання. При великій частці помилок і розкиді '
        'S описує зміну HTTP-швидкості, але не доводить частку послідовної роботи. Окремо наведено швидкість 2xx.')
    add('### Закон Літтла\n\nL=λW. L вимірюється як площа (sent−completed) за вікно / тривалість. '
        'Для узгодженості W — середній час завершення всіх спроб, а λ — фактичні відправки. '
        'На рівні 100 rps без помилок це одночасно середній час HTTP-відповіді.')
    if (1,100) in runs:
        s=sorted(runs[1,100],key=lambda v:v['summary']['achieved_rps'])[1]['summary']
        lam,w,l=s['sent_rps'],s['mean_ms']/1000,s['measured_L'];pred=lam*w
        add(f'λ={fmt(lam,5)} rps; W={fmt(w,7)} с; λW={fmt(pred,7)}; '
            f'L виміряне={fmt(l,7)}; розбіжність=|{fmt(l,7)}−{fmt(pred,7)}|/{fmt(pred,7)}×100%={fmt(abs(l-pred)/pred*100)}%.')
    add('Обрано один повтор із медіанною HTTP-швидкістю; незалежні медіани не змішуються. '
        'Скінченне вікно обрізає незавершені запити при обчисленні L, а W включає їх повний час. '
        'Закон застосовний до стабільного потоку; при наростанні черги його стаціонарна інтерпретація обмежена.')
    add('### Відкритий і закритий контури\n\n'
        'У закритому контурі фіксовано round(L) одночасних потоків, мінімум 1; '
        'наступний запит потоку лише після завершення попереднього. '
        'Новий сценарій обирає перевантажений рівень за HTTP-швидкістю, не за кількістю завершених помилок.')
    closed=load_run('closed.json');o=compare_closed(closed,runs)
    if o:
        c=closed['summary']
        add(f"Рівень {closed['rate']} rps; конкуренція {closed['concurrency']}=round({fmt(o['measured_L'],7)}).\n\n"
            '| Режим | HTTP rps | 2xx rps | p95 HTTP, мс | p95 усіх спроб, мс |\n|---|---|---|---|---|\n'+
            '\n'.join(f"| {name} | {fmt(s['achieved_rps'])} | {fmt(s['success_rps'])} | {fmt(s['p95_ms'])} | {fmt(s['attempt_p95_ms'])} |" for name,s in [('Відкритий',o),('Закритий',c)]))
        if c['p95_ms'] is not None and o['p95_ms'] is not None:
            add('У цій серії p95 HTTP-відповідей у закритому контурі '+
                ('нижчий' if c['p95_ms']<o['p95_ms'] else 'не нижчий')+
                ' за відкритий. Теоретично зворотний зв’язок закритого контуру зменшує надходження при '
                'сповільненні відповідей і стримує наростання черги. Цей механізм не гарантує менший виміряний p95: '
                'закритий генератор має один процес і багато потоків; значні помилки змінюють склад отриманих відповідей. '
                'p95 HTTP виключає запити без відповіді, тому для контролю цензурування поруч наведено p95 усіх спроб. '
                'Висновок про меншу затримку робиться лише за фактичними числами.')
    else: add('Порівняння не виконано або відкритий еталон не знайдено серед сирих результатів.')
    add('## Етап 8. Додаткова вимога варіанта\n\n'
        'Обидві стадії Dockerfile використовують Debian 12 slim із digest. Ліміти web: 1.5 CPU, 1 GB. '
        'results/build-first.log і build-second.log зберігають збірки, image.json — базові RootFS-шари. '+
        (f"Порівняння однакових базових шарів: {image['same_base_layers']}. Digest: `{image['base_digest']}`." if image else 'Підтвердження шарів відсутнє.'))
    add('## Етап 9. Журнал перевірки\n\n'
        'Сценарій перевіряє CRUD, валідацію, збереження після down/up, порожню базу після down -v/up '
        'і healthz=503 при зупиненій базі. Фактичні відповіді нижче; повні дані — results/checks.json.')
    checks=read('checks.json')
    if checks:
        add('| Метод | Шлях | Код |\n|---|---|---|\n'+ '\n'.join(f"| {v['method']} | `{v['path']}` | {v['status']} |" for v in checks))
        for v in checks: add('```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```')
    else: add('Журнал відсутній.')
    add('## Висновок')
    for n in (1,2):
        overloaded=[rate for rate in (10,100,500) if (n,rate) in runs and med(runs[n,rate],'achieved_rps')<.95*rate]
        add(f'Для {n} реплік рівні з відставанням HTTP-швидкості понад 5%: {overloaded or "не спостерігалось"}.')
    if (1,500) in runs and (2,500) in runs:
        for n in (1,2):
            vs=runs[n,500]
            add(f"При 500 rps, {n} реплік: HTTP-швидкість {fmt(med(vs,'achieved_rps'))} rps; "
                f"2xx {fmt(med(vs,'success_rps'))} rps; p95 HTTP {fmt(med(vs,'p95_ms'))} мс; "
                f"транспортні помилки {fmt(med(vs,'transport_error_fraction')*100)}%; усі неуспіхи {fmt(med(vs,'failure_fraction')*100)}%.")
    add('Наявність спільної бази та балансувальника не доводить конкретне вузьке місце. '
        'На верхньому рівні враховано помилки, розкид повторів і конкуренцію генератора зі стендом за ресурси. '
        'Без додаткових логів вебпроцесу та ресурсних вимірювань точний компонент обмеження не встановлено. '
        'Отримані числа не підмінюються очікуваним подвоєнням швидкості або очікуваним меншим p95.')
    add('## Відкинуті рішення\n\n1. SQLite — умова вимагає спільну PostgreSQL.\n'
        '2. Словник у пам’яті — дані губляться і не є спільними для реплік.\n'
        '3. Копіювання web2 — суперечить масштабуванню параметром.\n'
        '4. Лише фіксовані користувачі — це закритий контур, який зменшує потік під перевантаженням.\n'
        '5. Базовий образ лише за тегом — не виконує вимогу digest.')
    add('## Контрольні питання\n\n'
        '1. PUT замінює всі поля; PATCH передавав би лише зміни.\n'
        '2. Конфлікт із наявним ID зазвичай 409; це API забороняє клієнтський ID із 400 і генерує його у базі.\n'
        '3. Шари зберігають файлові зміни; рання зміна інвалідує наступний кеш, тому залежності копіюються раніше коду.\n'
        '4. down зберігає named volume; down -v видаляє його; видалення контейнера не видаляє named volume.\n'
        '5. depends_on без service_healthy задає порядок, а не готовність бази.\n'
        '6. EXPOSE документує порт, ports публікує його. База доступна за db:5432 у мережі Compose.\n'
        '7. Відкритий контур планує потік незалежно від відповіді, закритий уповільнює надходження при зростанні затримки.\n'
        '8. Зміни після другої репліки визначено таблицями; спільні база, Nginx і ресурси хоста.\n'
        '9. e — оцінка за моделлю, не буквальна частка коду при помилках і суперлінійних ефектах. Окремі бази можуть змінити обмеження, але додають узгодження.\n'
        '10. Біля насичення черга зростає нелінійно; для M/M/1 W=1/(μ−λ).')
    (ROOT/'REPORT.md').write_text(polish('\n\n'.join(parts)),encoding='utf-8')

if __name__=='__main__':
    main()
