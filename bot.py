"""
CoBuilt bots runner — runs the Quote bot and the Concrete Price bot together
in ONE Render service, to save the cost of a second service.

Each bot runs exactly as before, unchanged, in its own separate process:
  - quote_bot.py        Quote bot (PDF quotes)        uses BOT_TOKEN
  - price_bot/bot.py    Concrete Price bot (costing)  uses PRICE_BOT_TOKEN
                                                     (given to it as BOT_TOKEN)

If one bot crashes, only that bot is restarted; the other keeps running.
Telegram bot tokens are hidden from the logs, and the repeating
"getUpdates 200 OK" polling lines are left out to keep the logs readable.
"""
import os
import re
import signal
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))

BOTS = [
    {"name": "quote", "script": "quote_bot.py", "cwd": HERE, "token_env": "BOT_TOKEN"},
    {"name": "price", "script": "bot.py", "cwd": os.path.join(HERE, "price_bot"), "token_env": "PRICE_BOT_TOKEN"},
]

TOKEN_RE = re.compile(r"bot\d{6,}:[A-Za-z0-9_-]{20,}")
QUIET_RE = re.compile(r"/getUpdates \"HTTP/1\.1 200 OK\"")

stopping = threading.Event()
lock = threading.Lock()


def log(msg):
    with lock:
        print(f"[runner] {msg}", flush=True)


def pipe_output(name, stream):
    for raw in iter(stream.readline, b""):
        line = raw.decode("utf-8", "replace").rstrip("\n")
        if QUIET_RE.search(line):
            continue
        line = TOKEN_RE.sub("bot<hidden>", line)
        with lock:
            print(f"[{name}] {line}", flush=True)
    stream.close()


def start(bot):
    token = os.environ.get(bot["token_env"], "").strip()
    env = dict(os.environ)
    env["BOT_TOKEN"] = token
    env.pop("PRICE_BOT_TOKEN", None)  # each bot only sees its own token
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [sys.executable, bot["script"]],
        cwd=bot["cwd"], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    threading.Thread(target=pipe_output, args=(bot["name"], proc.stdout), daemon=True).start()
    log(f"started {bot['name']} bot (pid {proc.pid})")
    return proc


def supervise(bot, procs):
    delay = 5
    while not stopping.is_set():
        started_at = time.time()
        proc = start(bot)
        procs[bot["name"]] = proc
        code = proc.wait()
        if stopping.is_set():
            break
        ran = time.time() - started_at
        if ran > 300:
            delay = 5  # it ran fine for a while: restart quickly
        log(f"{bot['name']} bot stopped (exit code {code}) after {int(ran)}s — restarting in {delay}s")
        if stopping.wait(delay):
            break
        delay = min(delay * 2, 120)


def main():
    procs = {}
    threads = []
    for bot in BOTS:
        if not os.environ.get(bot["token_env"], "").strip():
            log(f"{bot['token_env']} is not set — the {bot['name']} bot will NOT start")
            continue
        t = threading.Thread(target=supervise, args=(bot, procs), daemon=True)
        t.start()
        threads.append(t)

    if not threads:
        log("no bot tokens set — nothing to run")
        sys.exit(1)

    def shutdown(signum, _frame):
        if stopping.is_set():
            return
        stopping.set()
        log(f"received signal {signum} — stopping bots")
        for p in list(procs.values()):
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
        deadline = time.time() + 20
        for p in list(procs.values()):
            try:
                p.wait(timeout=max(0.1, deadline - time.time()))
            except subprocess.TimeoutExpired:
                p.kill()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    while not stopping.is_set():
        time.sleep(1)


if __name__ == "__main__":
    main()
