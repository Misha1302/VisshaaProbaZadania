import argparse
import importlib.util
import math
import os
import random
import traceback
from dataclasses import dataclass
from typing import List, Tuple, Optional


SIZE_COST = 5
HAS_EDGE_COST = 12
OUT_NEIGHBORS_COST = 35

MAX_TESTS = 50
RANDOM_SEED = 1337

# Калибровка под текущий набор из 50 тестов:
# bad.py  -> 858_343_054
# best.py ->     922_570
REFERENCE_BAD_TOTAL_COST = 858_343_054
REFERENCE_BEST_TOTAL_COST = 922_570


class WrongAnswer(Exception):
    pass


class PresentationError(Exception):
    pass


@dataclass
class JudgeResult:
    ok: bool
    cost: int
    expected: Optional[int]
    received: Optional[int]
    message: str
    stats: dict


class GraphAPI:
    def __init__(self, out_adj: List[List[int]]):
        self._n = len(out_adj)
        self._out_adj = [list(nei) for nei in out_adj]
        self._out_sets = [set(nei) for nei in out_adj]
        self._cost = 0
        self._size_calls = 0
        self._has_edge_calls = 0
        self._out_neighbors_calls = 0

    @property
    def cost(self) -> int:
        return self._cost

    @property
    def stats(self) -> dict:
        return {
            "size_calls": self._size_calls,
            "has_edge_calls": self._has_edge_calls,
            "out_neighbors_calls": self._out_neighbors_calls,
            "total_cost": self._cost,
        }

    def size(self) -> int:
        self._cost += SIZE_COST
        self._size_calls += 1
        return self._n

    def has_edge(self, u: int, v: int) -> bool:
        self._validate_vertex(u)
        self._validate_vertex(v)
        self._cost += HAS_EDGE_COST
        self._has_edge_calls += 1
        return v in self._out_sets[u]

    def out_neighbors(self, v: int) -> List[int]:
        self._validate_vertex(v)
        self._cost += OUT_NEIGHBORS_COST
        self._out_neighbors_calls += 1
        return list(self._out_adj[v])

    def _validate_vertex(self, v: int) -> None:
        if not isinstance(v, int):
            raise PresentationError(f"Vertex must be int, got {type(v).__name__}")
        if not (0 <= v < self._n):
            raise PresentationError(f"Vertex index out of range: {v}")


def validate_graph(out_adj: List[List[int]]) -> None:
    n = len(out_adj)
    edge_count = 0

    for u in range(n):
        seen = set()

        for v in out_adj[u]:
            if not isinstance(v, int):
                raise ValueError(f"Edge endpoint must be int, got {type(v).__name__}")

            if not (0 <= v < n):
                raise ValueError(f"Edge {u}->{v} goes out of range")

            if u >= v:
                raise ValueError(f"Invalid edge {u}->{v}: must satisfy u < v")

            if v in seen:
                raise ValueError(f"Duplicate edge {u}->{v}")

            seen.add(v)
            edge_count += 1

    if not (1 <= n <= 2 * 10**5):
        raise ValueError(f"N = {n} is outside allowed range")

    if not (0 <= edge_count <= 4 * 10**5):
        raise ValueError(f"M = {edge_count} is outside allowed range")


def reference_solve(out_adj: List[List[int]]) -> int:
    n = len(out_adj)
    dp = [0] * n
    ans = 0

    for u in range(n):
        cur = dp[u]
        if cur > ans:
            ans = cur

        for v in out_adj[u]:
            cand = cur + 1
            if cand > dp[v]:
                dp[v] = cand

    for value in dp:
        if value > ans:
            ans = value

    return ans


def resolve_participant_path(name: str) -> str:
    if os.path.isfile(name):
        return name

    if not name.endswith(".py"):
        alt = name + ".py"
        if os.path.isfile(alt):
            return alt

    raise FileNotFoundError(f"Cannot find participant script: {name}")


def load_participant_solution(script_name: str):
    participant_path = resolve_participant_path(script_name)
    spec = importlib.util.spec_from_file_location("participant_solution", participant_path)

    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load solution file: {participant_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "solve"):
        raise RuntimeError("Participant file does not contain solve(api)")

    solve = getattr(module, "solve")
    if not callable(solve):
        raise RuntimeError("solve is not callable")

    return solve


