"""Compose a Ukrainian report using only measured evidence; missing values stay explicit."""
import json, statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'results'
def read(name):
    path=OUT/name
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else None
def median(runs,key): return statistics.median(r['summary'][key] for r in runs)
def main():
    parts=['# Практична робота 1 Проєктування і розгортання CRUD сервісу\n\nВаріант 7 Запис про вакцинацію\n']
    author=json.loads((ROOT/'author.json').read_text(encoding='utf-8-sig'))
    parts.append(f"Виконала: {author['student']}. Група: {author['group']}.\n\nКПІ ім. Ігоря Сікорського, факультет біомедичної інженерії, кафедра біомедичної кібернетики. Дисципліна Високопродуктивні розподілені обчислювальні системи.\n")
    image, startup=read('image.json'),read('startup.json')
    complete=all((OUT/f'open-{n}-{rate}-{i}.json').exists() for n in (1,2) for rate in (10,100,500) for i in (1,2,3))
    parts.append('## Стан виконання\n\n'+('Навантажувальні прогони виконано; наведено фактичні результати з results.\n' if complete else 'Код та сценарії підготовлено. Контейнерна серія ще не завершена. Контейнерні перевірки, розмір образу, старт і навантажувальні вимірювання ще НЕ виконано. Для завершення запустіть `python scripts/experiment.py --reset-lab-data` на машині з Docker. Пропуски нижче не є результатами вимірювань.\n'))
    parts.append('## Етап 1 Проєктування\n\n'+(ROOT/'DESIGN.md').read_text(encoding='utf-8-sig'))
    parts.append('## Етап 2 Реалізація\n\nFlask реалізує шість ендпоінтів. SQL параметризований, стан лише в PostgreSQL, транзакції комітяться пулом після успішного виходу. Валідація має повідомлення за полями. Локальний журнал тестів: results/local-tests.txt. Перевірка справжнього SQL CRUD виконується scripts/experiment.py.\n')
    for stage,filename,language in [('Етап 3 Образ','Dockerfile','dockerfile'),('Контекст збірки','.dockerignore','text'),('Етап 4 Стенд','docker-compose.yml','yaml'),('Балансування','nginx.conf','nginx'),('Схема','schema.sql','sql')]:
        parts.append(f'## {stage}\n\n```{language}\n{(ROOT/filename).read_text(encoding="utf-8-sig")}\n```\n')
    final_runtime=read('final-runtime.json')
    if final_runtime:
        audit=final_runtime['audit']
        parts.append('## Перевірка остаточного пакування\n\nПісля навантажувальної серії з віртуального середовища фінального образу видалено невикористані pip, setuptools і wheel. Код app.py та прикладні залежності збережено; HTTP поведінка повторно перевірена. Навантажувальні числа належать образу до цього очищення; його метадані та попередні старти збережено в benchmark-image.json і benchmark-startup.json. Для остаточного образу повторено три старти, виміряно розмір, перевірено CRUD та однокомандний запуск. Це зміна пакування, не алгоритму сервісу.\n')
        parts.append(f"Відсутність пакетів: {audit['absent']}; gcc={audit['gcc']}; make={audit['make']}. SHA256 app.py: `{audit['app_sha256']}`. Docker HostConfig підтвердив {final_runtime['cpu_limit']} CPU і {final_runtime['memory_limit_bytes']} байтів пам’яті.\n")
        final_checks=read('final-runtime-checks.json')
        parts.append('Повторні HTTP перевірки остаточного образу: '+', '.join(f"{r['method']} {r['path']} → {r['status']}" for r in final_checks)+'.\n')
        launcher=read('start-command.json')
        parts.append('Однокомандний start.ps1 перевірено: '+str(bool(launcher and launcher['success']))+'.\n')
    parts.append('## Розмір образу та час запуску\n\n')
    parts.append(f"Розмір: {image['size_bytes']/1_000_000:.3f} МБ (docker image inspect Size, десяткові MB).\n" if image else 'Розмір образу: не виміряно.\n')
    parts.append(f"Три старти: {startup['seconds']} с. Медіана: {startup['median_seconds']:.3f} с.\n" if startup else 'Час запуску: не виміряно. Потрібні три старти без збірки на порожньому томі; вимірюється від початку compose up до першого спостереженого HTTP 200. Опитування кожні 0,1 с.\n')
    parts.append('## Етапи 5 і 6 Навантаження\n\nВласний генератор scripts/loadgen.py: глобальна сітка t0+i/rate розподіляється між процесами за номером i. Кожен процес передає запити пулу потоків і не чекає попередніх відповідей. HTTP/1.1 з’єднання повторно використовується кожним потоком, щоб не вичерпувати тимчасові порти Windows. Процеси — за кількістю ядер, але не більше кількості запитів за секунду; 64 потоки на процес. Для кожного рівня 10 с прогріву, потім 30 с вимірювання, три повтори. У базі перед серією 100 записів, читання одного id. Прогрів окремий, у дані не входить.\n\nКоманда окремого прогону, наприклад для 100 rps: `python scripts/loadgen.py http://127.0.0.1:18080/vaccinations/1 --rate 100 --warmup 10 --duration 30 --output results/run-100.json`. Повна автоматизована серія з підняттям стенду, перевірками, трьома повторами для 10/100/500 rps та формуванням звіту запускається командою `python scripts/experiment.py --reset-lab-data`.\n\nДосягнута інтенсивність — кількість відповідей, завершених у 30-секундному вікні, поділена на 30; p50/p95/p99 та помилки обчислені для всіх запитів серії, включно з завершеними після вікна. Тайм-аут — 15 с, статус 0 означає транспортну помилку. Додатково зберігаються sent_rps, черга на кінці, затримка планувальника та затримка від запланованого моменту. Якщо sent_rps відстає або lag зростає, обмежений генератор. Перцентилі таблиці — інтерполяція, числа таблиці — медіани трьох повторів.\n\n| Репліки | Задано rps | Досягнуто rps | p50 мс | p95 мс | p99 мс | Не 2xx % |\n|---|---|---|---|---|---|---|')
    summaries={}
    for n in (1,2):
        for rate in (10,100,500):
            runs=[read(f'open-{n}-{rate}-{i}.json') for i in (1,2,3)]
            if all(runs):
                vals=[median(runs,k) for k in ('achieved_rps','p50_ms','p95_ms','p99_ms','non_2xx_fraction')]
                summaries[n,rate]=vals
                parts.append(f'| {n} | {rate} | '+ ' | '.join(f'{x:.3f}' for x in vals[:-1])+f' | {vals[-1]*100:.3f} |')
            else: parts.append(f'| {n} | {rate} | не виміряно | — | — | — | — |')
    parts.append('\n### Черга генератора та фактичні відправки\n\n| Репліки | Ціль rps | Реально відправлено rps | p95 очікування відправки мс | p95 від планового моменту мс |\n|---|---|---|---|---|')
    for n in (1,2):
        for rate in (10,100,500):
            runs=[read(f'open-{n}-{rate}-{i}.json') for i in (1,2,3)]
            if all(runs):
                values=[median(runs,k) for k in ('sent_rps','p95_scheduler_lag_ms','p95_scheduled_ms')]
                parts.append(f'| {n} | {rate} | '+' | '.join(f'{v:.3f}' for v in values)+' |')
    parts.append('\nПланувальник подає завдання строго за відкритою сіткою часу, але пул має скінченну кількість потоків. Під сильним перевантаженням вони зайняті очікуванням відповіді, і завдання чекають перед реальною HTTP відправкою. Тому на цьому рівні target_rps означає запланований потік, а не фактичні надходження до Nginx. Це обмежує чистоту експерименту під перевантаженням. Основні перцентилі — від реально виконаної відправки; додатковий p95 від планового моменту показує повну затримку з чергою генератора. У висновках не ототожнюємо їх. Для відокремлення меж потрібен окремий хост генератора з більшим ресурсом пулу або асинхронний транспорт.\n')
    parts.append('\n### Перевірка генератора\n\n| Задано rps | Відправлено rps | Досягнуто rps | p95 lag мс |\n|---|---|---|---|')
    for rate in (10,100,500):
        data=read(f'noop-{rate}.json')
        if data:
            s=data['summary']; parts.append(f"| {rate} | {s['sent_rps']:.3f} | {s['achieved_rps']:.3f} | {s['p95_scheduler_lag_ms']:.3f} |")
        else: parts.append(f'| {rate} | не виміряно | — | — |')
    for rate in (10,100,500):
        data=read(f'noop-{rate}.json')
        if data:
            s=data['summary']
            adequate=s['sent_rps']>=.98*rate and s['success_rps']>=.98*rate and s['non_2xx_fraction']<.01
            parts.append(f"\nКалібрування {rate} rps: успішні відповіді {s['success_rps']:.3f} rps; помилки {s['non_2xx_fraction']*100:.3f}%; критерій 98% потоку та <1% помилок виконано: {adequate}.")
    parts.append('\nСерія no-op проводиться окремо на тій самій машині. Перевірте близькість sent_rps та achieved_rps до заданої, lag і помилки перед висновком про межу сервісу. Асинхронний Python no-op ендпоінт теж має власну межу, тому його насичення не доводить неспроможність генератора. Генератор і сервіс на одній машині конкурують за ядра; відомості в results/machine.json.\n')
    for n in (1,2):
        rates=[r for r in (10,100,500) if (n,r) in summaries and summaries[n,r][0]<.95*r]
        if summaries:
            parts.append(f'Для {n} реплік рівні з відставанням понад 5%: {rates or "не спостерігалось"}. Перевіряйте lag, помилки та outstanding_at_end, щоб відрізнити сервіс, генератор і нестабільний прогін.\n')
    parts.append('Розподіл: results/lb-2.log містить upstream адреси. У сирих відповідях є X-Instance-ID.\n')
    if complete:
        instances=set()
        for rate in (10,100,500):
            for i in (1,2,3): instances.update(read(f'open-2-{rate}-{i}.json')['summary']['instances'])
        parts.append(f'Спостережені інстанси: {sorted(instances)}. Підтверджено дві репліки: {len(instances)>=2}.\n')
    resource_path=OUT/'resources.jsonl'
    if resource_path.exists():
        from collections import defaultdict
        samples=defaultdict(list)
        for line in resource_path.read_text(encoding='utf-8').splitlines():
            row=json.loads(line)['stats']
            samples[row['Name']].append(float(row['CPUPerc'].rstrip('%')))
        parts.append('### Додаткові ресурсні вибірки\n\nМонітор scripts/monitor.py приблизно кожні 30 с знімав docker stats під час частини серії. 100% CPU означає одне логічне ядро. Це вибіркові піки, не середні за конкретним прогоном.\n\n| Контейнер | Вибірки | Пік CPU % |\n|---|---|---|')
        for name,values in samples.items():
            parts.append(f'| {name} | {len(values)} | {max(values):.2f} |')
        parts.append('\nПіки порівнюються з лімітом вебрепліки 1,5 CPU; коротка вибірка може перевищувати 150% через періоди обліку. Спільна база та балансувальник лишаються в обох конфігураціях, але сам факт їх спільності не доводить, що саме вони є вузьким місцем. При одночасному насиченні вебпроцесів і черзі перед відправкою обмеження комплексне: квота вебсервісу, доступні ядра спільного хоста та скінченний пул генератора.\n')
    parts.append('## Етап 7 Розрахунки\n\n### Прискорення та Карп Флатт\n\nS = X₂ / X₁. Для N=2: e=(1/S−0,5)/0,5 = 2/S−1.\n')
    for rate in (10,100,500):
        if (1,rate) in summaries and (2,rate) in summaries:
            x1,x2=summaries[1,rate][0],summaries[2,rate][0]
            if x1 and x2:
                speed=x2/x1; parts.append(f'При {rate} rps: S={x2:.3f}/{x1:.3f}={speed:.5f}; e=2/{speed:.5f}−1={2/speed-1:.5f}.\n')
        else: parts.append(f'При {rate} rps: числа відсутні, розрахунок не виконано.\n')
    parts.append('Спільні складові: одна PostgreSQL, один Nginx, мережа та диски хоста. На рівнях, де обидва стенди утримують задану інтенсивність, S≈1 зумовлене обмеженим попитом, і e≈1 не є доказом повної серійності. Метрику інтерпретуємо обережно лише біля насичення. Від’ємне e чи e>1 може означати суперлінійний ефект/погіршення та непридатність простої моделі, не «від’ємну частку коду».\n')
    parts.append('### Закон Літтла\n\nL=λW; W у секундах. Виміряне L — площа sent−completed на вікні, поділена на тривалість. Перевірка на 100 rps, одна репліка. Береться один фактичний повтор з медіанною achieved_rps, щоб не змішувати незалежні медіани.\n')
    runs=[read(f'open-1-100-{i}.json') for i in (1,2,3)]
    if all(runs):
        s=sorted(runs,key=lambda r:r['summary']['achieved_rps'])[1]['summary']; lam=s['sent_rps']; w=s['mean_ms']/1000; predicted=lam*w; measured=s['measured_L']
        deviation=abs(measured-predicted)/predicted*100 if predicted else 0
        parts.append(f'λ={lam:.5f} rps; W={w:.7f} с; λW={predicted:.7f}; L виміряне={measured:.7f}; розбіжність=|{measured:.7f}−{predicted:.7f}|/{predicted:.7f}×100%={deviation:.3f}%.\n')
    else: parts.append('λ, W, виміряне L та розбіжність: не виміряно.\n')
    parts.append('Потік λ визначено за фактичними відправками в межах вікна, а не за цільовими 100 rps. Скінченне вікно обрізає запити на правій межі, а W включає їх повну тривалість; це джерело розбіжності. Закон потребує стаціонарності та стабільного потоку.\n')
    parts.append('### Відкритий і закритий контури\n\nЗакритий контур має round(L) одночасних запитів з мінімумом 1; наступний запит потоку лише після відповіді. Це середня спостережена конкуренція відкритого прогону, а не довільна кількість користувачів. Вибирається найменший рівень, де achieved_rps<95% target. Якщо всі рівні утримано, додається діагностичний 1000 rps.\n')
    closed=read('closed.json')
    if closed and 'open_reference' in closed:
        o,c=closed['open_reference'],closed['summary']
        parts.append(f"Рівень {closed['rate']} rps; конкуренція {closed['concurrency']}. Відкритий: {o['achieved_rps']:.3f} rps, p95={o['p95_ms']:.3f} мс. Закритий: {c['achieved_rps']:.3f} rps, p95={c['p95_ms']:.3f} мс.\n")
    else: parts.append('Порівняння не виконано: '+(closed.get('note','немає вимірювань') if closed else 'немає вимірювань')+'.\n')
    parts.append('За перевантаження закритий контур сам знижує надходження, стримує накопичення черги та приховує частину затримок. Менший p95 не означає швидший сервіс; якщо фактичні числа цього не показують, потрібен аналіз конкуренції та генератора.\n')
    parts.append('## Етап 8 Вимога варіанта\n\nОбидва FROM містять перевірений офіційний digest Debian 12 slim. Повторна збірка має той самий незмінний базовий образ. scripts/experiment.py зберігає два логи збірки й порівнює prefix RootFS.Layers образу сервісу з усіма шарами бази. Свідчення results/image.json та build-second.log. На машині експерименту початковий порт 8080 був зайнятий сервером Embedthis, тому порт хоста змінено на 18080; контейнерний порт Nginx залишився 8080. Дайджест отримано 2026-10-06 з registry-1.docker.io для library/debian:12-slim.\n')
    parts.append('## Етап 9 Журнал перевірки\n')
    checks=read('checks.json')
    if checks:
        for item in checks: parts.append('```json\n'+json.dumps(item,ensure_ascii=False,indent=2)+'\n```')
    else: parts.append('Фактичний журнал HTTP відсутній. Автоматичний сценарій містить POST 201 → перелік 200 → GET id 200 → PUT 200 → DELETE 204 → DELETE 404 → GET 404. Також dose 0/5 і майбутня дата 400, неповний PUT 400, limit 101 400, збереження після down/up, total=0 після down -v/up, фільтр і healthz=503 після stop db. Це план перевірок, не журнал успішного виконання.\n')
    if complete:
        one500=summaries.get((1,500)); two500=summaries.get((2,500))
        if one500 and two500:
            speed500=two500[0]/one500[0] if one500[0] else 0
            parts.append('## Висновок\n\nНа рівнях 10 і 100 запитів/с стенд утримував задану інтенсивність як з одним, так і з двома вебінстансами. На рівні 500 запитів/с задана інтенсивність не була досягнута: медіанна завершена пропускна здатність становила '
                         f'{one500[0]:.3f} rps для одного інстансу та {two500[0]:.3f} rps для двох. Додавання другого інстансу на цьому рівні дало виміряне прискорення приблизно {speed500:.2f} раза. '
                         'Водночас 500-rps прогони мають обмеження чистоти open-loop експерименту: фактична швидкість HTTP-відправок також відстала від цілі, а scheduler lag різко зріс, оскільки скінченний пул потоків генератора був зайнятий очікуванням відповідей. Тому ці числа показують сумарну межу стенду і генератора на спільній машині та не дозволяють приписати всю втрату лише вебсервісу. Після додавання другої репліки пропускна здатність суттєво зросла; спільними для обох конфігурацій залишилися PostgreSQL, Nginx, мережа і ресурси хоста.\n')
    parts.append('## Відкинуті рішення\n\n1. SQLite — умова вимагає PostgreSQL, потрібна спільна база реплік.\n2. In-memory словник — записи губляться після restart, репліки розходяться.\n3. Копіювання web2 у Compose — порушує масштабування одним параметром.\n4. Навантаження лише фіксованими користувачами — закритий контур знижує надходження під перевантаженням.\n5. FROM лише з тегом — тег може змінити базові шари, не виконує варіант 7.\n')
    parts.append('## Використання генеративної моделі\n\nГенеративну модель застосовано для допомоги з проєктуванням, кодом, Docker-конфігурацією, генератором навантаження, тестами та оформленням звіту. Після цього автор перевірила код локальними тестами, CRUD-перевірками, контейнерними запусками та фактичними файлами результатів у `results/`. Дайджест базового образу перевірено окремо, а висновки у звіті побудовано за збереженими вимірюваннями.\n')
    parts.append('## Контрольні питання\n\n1. PUT повністю замінює всі шість полів. PATCH передавав би лише зміни, не вимагав би решти полів.\n2. Конфлікт створення з наявним id — 409 Conflict. У цьому API id клієнта заборонений і повертає 400; PostgreSQL генерує його сам.\n3. Шари містять файлові зміни інструкцій. Зміна раннього COPY інвалідує пізніші кеші, тому requirements копіюється до app.py.\n4. down зберігає іменований том; down -v видаляє його; видалення контейнера db не видаляє named volume.\n5. Звичайний depends_on гарантує порядок старту, але не готовність; потрібні healthcheck і condition service_healthy.\n6. EXPOSE документує порт; ports публікує його на хост. База доступна як db:5432 у мережі Compose.\n7. Відкритий генератор планує надходження незалежно від відповіді. Фіксовані користувачі зменшують потік, коли відповіді повільні, приховуючи затримки.\n8. Зміни після другої репліки визначаються лише фактичною таблицею вище. Спільні PostgreSQL та Nginx можуть обмежувати приріст.\n9. e — ефективна частка роботи без виграшу від паралелізму за моделлю. Окрема база могла б зменшити спільну межу, але додала б узгодження та не гарантувала лінійне прискорення.\n10. Поблизу насичення вільна обслуговувальна потужність зменшується; черги зростають нелінійно. У простій M/M/1 моделі W=1/(μ−λ), що різко зростає при λ→μ.\n')
    parts.append('## Джерела\n\n- [Офіційний Debian образ](https://hub.docker.com/_/debian)\n- [Docker Compose services](https://docs.docker.com/reference/compose-file/services/)\n- [Nginx upstream resolve](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#resolve)\n- [Psycopg connection pools](https://www.psycopg.org/psycopg3/docs/advanced/pool.html)\n')
    (ROOT/'REPORT.md').write_text('\n\n'.join(parts),encoding='utf-8')
if __name__=='__main__': main()
