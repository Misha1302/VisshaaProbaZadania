#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import importlib.util
import io
import json
import multiprocessing as mp
import os
import random
import sys
import time
import traceback
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MAX_N = 100_000
MAX_A = 10**9
MAX_NONZERO_RATIO = 0.02
MAX_BLOCKS = 40

FULL_SCORE_LIMIT = 90_000
MID_SCORE_LIMIT = 140_000
LOW_SCORE_LIMIT = 220_000

FULL_SCORE_POINTS = 100
MID_SCORE_POINTS = 20
LOW_SCORE_POINTS = 0
ZERO_SCORE_POINTS = 0


@dataclass
class SingleRunResult:
    ok: bool
    verdict: str
    answer: Any
    expected: int
    total_cost: int
    elapsed_sec: float
    seed: int
    error_text: str = ""


@dataclass
class TestCaseSummary:
    test_name: str
    runs: list[SingleRunResult]
    passed_all_runs: bool
    effective_cost: float
    base_points: int
    weighted_points: int
    weight: int
    expected: int


def count_nonzero_blocks(arr: list[int]) -> int:
    blocks = 0
    inside = False

    for value in arr:
        if value != 0:
            if not inside:
                blocks += 1
                inside = True
        else:
            inside = False

    return blocks


def validate_array(arr: list[int], source_name: str) -> None:
    if not isinstance(arr, list):
        raise TypeError(f"{source_name}: array must be a JSON list")

    n = len(arr)
    if not (0 <= n <= MAX_N):
        raise ValueError(f"{source_name}: invalid n={n}, expected 0 <= n <= {MAX_N}")

    nonzero_count = 0
    for index, value in enumerate(arr):
        if not isinstance(value, int):
            raise TypeError(
                f"{source_name}: array[{index}] must be int, got {type(value).__name__}"
            )
        if not (0 <= value <= MAX_A):
            raise ValueError(
                f"{source_name}: array[{index}]={value} is out of range [0, {MAX_A}]"
            )
        if value != 0:
            nonzero_count += 1

    max_nonzero = int(MAX_NONZERO_RATIO * n)
    if nonzero_count > max_nonzero:
        raise ValueError(
            f"{source_name}: too many nonzero elements: "
            f"{nonzero_count} > floor(0.02 * {n}) = {max_nonzero}"
        )

    blocks = count_nonzero_blocks(arr)
    if blocks > MAX_BLOCKS:
        raise ValueError(
            f"{source_name}: too many nonzero blocks: {blocks} > {MAX_BLOCKS}"
        )


def load_test_array(path: Path) -> list[int]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, list):
        arr = data
    elif isinstance(data, dict) and "array" in data:
        arr = data["array"]
    else:
        raise ValueError(f"{path}: expected JSON list or JSON object with key 'array'")

    validate_array(arr, str(path))
    return arr


def load_expected_answer(test_path: Path, arr: list[int]) -> int:
    ans_path = test_path.with_suffix(".ans")
    if ans_path.is_file():
        with ans_path.open("r", encoding="utf-8") as file:
            content = file.read().strip()
        try:
            return int(content)
        except ValueError as exc:
            raise ValueError(f"{ans_path}: answer file does not contain an integer") from exc

    return sum(arr)


def compute_points(cost: float) -> int:
    if cost <= FULL_SCORE_LIMIT:
        return FULL_SCORE_POINTS
    if cost <= MID_SCORE_LIMIT:
        return MID_SCORE_POINTS
    if cost <= LOW_SCORE_LIMIT:
        return LOW_SCORE_POINTS
    return ZERO_SCORE_POINTS


def get_test_weight(test_stem: str) -> int:
    if test_stem.startswith("manual_"):
        return 0
    if test_stem.startswith("small_"):
        return 5
    if test_stem.startswith("large_all_zero_"):
        return 20
    if test_stem.startswith("large_one_huge_block_"):
        return 110
    if test_stem.startswith("large_max_blocks_singletons_"):
        return 140
    if test_stem.startswith("large_near_limit_"):
        return 170
    if test_stem.startswith("large_many_short_blocks_"):
        return 160
    if test_stem.startswith("adv_"):
        return 220
    return 50


