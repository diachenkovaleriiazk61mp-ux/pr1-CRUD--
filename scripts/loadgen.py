"""Own open-loop multiprocessing/thread-pool generator; standard library only."""
import argparse, concurrent.futures as cf, json, math, multiprocessing as mp
import os, sys, time, http.client, threading
from urllib.parse import urlsplit
LOCAL = threading.local()
from pathlib import Path

def request_one(url, planned, origin):
    sent = time.perf_counter()
    error = None
    try:
        parsed = urlsplit(url)
        key = (parsed.scheme, parsed.netloc)
        if getattr(LOCAL, 'key', None) != key or getattr(LOCAL, 'connection', None) is None:
            cls = http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection
            LOCAL.connection = cls(parsed.hostname, parsed.port, timeout=15)
            LOCAL.key = key
        connection = LOCAL.connection
        path = parsed.path or '/'
        if parsed.query:
            path += '?' + parsed.query
        connection.request('GET', path)
        response = connection.getresponse()
        response.read()
        status, instance = response.status, response.getheader('X-Instance-ID', '')
    except Exception as exc:
        status, instance, error = 0, '', repr(exc)
        if getattr(LOCAL, 'connection', None):
            LOCAL.connection.close()
        LOCAL.connection = None
    done = time.perf_counter()
    return dict(planned=planned-origin, sent=sent-origin, done=done-origin,
                status=status, instance=instance, latency_ms=(done-sent)*1000,
                scheduled_latency_ms=(done-planned)*1000, lag_ms=(sent-planned)*1000,
                error=error)

def worker(args):
    url, rate, duration, origin, rank, processes, threads = args
    futures = []
    with cf.ThreadPoolExecutor(max_workers=threads) as pool:
        for index in range(rank, math.ceil(rate*duration), processes):
            planned = origin + index/rate
            remaining = planned-time.perf_counter()
            if remaining > 0:
                time.sleep(remaining)
            futures.append(pool.submit(request_one, url, planned, origin))
        return [f.result() for f in futures]

def quantile(values, q):
    values = sorted(values)
    pos = (len(values)-1)*q
    lo = int(pos)
    return values[lo]+(values[min(lo+1, len(values)-1)]-values[lo])*(pos-lo)

def summarize(rows, duration, rate=None):
    latency = [r['latency_ms'] for r in rows]
    # Requests crossing the right boundary contribute only their observed overlap.
    area = sum(max(0, min(r['done'], duration)-max(0, r['sent'])) for r in rows)
    in_window = [r for r in rows if 0 <= r['done'] <= duration]
    events = sorted([(max(0,r['sent']), 1) for r in rows if r['sent'] < duration] +
                    [(r['done'], -1) for r in rows if r['done'] < duration])
    active = maximum = 0
    for _, delta in events:
        active += delta
        maximum = max(active, maximum)
    return dict(target_rps=rate, duration=duration, requests=len(rows),
                sent_rps=sum(r['sent'] < duration for r in rows)/duration,
                achieved_rps=len(in_window)/duration,
                success_rps=sum(200 <= r['status'] < 300 for r in in_window)/duration,
                p50_ms=quantile(latency,.5), p95_ms=quantile(latency,.95),
                p99_ms=quantile(latency,.99), mean_ms=sum(latency)/len(latency),
                non_2xx_fraction=sum(not 200 <= r['status'] < 300 for r in rows)/len(rows),
                measured_L=area/duration, max_inflight=maximum,
                outstanding_at_end=sum(r['sent'] < duration < r['done'] for r in rows),
                p95_scheduler_lag_ms=quantile([r['lag_ms'] for r in rows],.95),
                p95_scheduled_ms=quantile([r['scheduled_latency_ms'] for r in rows],.95),
                instances=sorted(set(r['instance'] for r in rows if r['instance'])))

def announce_ready(queue):
    queue.put(True)

def run_open(url, rate, duration=30, processes=None, threads=64):
    processes = processes or min(os.cpu_count() or 1, math.ceil(rate))
    queue=mp.Queue()
    with mp.Pool(processes,initializer=announce_ready,initargs=(queue,)) as pool:
        for _ in range(processes):
            queue.get(timeout=60)
        origin = time.perf_counter()+2
        chunks = pool.map(worker, [(url,rate,duration,origin,i,processes,threads) for i in range(processes)])
    rows = sorted([r for c in chunks for r in c], key=lambda r:r['sent'])
    return dict(summary=summarize(rows,duration,rate), rows=rows)

def closed_worker(url, origin, duration):
    rows=[]
    while time.perf_counter() < origin:
        time.sleep(.001)
    while time.perf_counter() < origin+duration:
        rows.append(request_one(url,time.perf_counter(),origin))
    return rows

def run_closed(url, concurrency, duration=30):
    origin=time.perf_counter()+1
    with cf.ThreadPoolExecutor(max_workers=concurrency) as pool:
        chunks=list(pool.map(lambda _:closed_worker(url,origin,duration),range(concurrency)))
    rows=[r for c in chunks for r in c]
    return dict(summary=summarize(rows,duration),rows=rows,concurrency=concurrency)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('url'); p.add_argument('--rate',type=int,default=100)
    p.add_argument('--duration',type=int,default=30); p.add_argument('--warmup',type=int,default=10)
    p.add_argument('--processes',type=int); p.add_argument('--threads',type=int,default=64)
    p.add_argument('--closed',type=int); p.add_argument('--output',default='results/run.json')
    a=p.parse_args()
    if a.closed:
        run_closed(a.url,a.closed,a.warmup)
        result=run_closed(a.url,a.closed,a.duration)
    else:
        run_open(a.url,a.rate,a.warmup,a.processes,a.threads)
        result=run_open(a.url,a.rate,a.duration,a.processes,a.threads)
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result['summary'],indent=2))
    if not a.closed and result['summary']['sent_rps'] < 0.98 * a.rate:
        print(
            f"WARNING: actual HTTP send rate {result['summary']['sent_rps']:.3f} rps is below 98% "
            f"of target {a.rate} rps. Treat this run as generator/host limited too; "
            "consider more --threads or a separate generator host before attributing the limit only to the service.",
            file=sys.stderr,
        )
