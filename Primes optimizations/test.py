#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import os
import random
import signal
import sys
import time
from dataclasses import dataclass
from typing import List, Optional


# ----------------------------
# Таймаут (Unix)
# ----------------------------

class TimeoutError_(Exception):
    pass


def _timeout_handler(signum, frame):
    raise TimeoutError_("Time limit exceeded")


# ----------------------------
# Простота (для judge)
# ----------------------------

def is_prime_judge(n: int) -> bool:
    if n < 2:
        return False
    small_primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37]
    for p in small_primes:
        if n == p:
            return True
        if n % p == 0:
            return False

    d = n - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1

    bases = [2, 325, 9375, 28178, 450775, 9780504, 1795265022]
    for a in bases:
        if a % n == 0:
            continue
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        composite = True
        for _ in range(s - 1):
            x = (x * x) % n
            if x == n - 1:
                composite = False
                break
        if composite:
            return False
    return True


# ----------------------------
# API и попугаи
# ----------------------------

@dataclass
class CallStats:
    parrots: int = 0
    calls_size: int = 0
    calls_get_item: int = 0
    calls_is_prime: int = 0
    calls_batch_get: int = 0
    calls_sum_range: int = 0


class WarehouseAPI:
    pass


class WarehouseAPIImpl(WarehouseAPI):
    def __init__(self, arr: List[int]):
        self._arr = arr
        self.stats = CallStats()

    def size(self) -> int:
        self.stats.calls_size += 1
        self.stats.parrots += 5
        return len(self._arr)

    def get_item(self, index: int) -> int:
        self.stats.calls_get_item += 1
        self.stats.parrots += 20
        if index < 0 or index >= len(self._arr):
            raise IndexError("index out of range")
        return self._arr[index]

    def is_prime(self, x: int) -> bool:
        self.stats.calls_is_prime += 1
        self.stats.parrots += 15
        return is_prime_judge(x)

    def batch_get(self, indices: List[int]) -> List[int]:
        self.stats.calls_batch_get += 1
        k = len(indices)
        self.stats.parrots += 10 + 2 * k
        n = len(self._arr)
        out = []
        for idx in indices:
            if idx < 0 or idx >= n:
                raise IndexError("index out of range in batch_get")
            out.append(self._arr[idx])
        return out

    def sum_range(self, left: int, right: int) -> int:
        self.stats.calls_sum_range += 1
        self.stats.parrots += 50
        if left < 0 or right < 0 or left > right or right >= len(self._arr):
            raise IndexError("invalid range")
        return sum(self._arr[left:right + 1])


# ----------------------------
# Генерация тестов
# ----------------------------

def gen_test(seed: int, n: int, mode: str) -> List[int]:
    rng = random.Random(seed)
    if n == 0:
        return []

    if mode == "uniform_1e9":
        return [rng.randint(1, 10**9) for _ in range(n)]

    if mode == "many_small":
        return [rng.randint(1, 200000) for _ in range(n)]

    if mode == "prime_heavy":
        arr = []
        x = rng.randint(10**8, 10**9)
        while len(arr) < n:
            x += rng.randint(1, 1000)
            if x % 2 == 0:
                x += 1
            if is_prime_judge(x):
                arr.append(x)
            else:
                if rng.random() < 0.2:
                    arr.append(x)
        return arr

    if mode == "structured_blocks":
        arr = []
        while len(arr) < n:
            block_len = rng.randint(1, 1000)
            val = rng.randint(1, 10**6)
            arr.extend([val] * block_len)
        return arr[:n]

    raise ValueError("unknown mode")


@dataclass
class TestCase:
    name: str
    seed: int
    n: int
    mode: str
    time_limit_sec: float


def default_tests() -> List[TestCase]:
    return [
        TestCase("tiny_empty", 1, 0, "uniform_1e9", 0.2),
        TestCase("tiny_10", 2, 10, "many_small", 0.2),
        TestCase("small_1k", 3, 1000, "many_small", 0.4),
        TestCase("mid_20k_uniform", 4, 20000, "uniform_1e9", 0.8),
        TestCase("mid_20k_small", 5, 20000, "many_small", 0.8),
        TestCase("mid_20k_prime_heavy", 6, 20000, "prime_heavy", 1.2),
        TestCase("big_100k_uniform", 7, 100000, "uniform_1e9", 1.5),
        TestCase("big_100k_blocks", 8, 100000, "structured_blocks", 1.5),
        TestCase("big_100k_small", 9, 100000, "many_small", 1.5),
    ]