def judge_one(out_adj: List[List[int]], participant_solve) -> JudgeResult:
    try:
        validate_graph(out_adj)
    except Exception as ex:
        return JudgeResult(
            ok=False,
            cost=0,
            expected=None,
            received=None,
            message=f"Invalid test data: {ex}",
            stats={},
        )

    expected = reference_solve(out_adj)
    api = GraphAPI(out_adj)

    try:
        received = participant_solve(api)
    except Exception as ex:
        return JudgeResult(
            ok=False,
            cost=api.cost,
            expected=expected,
            received=None,
            message="Runtime error:\n" + "".join(traceback.format_exception(ex)),
            stats=api.stats,
        )

    if not isinstance(received, int):
        return JudgeResult(
            ok=False,
            cost=api.cost,
            expected=expected,
            received=None,
            message=f"solve(api) must return int, got {type(received).__name__}",
            stats=api.stats,
        )

    if received != expected:
        return JudgeResult(
            ok=False,
            cost=api.cost,
            expected=expected,
            received=received,
            message="Wrong answer",
            stats=api.stats,
        )

    return JudgeResult(
        ok=True,
        cost=api.cost,
        expected=expected,
        received=received,
        message="OK",
        stats=api.stats,
    )


def global_score_by_total_cost(total_cost: int) -> int:
    if total_cost <= 0:
        return 0

    if total_cost <= REFERENCE_BEST_TOTAL_COST:
        return 100

    numerator = math.log(REFERENCE_BAD_TOTAL_COST / total_cost)
    denominator = math.log(REFERENCE_BAD_TOTAL_COST / REFERENCE_BEST_TOTAL_COST)

    value = 10 + 90 * (numerator / denominator)
    value = max(0.0, min(100.0, value))

    return round(value)


def judge_many(tests: List[List[List[int]]], script_name: str) -> Tuple[int, List[JudgeResult], int]:
    participant_solve = load_participant_solution(script_name)
    results = []

    for out_adj in tests:
        result = judge_one(out_adj, participant_solve)
        results.append(result)

    if any(not r.ok for r in results):
        return 0, results, sum(r.cost for r in results)

    total_cost = sum(r.cost for r in results)
    total_score = global_score_by_total_cost(total_cost)

    return total_score, results, total_cost


def make_empty_graph(n: int) -> List[List[int]]:
    return [[] for _ in range(n)]


def make_chain_graph(n: int) -> List[List[int]]:
    out_adj = [[] for _ in range(n)]
    for i in range(n - 1):
        out_adj[i].append(i + 1)
    return out_adj


def make_star_graph(n: int) -> List[List[int]]:
    out_adj = [[] for _ in range(n)]
    for i in range(1, n):
        out_adj[0].append(i)
    return out_adj


def make_reverse_star_graph(n: int) -> List[List[int]]:
    out_adj = [[] for _ in range(n)]
    for i in range(n - 1):
        out_adj[i].append(n - 1)
    return out_adj


def make_complete_dag(n: int) -> List[List[int]]:
    out_adj = [[] for _ in range(n)]
    for u in range(n):
        for v in range(u + 1, n):
            out_adj[u].append(v)
    return out_adj


def make_two_layer_graph(a: int, b: int) -> List[List[int]]:
    n = a + b
    out_adj = [[] for _ in range(n)]
    for u in range(a):
        for v in range(a, n):
            out_adj[u].append(v)
    return out_adj


def make_binary_like_dag(n: int) -> List[List[int]]:
    out_adj = [[] for _ in range(n)]
    for u in range(n):
        left = 2 * u + 1
        right = 2 * u + 2
        if left < n:
            out_adj[u].append(left)
        if right < n:
            out_adj[u].append(right)
    return out_adj


def make_ladder_graph(levels: int) -> List[List[int]]:
    n = levels * 2
    out_adj = [[] for _ in range(n)]

    for i in range(levels - 1):
        a = 2 * i
        b = 2 * i + 1
        na = 2 * (i + 1)
        nb = 2 * (i + 1) + 1

        out_adj[a].append(na)
        out_adj[a].append(nb)
        out_adj[b].append(na)
        out_adj[b].append(nb)

    return out_adj


def make_skip_chain(n: int, max_jump: int) -> List[List[int]]:
    out_adj = [[] for _ in range(n)]
    for u in range(n):
        for jump in range(1, max_jump + 1):
            v = u + jump
            if v < n:
                out_adj[u].append(v)
    return out_adj


def make_random_dag(n: int, m: int, rng: random.Random) -> List[List[int]]:
    max_edges = n * (n - 1) // 2
    m = min(m, max_edges)

    all_edges = []
    for u in range(n):
        for v in range(u + 1, n):
            all_edges.append((u, v))

    rng.shuffle(all_edges)
    chosen = all_edges[:m]

    out_adj = [[] for _ in range(n)]
    for u, v in chosen:
        out_adj[u].append(v)

    for u in range(n):
        out_adj[u].sort()

    return out_adj