class WarehouseAPI:
    def __init__(self, array: list[int], rng: random.Random) -> None:
        self._array = array
        self._rng = rng
        self.total_cost = 0

    def _charge(self, amount: int) -> None:
        self.total_cost += amount

    def size(self) -> int:
        self._charge(5)
        return len(self._array)

    def get(self, i: int) -> int:
        if not isinstance(i, int):
            raise TypeError(f"get(i): i must be int, got {type(i).__name__}")
        if not (0 <= i < len(self._array)):
            raise IndexError(f"get({i}) out of bounds for n={len(self._array)}")

        self._charge(self._rng.randint(10, 50))
        return self._array[i]

    def has_nonzero(self, l: int, r: int) -> bool:
        if not isinstance(l, int) or not isinstance(r, int):
            raise TypeError("has_nonzero(l, r): l and r must be int")
        if len(self._array) == 0:
            raise IndexError("has_nonzero(l, r) called on empty array")
        if not (0 <= l <= r < len(self._array)):
            raise IndexError(
                f"has_nonzero({l}, {r}) out of bounds for n={len(self._array)}"
            )

        self._charge(self._rng.randint(5, 15))
        return any(value != 0 for value in self._array[l:r + 1])


def worker_run(
    solution_path: str,
    test_path: str,
    seed: int,
    queue: mp.Queue,
) -> None:
    start_time = time.perf_counter()

    try:
        test_file = Path(test_path)
        array = load_test_array(test_file)
        expected = load_expected_answer(test_file, array)

        rng = random.Random(seed)
        api = WarehouseAPI(array, rng)

        module_name = f"participant_solution_{os.getpid()}_{seed}_{int(time.time() * 1000)}"
        spec = importlib.util.spec_from_file_location(module_name, solution_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot import solution from {solution_path}")

        module = importlib.util.module_from_spec(spec)

        import types
        fake_mod = types.ModuleType("warehouse_api")
        fake_mod.WarehouseAPI = WarehouseAPI
        sys.modules["warehouse_api"] = fake_mod

        spec.loader.exec_module(module)

        if not hasattr(module, "solve"):
            raise AttributeError("Solution file must define function solve(api)")

        solve_function = module.solve
        if not callable(solve_function):
            raise TypeError("solve must be callable")

        stdout_buffer = io.StringIO()
        with redirect_stdout(stdout_buffer):
            answer = solve_function(api)

        stdout_text = stdout_buffer.getvalue().strip()

        if answer is None:
            if stdout_text == "":
                raise RuntimeError(
                    "solve(api) returned None and printed nothing. "
                    "Return the answer or print it."
                )

            last_line = stdout_text.splitlines()[-1].strip()
            try:
                answer = int(last_line)
            except ValueError as exc:
                raise RuntimeError(
                    "solve(api) returned None, and the last printed line "
                    f"is not an integer: {last_line!r}"
                ) from exc

        if not isinstance(answer, int):
            raise TypeError(f"Answer must be int, got {type(answer).__name__}")

        elapsed = time.perf_counter() - start_time
        ok = (answer == expected)

        result = SingleRunResult(
            ok=ok,
            verdict="OK" if ok else "WA",
            answer=answer,
            expected=expected,
            total_cost=api.total_cost,
            elapsed_sec=elapsed,
            seed=seed,
        )
        queue.put(result)

    except Exception:
        elapsed = time.perf_counter() - start_time
        result = SingleRunResult(
            ok=False,
            verdict="RE",
            answer=None,
            expected=-1,
            total_cost=0,
            elapsed_sec=elapsed,
            seed=seed,
            error_text=traceback.format_exc(),
        )
        queue.put(result)


def run_single_with_timeout(
    solution_path: Path,
    test_path: Path,
    seed: int,
    timeout_sec: float,
) -> SingleRunResult:
    ctx = mp.get_context("spawn")
    queue: mp.Queue = ctx.Queue()

    process = ctx.Process(
        target=worker_run,
        args=(str(solution_path), str(test_path), seed, queue),
    )

    process.start()
    process.join(timeout=timeout_sec)

    if process.is_alive():
        process.terminate()
        process.join()

        return SingleRunResult(
            ok=False,
            verdict="TL",
            answer=None,
            expected=-1,
            total_cost=0,
            elapsed_sec=timeout_sec,
            seed=seed,
            error_text=f"Time limit exceeded: {timeout_sec:.3f}s",
        )

    if queue.empty():
        return SingleRunResult(
            ok=False,
            verdict="JE",
            answer=None,
            expected=-1,
            total_cost=0,
            elapsed_sec=0.0,
            seed=seed,
            error_text="Judge error: worker exited without returning a result",
        )

    return queue.get()


def run_test_case(
    solution_path: Path,
    test_path: Path,
    runs_per_test: int,
    timeout_sec: float,
    base_seed: int,
) -> TestCaseSummary:
    array = load_test_array(test_path)
    expected = load_expected_answer(test_path, array)

    runs: list[SingleRunResult] = []
    for run_index in range(runs_per_test):
        seed = base_seed + run_index
        result = run_single_with_timeout(solution_path, test_path, seed, timeout_sec)
        runs.append(result)

    passed_all_runs = all(run.ok for run in runs)

    effective_cost = (
        max(run.total_cost for run in runs)
        if passed_all_runs and runs
        else 0.0
    )

    base_points = compute_points(effective_cost) if passed_all_runs else 0
    weight = get_test_weight(test_path.stem)
    weighted_points = (base_points * weight) // 100

    return TestCaseSummary(
        test_name=test_path.name,
        runs=runs,
        passed_all_runs=passed_all_runs,
        effective_cost=effective_cost,
        base_points=base_points,
        weighted_points=weighted_points,
        weight=weight,
        expected=expected,
    )


def discover_tests(tests_dir: Path) -> list[Path]:
    tests = sorted(
        path
        for path in tests_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".json"
    )

    if not tests:
        raise FileNotFoundError(f"No .json tests found in directory: {tests_dir}")

    return tests


def print_test_header(summary: TestCaseSummary) -> None:
    print("=" * 100)
    print(f"TEST: {summary.test_name}")
    print(f"EXPECTED ANSWER: {summary.expected}")
    print(f"WEIGHT: {summary.weight}")
    print("=" * 100)


def print_run_result(run: SingleRunResult) -> None:
    line = (
        f"seed={run.seed:<10} | "
        f"verdict={run.verdict:<2} | "
        f"cost={run.total_cost:<8} | "
        f"time={run.elapsed_sec:.4f}s"
    )

    if run.verdict == "WA":
        line += f" | expected={run.expected}, got={run.answer}"

    print(line)

    if run.error_text and run.verdict in {"RE", "TL", "JE"}:
        print("  details:")
        for error_line in run.error_text.strip().splitlines():
            print(f"    {error_line}")


def print_summary(summaries: list[TestCaseSummary]) -> None:
    total_points = 0
    max_points = sum(summary.weight for summary in summaries)

    print("\n" + "#" * 100)
    print("PER-TEST RESULTS")
    print("#" * 100 + "\n")

    for summary in summaries:
        print_test_header(summary)

        for run in summary.runs:
            print_run_result(run)

        if summary.passed_all_runs:
            print(
                f"\nPASSED ALL RUNS | effective_cost={summary.effective_cost:.2f} "
                f"| base_points={summary.base_points}/100 "
                f"| weighted_points={summary.weighted_points}/{summary.weight}"
            )
        else:
            print(
                f"\nFAILED AT LEAST ONE RUN | effective_cost=--- "
                f"| weighted_points=0/{summary.weight}"
            )

        print()
        total_points += summary.weighted_points

    print("#" * 100)
    print(f"TOTAL SCORE: {total_points}/{max_points}")
    print("#" * 100)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Local judge for the WarehouseAPI optimization problem"
    )
    parser.add_argument(
        "solution",
        type=str,
        help="Path to participant Python solution",
    )
    parser.add_argument(
        "tests",
        type=str,
        help="Path to directory with .json tests",
    )
    parser.add_argument(
        "--runs-per-test",
        type=int,
        default=5,
        help="Number of runs per test with different random seeds (default: 5)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="Time limit per run in seconds (default: 3.0)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260314,
        help="Base random seed for reproducibility (default: 20260314)",
    )

    args = parser.parse_args()

    solution_path = Path(args.solution).resolve()
    tests_dir = Path(args.tests).resolve()

    if not solution_path.is_file():
        raise FileNotFoundError(f"Solution file not found: {solution_path}")

    if not tests_dir.is_dir():
        raise NotADirectoryError(f"Tests directory not found: {tests_dir}")

    if args.runs_per_test <= 0:
        raise ValueError("--runs-per-test must be positive")

    if args.timeout <= 0:
        raise ValueError("--timeout must be positive")

    tests = discover_tests(tests_dir)

    summaries: list[TestCaseSummary] = []
    for test_index, test_path in enumerate(tests):
        summary = run_test_case(
            solution_path=solution_path,
            test_path=test_path,
            runs_per_test=args.runs_per_test,
            timeout_sec=args.timeout,
            base_seed=args.seed + test_index * 1000,
        )
        summaries.append(summary)

    print_summary(summaries)


if __name__ == "__main__":
    main()
