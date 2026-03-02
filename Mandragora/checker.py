#!/usr/bin/env python3
"""
Checker for "Молчащая мандрагора" task.

Usage:
  python3 checker.py [-c "command to start server"] [--start-wait 0.5] [--host 127.0.0.1] [--port 8080]

If -c is provided the checker will spawn the command (shell) and attempt to contact the server.
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime, timedelta, date
import random
import threading
import requests

DATEFMT = "%d.%m.%Y"

def parse_date(s: str) -> date:
    return datetime.strptime(s, DATEFMT).date()

def format_date(d: date) -> str:
    return d.strftime(DATEFMT)

class Plant:
    def __init__(self, pid: str, interval: int, maxdelay: int, added: date):
        self.id = pid
        self.interval = interval
        self.maxdelay = maxdelay
        self.added = added
        self.waterings = []  # list of dates when watered (monotonic insert)
    def record_watering(self, d: date):
        # keep sorted; append only expected because dates never decrease in test generator
        if not self.waterings or d >= self.waterings[-1]:
            self.waterings.append(d)
        else:
            # if out of order, insert keeping order
            import bisect
            bisect.insort(self.waterings, d)

# Simulation/model of correct behavior
class Simulator:
    def __init__(self):
        self.plants = {}  # id -> Plant

    def add_plant(self, pid: str, interval: int, maxdelay: int, added: date):
        if pid in self.plants:
            # as problem doesn't state duplicate add, overwrite to be safe
            self.plants[pid] = Plant(pid, interval, maxdelay, added)
        else:
            self.plants[pid] = Plant(pid, interval, maxdelay, added)

    def water(self, pid: str, d: date):
        if pid not in self.plants:
            return
        p = self.plants[pid]
        p.record_watering(d)

    def _is_alive_on(self, p: Plant, cur: date):
        # For all scheduled S <= cur: if cur > S + maxdelay and there was no watering in [S, S+maxdelay] by time cur => died earlier
        if cur < p.added:
            return False
        interval = p.interval
        # number of scheduled occurrences up to cur
        last_k = (cur - p.added).days // interval
        # for each scheduled S_k with S_k <= cur, check if there was a watering in [S_k, min(S_k+maxdelay, cur)]
        for k in range(0, last_k+1):
            S = p.added + timedelta(days=k*interval)
            window_end = S + timedelta(days=p.maxdelay)
            # if window ended before cur and no watering in [S, window_end] -> dead
            if window_end < cur:
                # check any watering in [S, window_end]
                ok = any((w >= S and w <= window_end) for w in p.waterings)
                if not ok:
                    return False
            else:
                # window_end >= cur: current window not closed yet; can't be dead because we still can water
                pass
        return True

    def _needs_water_on(self, p: Plant, cur: date):
        # If alive and exists S with S <= cur <= S+maxdelay and no watering in [S, cur]
        if cur < p.added:
            return False
        interval = p.interval
        last_k = (cur - p.added).days // interval
        for k in range(0, last_k+1):
            S = p.added + timedelta(days=k*interval)
            window_end = S + timedelta(days=p.maxdelay)
            if S <= cur <= window_end:
                # check if any watering in [S, cur]
                if not any((w >= S and w <= cur) for w in p.waterings):
                    return True
        return False

    def task_on(self, cur: date):
        # return sorted list of plant ids that need watering on cur, considering death
        res = []
        # iterate over copy because plants can be many, but for checker it's fine
        for pid, p in self.plants.items():
            if not self._is_alive_on(p, cur):
                continue
            if self._needs_water_on(p, cur):
                res.append(pid)
        # lexicographic order
        res.sort()
        return res

# HTTP helpers
def do_get(base_url: str, path: str, timeout=2.0):
    url = base_url + path
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code, r.text
    except Exception as e:
        return None, str(e)

# Test sequences generator (includes the example from statement + random tests)
def generate_tests():
    tests = []

    # Example from statement (reconstructed as plausible sequence)
    # We'll use the explicit example given near description (best-effort reconstruction).
    ex = [
        ("GET", "/add/1/2/1/?date=01.01.2024"),
        ("GET", "/add/2/2/2/?date=01.01.2024"),
        ("GET", "/task/?date=01.01.2024"),
        ("GET", "/task/?date=02.01.2024"),
        ("GET", "/task/?date=03.01.2024"),
        ("GET", "/task/?date=04.01.2024"),
        ("GET", "/task/?date=05.01.2024"),
        ("GET", "/watering/2/?date=05.01.2024"),
        ("GET", "/task/?date=07.01.2024"),
        ("GET", "/watering/2/?date=07.01.2024"),
        ("GET", "/task/?date=08.01.2024"),
        ("GET", "/watering/2/?date=08.01.2024"),
        ("GET", "/task/?date=08.01.2024"),
        ("GET", "/task/?date=09.01.2024"),
        ("GET", "/task/?date=10.01.2024"),
    ]
    tests.append(("example", ex))

    # Some handcrafted edge cases:
    # 1) plant added and never watered, but maxdelay shorter -> dies
    t1 = [
        ("GET", "/add/a/3/1/?date=01.06.2024"),  # schedule: 01,04,07...
        ("GET", "/task/?date=01.06.2024"),      # needs watering
        ("GET", "/task/?date=03.06.2024"),      # still within maxdelay for S=01? maxdelay=1 so 01+1=02 < 03 -> died
        ("GET", "/task/?date=04.06.2024"),
    ]
    tests.append(("dies_if_missed", t1))

    # 2) watering early/late interplay, larger maxdelay
    t2 = [
        ("GET", "/add/x/5/3/?date=10.07.2024"),
        ("GET", "/task/?date=10.07.2024"),
        ("GET", "/task/?date=14.07.2024"),
        ("GET", "/task/?date=15.07.2024"),
        ("GET", "/watering/x/?date=15.07.2024"),
        ("GET", "/task/?date=16.07.2024"),
        ("GET", "/task/?date=20.07.2024"),
    ]
    tests.append(("late_watering", t2))

    # 3) random scenario (small) to check lexicographic ordering etc.
    rnd = []
    cur = parse_date("01.01.2025")
    ids = ["p"+str(i) for i in range(1,6)]
    random.seed(12345)
    # add some plants on same day with different params
    rnd.append(("GET", f"/add/{ids[0]}/2/1/?date={format_date(cur)}"))
    rnd.append(("GET", f"/add/{ids[1]}/3/2/?date={format_date(cur)}"))
    rnd.append(("GET", f"/add/{ids[2]}/1/0/?date={format_date(cur)}"))
    # simulate 10 days, random waterings
    for day in range(0, 10):
        d = cur + timedelta(days=day)
        # random watering
        for pid in ids[:3]:
            if random.random() < 0.2:
                rnd.append(("GET", f"/watering/{pid}/?date={format_date(d)}"))
        rnd.append(("GET", f"/task/?date={format_date(d)}"))
    tests.append(("random_small", rnd))

    return tests

# Run a single test sequence against server and simulator
def run_sequence(seq_name, seq, base_url, sim: Simulator, request_timeout):
    print(f"=== Running test sequence: {seq_name} ===")
    for idx, (method, path) in enumerate(seq, start=1):
        if method != "GET":
            raise RuntimeError("Only GET interactions implemented in checker")
        status, body_or_err = do_get(base_url, path, timeout=request_timeout)
        # Determine date in query param
        # path may be like /task/?date=01.01.2024 or /add/.../?date=...
        if "?date=" not in path:
            print("Malformed test path (no date):", path)
            return False, f"Malformed test path (no date): {path}"
        date_str = path.split("?date=")[1]
        cur = parse_date(date_str)

        # Update simulator state for add/watering
        if path.startswith("/add/"):
            # /add/<plant:str>/<interval:int>/<maxdelay:int>/?date=...
            parts = path[len("/add/"):].split("/?date=")[0].split("/")
            pid = parts[0]
            interval = int(parts[1])
            maxdelay = int(parts[2])
            sim.add_plant(pid, interval, maxdelay, cur)
            # Expect server to return something 200
            if status != 200:
                return False, f"Expected status 200 for add, got {status} with body: {body_or_err}"
            continue

        if path.startswith("/watering/"):
            # /watering/<plant>/?date=...
            parts = path[len("/watering/"):].split("/?date=")[0].split("/")
            pid = parts[0]
            sim.water(pid, cur)
            if status != 200:
                return False, f"Expected status 200 for watering, got {status} with body: {body_or_err}"
            continue

        if path.startswith("/task/"):
            if status != 200:
                return False, f"Expected status 200 for task, got {status} with body: {body_or_err}"
            expected_list = sim.task_on(cur)
            expected_body = ",".join(expected_list)
            # Normalize server body: strip whitespace and trailing newlines
            got_body = body_or_err.strip()
            # Some servers might return with trailing newline; strip is fine
            if got_body != expected_body:
                # Provide detailed debug
                dbg = []
                dbg.append(f"Mismatch at step {idx} (sequence {seq_name}):")
                dbg.append(f"  Request: GET {path}")
                dbg.append(f"  Expected (body): '{expected_body}'")
                dbg.append(f"  Got      (body): '{got_body}'")
                dbg.append(f"  Simulator state at date {format_date(cur)}:")
                for pid, p in sorted(sim.plants.items()):
                    dbg.append(f"    Plant {pid}: added={format_date(p.added)}, int={p.interval}, maxdelay={p.maxdelay}, waterings={[format_date(w) for w in p.waterings]}")
                return False, "\n".join(dbg)
            else:
                print(f" OK task {date_str} -> '{expected_body}'")
            continue

        # Unknown path type
        return False, f"Unknown path type: {path}"

    return True, "OK"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--command", help="Command to start the server (optional, shell executed).")
    parser.add_argument("--start-wait", type=float, default=0.5, help="Seconds to wait after starting server before tests.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--request-timeout", type=float, default=2.0)
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"

    server_proc = None
    if args.command:
        print("Starting server with command:", args.command)
        server_proc = subprocess.Popen(args.command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # wait a bit for server to start
        time.sleep(args.start_wait)
        # Optionally probe server root to ensure it's alive; if not alive, continue anyway and fail on first request
    try:
        tests = generate_tests()
        for name, seq in tests:
            sim = Simulator()
            ok, msg = run_sequence(name, seq, base_url, sim, args.request_timeout)
            if not ok:
                print("TEST FAILED:")
                print(msg)
                if server_proc:
                    server_proc.kill()
                sys.exit(1)
        print("\nAll tests passed.")
    finally:
        if server_proc:
            try:
                server_proc.terminate()
                # give it a moment
                time.sleep(0.2)
                server_proc.kill()
            except Exception:
                pass

if __name__ == "__main__":
    main()
