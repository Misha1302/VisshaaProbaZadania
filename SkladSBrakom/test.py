#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Judge for task "Склад с браком" (пер-тестовая оценка).

Гарантии генератора тестов:
  - N <= 100000
  - 0 <= A[i] <= 1e9
  - все ненулевые строго положительные
  - количество ненулевых <= floor(0.05 * N)  (т.е. <= 5%)
  - ненулевые располагаются блоками, число блоков <= max_nonzero_blocks

Запуск:
  python3 judge.py participant.py

participant.py должен содержать:
  def solve(api): -> int
"""

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
# API + попугаи
# ----------------------------

@dataclass
class CallStats:
    parrots: int = 0
    calls_size: int = 0
    calls_get_item: int = 0
    calls_sum_range: int = 0


class WarehouseAPI:
    pass


class WarehouseAPIImpl(WarehouseAPI):
    """
    Стоимость:
      size() = 5
      get_item(i) = 20
      sum_range(l,r) = 30
    """
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

    def sum_range(self, left: int, right: int) -> int:
        self.stats.calls_sum_range += 1
        self.stats.parrots += 30
        n = len(self._arr)
        if left < 0 or right < 0 or left > right or right >= n:
            raise IndexError("invalid range")
        return sum(self._arr[left:right + 1])


# ----------------------------
# Генерация тестов (ненулевых <= 5%)
# ----------------------------

def _rand_pos(rng: random.Random) -> int:
    return rng.randint(1, 10**9)


def _count_nonzero_blocks(arr: List[int]) -> int:
    blocks = 0
    in_block = False
    for x in arr:
        if x != 0:
            if not in_block:
                blocks += 1
                in_block = True
        else:
            in_block = False
    return blocks


def gen_test(seed: int, n: int, max_nonzero_blocks: int, mode: str) -> List[int]:
    """
    Гарантируем:
      - 0 <= A[i] <= 1e9
      - все ненулевые строго положительные
      - число ненулевых <= floor(0.05 * n)
      - ненулевые располагаются блоками, число блоков <= max_nonzero_blocks
    """
    rng = random.Random(seed)
    if n == 0:
        return []

    # База: всё нули (брак)
    arr = [0] * n

    max_k = int(0.05 * n)  # floor
    if max_k == 0:
        return arr

    # Выбираем количество ненулевых
    if mode == "no_nonzero":
        k_nonzero = 0
    elif mode == "min_nonzero":
        k_nonzero = 1
    elif mode == "random_nonzero":
        k_nonzero = rng.randint(0, max_k)
    elif mode == "max_nonzero":
        k_nonzero = max_k
    elif mode == "max_nonzero_singletons":
        # максимум ненулевых и максимально "зло": блоки длины 1
        k_nonzero = max_k
    else:
        raise ValueError("unknown mode")

    if k_nonzero == 0:
        return arr

    # Сколько блоков ненулевых
    if mode == "max_nonzero_singletons":
        blocks = min(max_nonzero_blocks, k_nonzero)
        # Сделаем блоки длины 1, если возможно (для этого blocks = k_nonzero, но ограничено 50)
        # Поэтому ставим blocks = min(50, k_nonzero), а длины распределим как 1.., остаток в последний.
        blocks = min(max_nonzero_blocks, 50, k_nonzero)
        lens = [1] * blocks
        # остаток ненулевых, который не уместился в единичные блоки, докинем в последний блок
        rest = k_nonzero - blocks
        lens[-1] += rest
    else:
        blocks = rng.randint(1, min(max_nonzero_blocks, k_nonzero))
        # Разбиваем k_nonzero на blocks положительных длин
        cuts = sorted(rng.sample(range(1, k_nonzero), k=blocks - 1)) if blocks > 1 else []
        lens = []
        prev = 0
        for c in cuts + [k_nonzero]:
            lens.append(c - prev)
            prev = c

    # Размещаем блоки без пересечений.
    # При 5% плотности это легко.
    used = [False] * n
    for L in lens:
        placed = False
        for _ in range(4000):
            s = rng.randint(0, n - L)
            if any(used[s:s + L]):
                continue
            for i in range(s, s + L):
                used[i] = True
                arr[i] = _rand_pos(rng)
            placed = True
            break
        if not placed:
            # Fallback: последовательный поиск
            s = 0
            while s + L <= n and any(used[s:s + L]):
                s += 1
            if s + L > n:
                # При 5% почти не случается, но если вдруг — уменьшим L (без нарушения лимита блоков)
                # и просто поставим что можем.
                L2 = max(0, n - s)
                for i in range(s, s + L2):
                    used[i] = True
                    arr[i] = _rand_pos(rng)
            else:
                for i in range(s, s + L):
                    used[i] = True
                    arr[i] = _rand_pos(rng)

    # Жёсткие проверки инвариантов (гарантия условия)
    nnz = sum(1 for x in arr if x != 0)
    assert nnz <= max_k, f"BUG: nnz={nnz} > floor(0.05*n)={max_k}"
    for x in arr:
        assert 0 <= x <= 10**9, "BUG: value out of range"
        assert x == 0 or x > 0, "BUG: nonzero must be positive"
    b = _count_nonzero_blocks(arr)
    assert b <= max_nonzero_blocks, f"BUG: blocks={b} > {max_nonzero_blocks}"

    return arr


# ----------------------------
# Тесты
# ----------------------------

@dataclass
class TestCase:
    name: str
    seed: int
    n: int
    mode: str
    max_nonzero_blocks: int
    time_limit_sec: float


def default_tests() -> List[TestCase]:
    return [
        TestCase("tiny_empty", 1, 0, "no_nonzero", 50, 0.15),
        TestCase("tiny_20_all_zero", 2, 20, "no_nonzero", 50, 0.15),
        TestCase("tiny_20_one_nonzero", 3, 20, "min_nonzero", 50, 0.15),

        TestCase("small_2k_random", 4, 2000, "random_nonzero", 50, 0.25),
        TestCase("small_2k_max5pct", 5, 2000, "max_nonzero", 50, 0.25),

        TestCase("mid_20k_random", 6, 20000, "random_nonzero", 50, 0.60),
        TestCase("mid_20k_max5pct", 7, 20000, "max_nonzero", 50, 0.60),

        TestCase("big_100k_random", 8, 100000, "random_nonzero", 50, 1.20),
        TestCase("big_100k_max5pct", 9, 100000, "max_nonzero", 50, 1.20),

        # "Злой" тест: максимум ненулевых и почти максимально "рвано" (одиночки насколько возможно)
        TestCase("big_100k_evil_singletons", 10, 100000, "max_nonzero_singletons", 50, 1.20),
    ]


# ----------------------------
# Правильный ответ
# ----------------------------

def correct_answer(arr: List[int]) -> int:
    # количество нулей
    return len(arr) - sum(1 for x in arr if x != 0)


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
    if C <= 300_000:
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
    arr = gen_test(tc.seed, tc.n, tc.max_nonzero_blocks, tc.mode)
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

    total_points = 0

    print(f"Participant: {participant_path}")
    print(f"Tests: {len(tests)}")
    print("-" * 118)
    print(f"{'TEST':28s} | {'STAT':4s} | {'TIME':>9s} | {'PARROTS':>10s} | {'PTS':>3s} | calls(size/get/sum)")
    print("-" * 118)

    for tc in tests:
        res = run_one_test(solve_fn, tc)
        total_points += res.points

        status = "OK" if res.ok else "FAIL"
        s = res.stats or CallStats()
        print(
            f"{res.name:28s} | {status:4s} | {res.time_sec:9.4f}s | "
            f"{res.parrots:10d} | {res.points:3d} | {s.calls_size}/{s.calls_get_item}/{s.calls_sum_range}"
        )

        if not res.ok:
            print(f"  error: {res.error}")
            if res.participant_ans is not None:
                print(f"  got: {res.participant_ans}")
                print(f"  exp: {res.correct_ans}")
            print("-" * 118)

    avg_points = total_points / len(tests) if tests else 0.0
    print("=" * 118)
    print(f"Total points (sum): {total_points} / {100 * len(tests)}")
    print(f"Final score (avg):  {avg_points:.2f} / 100.00")
    print("=" * 118)

    return 0 if avg_points > 0 else 1


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 judge.py participant.py")
        sys.exit(2)

    # Таймаут через signal обычно работает на Unix в main thread.
    sys.exit(run_all(sys.argv[1]))


if __name__ == "__main__":
    main()