# ----------------------------
# Правильный ответ
# ----------------------------

def correct_answer(arr: List[int]) -> int:
    return sum(x for x in arr if is_prime_judge(x))


# ----------------------------
# Загрузка решения
# ----------------------------

def load_participant(path: str):
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location("participant", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load participant module")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    if not hasattr(mod, "solve"):
        raise AttributeError("participant.py must define solve(api)")
    return mod.solve


# ----------------------------
# Скоры по попугаям (на ОДИН тест)
# ----------------------------

def score_from_parrots(C: int) -> int:
    if C <= 210_000:
        return 100
    if C <= 500_000:
        return 70
    if C <= 1_000_000:
        return 40
    return 0


# ----------------------------
# Прогон теста
# ----------------------------

@dataclass
class TestResult:
    name: str
    ok: bool
    time_sec: float
    parrots: int
    points: int
    participant_ans: Optional[int] = None
    correct_ans: Optional[int] = None
    error: Optional[str] = None
    stats: Optional[CallStats] = None


def run_one_test(solve_fn, tc: TestCase) -> TestResult:
    arr = gen_test(tc.seed, tc.n, tc.mode)
    api = WarehouseAPIImpl(arr)

    t0 = time.perf_counter()
    err = None
    ans = None

    old_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, tc.time_limit_sec)

    try:
        ans = solve_fn(api)
    except TimeoutError_ as e:
        err = str(e)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, old_handler)

    t1 = time.perf_counter()
    parrots = api.stats.parrots

    if err is not None:
        return TestResult(
            name=tc.name,
            ok=False,
            time_sec=t1 - t0,
            parrots=parrots,
            points=0,
            error=err,
            stats=api.stats,
        )

    corr = correct_answer(arr)
    ok = (ans == corr)
    points = score_from_parrots(parrots) if ok else 0

    return TestResult(
        name=tc.name,
        ok=ok,
        time_sec=t1 - t0,
        parrots=parrots,
        points=points,
        participant_ans=ans,
        correct_ans=corr,
        error=None if ok else "Wrong Answer",
        stats=api.stats,
    )


def run_all(participant_path: str) -> int:
    solve_fn = load_participant(participant_path)
    tests = default_tests()

    results: List[TestResult] = []
    total_points = 0

    print(f"Participant: {participant_path}")
    print(f"Tests: {len(tests)}")
    print("-" * 100)
    print(f"{'TEST':20s} | {'STAT':4s} | {'TIME':>9s} | {'PARROTS':>10s} | {'PTS':>3s}")
    print("-" * 100)

    for tc in tests:
        res = run_one_test(solve_fn, tc)
        results.append(res)
        total_points += res.points

        status = "OK" if res.ok else "FAIL"
        print(f"{res.name:20s} | {status:4s} | {res.time_sec:9.4f}s | {res.parrots:10d} | {res.points:3d}")

        if not res.ok:
            print(f"  error: {res.error}")
            if res.participant_ans is not None:
                print(f"  got: {res.participant_ans}")
                print(f"  exp: {res.correct_ans}")
            if res.stats:
                s = res.stats
                print(f"  calls: size={s.calls_size}, get_item={s.calls_get_item}, "
                      f"is_prime={s.calls_is_prime}, batch_get={s.calls_batch_get}, sum_range={s.calls_sum_range}")
            print("-" * 100)

    avg_points = total_points / len(tests) if tests else 0.0

    print("=" * 100)
    print(f"Total points (sum): {total_points} / {100 * len(tests)}")
    print(f"Final score (avg):  {avg_points:.2f} / 100.00")
    print("=" * 100)

    # Возврат 0 если средний балл > 0 и нет фатальных ошибок — можно настроить как хочешь.
    return 0 if avg_points > 0 else 1


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 judge.py participant.py")
        sys.exit(2)

    # Примечание: signal-таймаут обычно работает на Unix в main thread.
    sys.exit(run_all(sys.argv[1]))


if __name__ == "__main__":
    main()