def make_sparse_random_progressive_dag(n: int, rng: random.Random) -> List[List[int]]:
    out_adj = [[] for _ in range(n)]

    for u in range(n):
        max_deg = min(6, n - 1 - u)
        deg = rng.randint(0, max_deg)
        candidates = list(range(u + 1, n))
        rng.shuffle(candidates)
        out_adj[u] = sorted(candidates[:deg])

    return out_adj


def build_tests() -> List[List[List[int]]]:
    rng = random.Random(RANDOM_SEED)
    tests = []

    tests.append([[]])                                      # 1
    tests.append(make_empty_graph(2))                       # 2
    tests.append(make_chain_graph(2))                       # 3
    tests.append(make_chain_graph(3))                       # 4
    tests.append(make_chain_graph(5))                       # 5
    tests.append(make_star_graph(6))                        # 6
    tests.append(make_reverse_star_graph(6))                # 7
    tests.append(make_complete_dag(4))                      # 8
    tests.append(make_complete_dag(6))                      # 9
    tests.append(make_two_layer_graph(3, 4))                # 10
    tests.append(make_two_layer_graph(5, 5))                # 11
    tests.append(make_binary_like_dag(7))                   # 12
    tests.append(make_binary_like_dag(15))                  # 13
    tests.append(make_ladder_graph(4))                      # 14
    tests.append(make_ladder_graph(8))                      # 15
    tests.append(make_skip_chain(10, 2))                    # 16
    tests.append(make_skip_chain(12, 3))                    # 17
    tests.append(make_skip_chain(20, 4))                    # 18
    tests.append(make_random_dag(8, 10, rng))               # 19
    tests.append(make_random_dag(10, 20, rng))              # 20

    for _ in range(15):
        n = rng.randint(12, 40)
        max_edges = min(n * (n - 1) // 2, 120)
        m = rng.randint(0, max_edges)
        tests.append(make_random_dag(n, m, rng))

    for _ in range(10):
        n = rng.randint(30, 120)
        tests.append(make_sparse_random_progressive_dag(n, rng))

    tests.append(make_chain_graph(5000))                         # 46
    tests.append(make_star_graph(5000))                          # 47
    tests.append(make_reverse_star_graph(5000))                  # 48
    tests.append(make_skip_chain(2000, 10))                      # 49
    tests.append(make_sparse_random_progressive_dag(8000, rng))  # 50

    if len(tests) != MAX_TESTS:
        raise RuntimeError(f"Expected {MAX_TESTS} tests, got {len(tests)}")

    return tests


def print_summary(total_score: int, results: List[JudgeResult], total_cost: int) -> None:
    total = len(results)
    passed = sum(1 for r in results if r.ok)
    failed = total - passed

    if failed > 0:
        print("Failed tests:")
        for i, result in enumerate(results, 1):
            if not result.ok:
                print(f"  Test #{i}")
                print(f"    verdict : {result.message}")
                print(f"    cost    : {result.cost}")
                print(f"    expected: {result.expected}")
                print(f"    got     : {result.received}")
                print(
                    f"    calls   : size={result.stats.get('size_calls', 0)}, "
                    f"has_edge={result.stats.get('has_edge_calls', 0)}, "
                    f"out_neighbors={result.stats.get('out_neighbors_calls', 0)}"
                )
                print()

    print("Summary:")
    print(f"  Tests total      : {total}")
    print(f"  Passed           : {passed}")
    print(f"  Failed           : {failed}")
    print(f"  Total API cost   : {total_cost}")

    if passed > 0:
        costs = [r.cost for r in results if r.ok]
        print(f"  Min test cost    : {min(costs)}")
        print(f"  Max test cost    : {max(costs)}")
        print(f"  Avg test cost    : {sum(costs) // len(costs)}")

    print()
    print("Calibration:")
    print(f"  bad.py total cost  = {REFERENCE_BAD_TOTAL_COST}  -> about 10 points")
    print(f"  best.py total cost = {REFERENCE_BEST_TOTAL_COST} -> 100 points")
    print()
    print(f"FINAL SCORE: {total_score}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "script",
        help="Имя файла с решением участника: solution.py или просто solution",
    )
    args = parser.parse_args()

    tests = build_tests()
    total_score, results, total_cost = judge_many(tests, args.script)
    print_summary(total_score, results, total_cost)


if __name__ == "__main__":
    main()
