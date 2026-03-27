from __future__ import annotations

import copy
import importlib.util
import os
import sys
import types
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

getcontext().prec = 28


class CargoStatus(Enum):
    CREATED = "CREATED"
    LOADED = "LOADED"
    ARRIVED = "ARRIVED"
    INVOICED = "INVOICED"
    CANCELLED = "CANCELLED"


@dataclass
class Cargo:
    id: int
    public_id: str
    client_id: int
    status: CargoStatus
    declared_value: Decimal
    final_value: Decimal
    _dirty: bool = False


@dataclass
class Client:
    id: int
    rebate_percent: Decimal


@dataclass
class Metrics:
    cargos_calls: int = 0
    cargos_filtered_calls: int = 0
    cargos_unfiltered_calls: int = 0
    cargos_returned_count: int = 0
    insurance_calls: int = 0
    client_calls: int = 0
    mark_dirty_calls: int = 0
    save_dirty_calls: int = 0
    parse_status_calls: int = 0
    format_status_calls: int = 0
    virtual_cost: int = 0

    def absorb(self, other: "Metrics") -> None:
        for key in self.__dataclass_fields__:
            setattr(self, key, getattr(self, key) + getattr(other, key))


@dataclass
class Environment:
    cargo_by_public_id: Dict[str, Cargo]
    cargo_by_id: Dict[int, Cargo]
    client_by_id: Dict[int, Client]
    multiplier_by_cargo_id: Dict[int, Decimal]
    dirty_ids: set[int] = field(default_factory=set)
    persisted_snapshot: Dict[int, Cargo] = field(default_factory=dict)
    metrics: Metrics = field(default_factory=Metrics)


CURRENT_ENV: Optional[Environment] = None


def _require_env() -> Environment:
    if CURRENT_ENV is None:
        raise RuntimeError("Environment is not initialized")
    return CURRENT_ENV


def orbital_cargos(public_ids: Sequence[str], status: Optional[CargoStatus] = None) -> List[Cargo]:
    env = _require_env()
    env.metrics.cargos_calls += 1
    if status is None:
        env.metrics.cargos_unfiltered_calls += 1
    else:
        env.metrics.cargos_filtered_calls += 1
    out: List[Cargo] = []
    for public_id in public_ids:
        cargo = env.cargo_by_public_id.get(public_id)
        if cargo is None:
            continue
        if status is not None and cargo.status != status:
            continue
        out.append(cargo)
    env.metrics.cargos_returned_count += len(out)
    env.metrics.virtual_cost += 500 + 2 * len(out)
    return out


def orbital_insurance_multiplier(internal_cargo_id: int) -> Decimal:
    env = _require_env()
    env.metrics.insurance_calls += 1
    env.metrics.virtual_cost += 12
    return env.multiplier_by_cargo_id[internal_cargo_id]


def orbital_client(client_id: int) -> Client:
    env = _require_env()
    env.metrics.client_calls += 1
    env.metrics.virtual_cost += 7
    return env.client_by_id[client_id]


def orbital_mark_dirty(entity: Cargo) -> None:
    env = _require_env()
    entity._dirty = True
    env.dirty_ids.add(entity.id)
    env.metrics.mark_dirty_calls += 1
    env.metrics.virtual_cost += 1


def orbital_save_dirty() -> None:
    env = _require_env()
    dirty_ids = sorted(env.dirty_ids)
    for cargo_id in dirty_ids:
        live_cargo = env.cargo_by_id[cargo_id]
        env.persisted_snapshot[cargo_id] = copy.deepcopy(live_cargo)
        live_cargo._dirty = False
    flushed = len(dirty_ids)
    env.dirty_ids.clear()
    env.metrics.save_dirty_calls += 1
    env.metrics.virtual_cost += 80 + flushed


def orbital_parse_status(status_str: str) -> CargoStatus:
    env = _require_env()
    env.metrics.parse_status_calls += 1
    env.metrics.virtual_cost += 1
    return CargoStatus[status_str]


def orbital_format_status(status_enum: CargoStatus) -> str:
    env = _require_env()
    env.metrics.format_status_calls += 1
    env.metrics.virtual_cost += 1
    return status_enum.name


def install_orbital_module() -> None:
    module = types.ModuleType("orbital")
    module.CargoStatus = CargoStatus
    module.Cargo = Cargo
    module.Client = Client
    module.cargos = orbital_cargos
    module.insurance_multiplier = orbital_insurance_multiplier
    module.client = orbital_client
    module.mark_dirty = orbital_mark_dirty
    module.save_dirty = orbital_save_dirty
    module.parse_status = orbital_parse_status
    module.format_status = orbital_format_status
    sys.modules["orbital"] = module


@dataclass
class GroupSpec:
    key: str
    points: int
    datasets: List[Dict[str, Any]]
    gate: Optional[Any] = None


def _dec(text: str) -> Decimal:
    return Decimal(text)


def make_cargo(idx: int, status: CargoStatus, client_id: int, declared: str) -> Dict[str, Any]:
    return {
        "id": idx,
        "public_id": f"TRK{idx:05d}",
        "client_id": client_id,
        "status": status,
        "declared_value": _dec(declared),
        "final_value": _dec(declared),
    }


def build_dataset(
    cargos_data: List[Dict[str, Any]],
    clients_data: List[Tuple[int, str]],
    multipliers_data: Dict[int, str],
    track_ids: List[str],
) -> Dict[str, Any]:
    return {
        "cargos": copy.deepcopy(cargos_data),
        "clients": [{"id": cid, "rebate_percent": _dec(rebate)} for cid, rebate in clients_data],
        "multipliers": {cid: _dec(mult) for cid, mult in multipliers_data.items()},
        "track_ids": list(track_ids),
    }


def tiny_dataset() -> Dict[str, Any]:
    cargos_data = [
        make_cargo(1, CargoStatus.ARRIVED, 1, "100"),
        make_cargo(2, CargoStatus.CREATED, 1, "50"),
        make_cargo(3, CargoStatus.ARRIVED, 2, "80"),
        make_cargo(4, CargoStatus.LOADED, 3, "40"),
        make_cargo(5, CargoStatus.CANCELLED, 2, "70"),
        make_cargo(6, CargoStatus.ARRIVED, 4, "20"),
    ]
    clients = [(1, "5"), (2, "10"), (3, "0"), (4, "2")]
    mult = {1: "1.20", 2: "0.80", 3: "1.00", 4: "1.50", 5: "1.10", 6: "1.00"}
    track_ids = [c["public_id"] for c in cargos_data]
    return build_dataset(cargos_data, clients, mult, track_ids)


def edge_subdatasets() -> List[Dict[str, Any]]:
    base_cargos = [
        make_cargo(10, CargoStatus.CREATED, 11, "100"),
        make_cargo(11, CargoStatus.LOADED, 11, "130"),
        make_cargo(12, CargoStatus.CANCELLED, 12, "90"),
    ]
    clients_a = [(11, "3"), (12, "7")]
    mult_a = {10: "1", 11: "1.2", 12: "0.9"}

    all_arrived = [
        make_cargo(20 + i, CargoStatus.ARRIVED, 20, str(100 + i)) for i in range(6)
    ]
    clients_b = [(20, "4")]
    mult_b = {20 + i: ("1" if i % 2 == 0 else "1.3") for i in range(6)}

    empty = build_dataset([], [(1, "1")], {}, [])
    non_arrived = build_dataset(base_cargos, clients_a, mult_a, [c["public_id"] for c in base_cargos])
    all_arrived_ds = build_dataset(all_arrived, clients_b, mult_b, [c["public_id"] for c in all_arrived])
    return [empty, non_arrived, all_arrived_ds]


def group3_dataset() -> Dict[str, Any]:
    cargos_data = []
    clients = []
    multipliers: Dict[int, str] = {}
    for i in range(1, 91):
        cid = 1000 + i
        clients.append((cid, str((i % 5) + 1)))
        cargos_data.append(make_cargo(100 + i, CargoStatus.ARRIVED, cid, str(100 + i)))
        multipliers[100 + i] = "1.40" if i % 10 else "1.10"
    track_ids = [c["public_id"] for c in cargos_data]
    return build_dataset(cargos_data, clients, multipliers, track_ids)


def group4_dataset() -> Dict[str, Any]:
    cargos_data = []
    clients = [(500 + i, str((i % 12) + 1)) for i in range(30)]
    multipliers: Dict[int, str] = {}
    for i in range(1, 241):
        client_id = 500 + (i % 30)
        cargos_data.append(make_cargo(5000 + i, CargoStatus.ARRIVED, client_id, str(200 + (i % 13))))
        multipliers[5000 + i] = "1.25" if i % 3 else "1.00"
    track_ids = [c["public_id"] for c in cargos_data]
    return build_dataset(cargos_data, clients, multipliers, track_ids)


def group5_dataset() -> Dict[str, Any]:
    cargos_data = []
    clients = [(900 + i, str((i % 8) + 1)) for i in range(40)]
    multipliers: Dict[int, str] = {}
    for i in range(1, 161):
        status = CargoStatus.ARRIVED if i % 5 else CargoStatus.LOADED
        client_id = 900 + (i % 40)
        cargos_data.append(make_cargo(8000 + i, status, client_id, str(120 + i)))
        multipliers[8000 + i] = "1.50" if i % 4 else "0.95"
    track_ids = [c["public_id"] for c in cargos_data]
    return build_dataset(cargos_data, clients, multipliers, track_ids)


def group6_dataset() -> Dict[str, Any]:
    cargos_data = []
    clients = [(1300 + i, str((i % 9) + 1)) for i in range(80)]
    multipliers: Dict[int, str] = {}
    for i in range(1, 2001):
        status = CargoStatus.ARRIVED if i % 40 == 0 else CargoStatus.LOADED
        client_id = 1300 + (i % 80)
        cargos_data.append(make_cargo(15000 + i, status, client_id, str(70 + (i % 17))))
        multipliers[15000 + i] = "1.35" if i % 6 else "1.00"
    track_ids = [c["public_id"] for c in cargos_data]
    return build_dataset(cargos_data, clients, multipliers, track_ids)


def clone_dataset(dataset: Dict[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(dataset)


def reference_compute(dataset: Dict[str, Any]) -> Tuple[List[Tuple[str, str, str]], Dict[int, Tuple[str, str]], int, int]:
    cargo_by_public = {c["public_id"]: c for c in dataset["cargos"]}
    client_by_id = {c["id"]: c for c in dataset["clients"]}
    multipliers = dataset["multipliers"]
    result: List[Tuple[str, str, str]] = []
    dirty_ids: List[int] = []
    for public_id in dataset["track_ids"]:
        cargo = cargo_by_public.get(public_id)
        if cargo is None:
            continue
        if cargo["status"] != CargoStatus.ARRIVED:
            continue
        k = multipliers[cargo["id"]]
        declared = cargo["declared_value"]
        insured = declared * k if k > Decimal("1") else declared
        rebate_percent = client_by_id[cargo["client_id"]]["rebate_percent"]
        cargo["final_value"] = insured - declared * (rebate_percent / Decimal("100"))
        cargo["status"] = CargoStatus.INVOICED
        dirty_ids.append(cargo["id"])
        result.append((cargo["public_id"], cargo["status"].name, str(cargo["final_value"])))
    persisted = {
        c["id"]: (c["status"].name, str(c["final_value"]))
        for c in dataset["cargos"]
    }
    arrived_count = len(result)
    unique_arrived_clients = len(
        {
            c["client_id"]
            for c in dataset["cargos"]
            if c["status"] == CargoStatus.INVOICED
        }
    )
    return result, persisted, arrived_count, unique_arrived_clients


def make_environment(dataset: Dict[str, Any]) -> Environment:
    cargos = [Cargo(**c) for c in dataset["cargos"]]
    cargo_by_public = {c.public_id: c for c in cargos}
    cargo_by_id = {c.id: c for c in cargos}
    clients = [Client(**c) for c in dataset["clients"]]
    client_by_id = {c.id: c for c in clients}
    persisted = {c.id: copy.deepcopy(c) for c in cargos}
    return Environment(
        cargo_by_public_id=cargo_by_public,
        cargo_by_id=cargo_by_id,
        client_by_id=client_by_id,
        multiplier_by_cargo_id=dict(dataset["multipliers"]),
        persisted_snapshot=persisted,
    )


def candidate_summary(result: Iterable[Cargo], env: Environment) -> Tuple[List[Tuple[str, str, str]], Dict[int, Tuple[str, str]]]:
    result_rows = [(c.public_id, c.status.name, str(c.final_value)) for c in result]
    persisted = {
        cid: (stored.status.name, str(stored.final_value))
        for cid, stored in sorted(env.persisted_snapshot.items())
    }
    return result_rows, persisted


def semantic_ok(candidate_result: Iterable[Cargo], env: Environment, expected_result: List[Tuple[str, str, str]], expected_persisted: Dict[int, Tuple[str, str]]) -> bool:
    actual_result, actual_persisted = candidate_summary(candidate_result, env)
    return actual_result == expected_result and actual_persisted == expected_persisted


def load_solution(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Solution file not found: {path}")
    module_name = f"candidate_{path.stem}_{abs(hash(path.resolve()))}"
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import solution: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    func = getattr(module, "process_arrived_cargos", None)
    if not callable(func):
        raise AttributeError(f"{path} must define callable process_arrived_cargos(track_ids)")
    return module, func


def run_dataset(func, dataset: Dict[str, Any]) -> Tuple[bool, Metrics, int, int]:
    reference_dataset = clone_dataset(dataset)
    expected_result, expected_persisted, arrived_count, unique_arrived_clients = reference_compute(reference_dataset)

    env_dataset = clone_dataset(dataset)
    env = make_environment(env_dataset)
    global CURRENT_ENV
    CURRENT_ENV = env
    returned = func(list(dataset["track_ids"]))
    if returned is None:
        returned = []
    ok = semantic_ok(returned, env, expected_result, expected_persisted)
    return ok, env.metrics, arrived_count, unique_arrived_clients


def score_group(group: GroupSpec, func) -> Tuple[int, bool, Metrics, List[str], int, int]:
    total_metrics = Metrics()
    diagnostics: List[str] = []
    all_semantic_ok = True
    last_arrived = 0
    last_unique_clients = 0
    for idx, dataset in enumerate(group.datasets, start=1):
        ok, metrics, arrived_count, unique_clients = run_dataset(func, dataset)
        total_metrics.absorb(metrics)
        last_arrived = arrived_count
        last_unique_clients = unique_clients
        if not ok:
            all_semantic_ok = False
            diagnostics.append(f"subtest {idx}: semantic mismatch")
    gated = True
    if all_semantic_ok and group.gate is not None:
        gated, gate_msg = group.gate(total_metrics, last_arrived, last_unique_clients)
        if not gated:
            diagnostics.append(gate_msg)
    elif not all_semantic_ok:
        gated = False
    passed = all_semantic_ok and gated
    return (group.points if passed else 0), passed, total_metrics, diagnostics, last_arrived, last_unique_clients


def gate_group3(metrics: Metrics, arrived_count: int, _unique_clients: int) -> Tuple[bool, str]:
    allowed = arrived_count + 2
    ok = metrics.insurance_calls <= allowed
    return ok, f"insurance_calls={metrics.insurance_calls} > {allowed}"


def gate_group4(metrics: Metrics, _arrived: int, unique_clients: int) -> Tuple[bool, str]:
    allowed = unique_clients + 2
    ok = metrics.client_calls <= allowed
    return ok, f"client_calls={metrics.client_calls} > {allowed}"


def gate_group5(metrics: Metrics, _arrived: int, _unique_clients: int) -> Tuple[bool, str]:
    ok = metrics.save_dirty_calls <= 2
    return ok, f"save_dirty_calls={metrics.save_dirty_calls} > 2"


def gate_group6(metrics: Metrics, arrived_count: int, _unique_clients: int) -> Tuple[bool, str]:
    ok = (
        metrics.cargos_calls == 1
        and metrics.cargos_filtered_calls == 1
        and metrics.cargos_unfiltered_calls == 0
        and metrics.cargos_returned_count == arrived_count
    )
    return (
        ok,
        "group6 gate failed: "
        f"cargos_calls={metrics.cargos_calls}, "
        f"filtered={metrics.cargos_filtered_calls}, "
        f"unfiltered={metrics.cargos_unfiltered_calls}, "
        f"returned={metrics.cargos_returned_count}, "
        f"arrived={arrived_count}",
    )


def build_groups() -> List[GroupSpec]:
    return [
        GroupSpec("Group 1", 8, [tiny_dataset()]),
        GroupSpec("Group 2", 10, edge_subdatasets()),
        GroupSpec("Group 3", 22, [group3_dataset()], gate_group3),
        GroupSpec("Group 4", 20, [group4_dataset()], gate_group4),
        GroupSpec("Group 5", 15, [group5_dataset()], gate_group5),
        GroupSpec("Group 6", 25, [group6_dataset()], gate_group6),
    ]


def evaluate_solution(solution_path: Path) -> Tuple[int, List[Tuple[str, int, int, bool, Metrics, List[str]]], Metrics]:
    _, func = load_solution(solution_path)
    groups = build_groups()
    total = 0
    report_rows = []
    aggregate = Metrics()
    for group in groups:
        score, passed, metrics, diagnostics, _, _ = score_group(group, func)
        total += score
        aggregate.absorb(metrics)
        report_rows.append((group.key, score, group.points, passed, metrics, diagnostics))
    return total, report_rows, aggregate


def print_report(solution_path: Path, total: int, report_rows, aggregate: Metrics) -> None:
    print(f"Solution: {solution_path.name}")
    for key, score, points, passed, metrics, diagnostics in report_rows:
        state = "PASS" if passed else "FAIL"
        print(f"  {key}: {state} {score}/{points} | virtual_cost={metrics.virtual_cost}")
        print(
            "    metrics: "
            f"cargos={metrics.cargos_calls} (f={metrics.cargos_filtered_calls}, u={metrics.cargos_unfiltered_calls}, ret={metrics.cargos_returned_count}), "
            f"ins={metrics.insurance_calls}, client={metrics.client_calls}, dirty={metrics.mark_dirty_calls}, save={metrics.save_dirty_calls}, "
            f"parse={metrics.parse_status_calls}, format={metrics.format_status_calls}"
        )
        for diag in diagnostics:
            print(f"    note: {diag}")
    print(f"  TOTAL: {total}/100")
    print(
        "  aggregate metrics: "
        f"cargos={aggregate.cargos_calls}, insurance={aggregate.insurance_calls}, client={aggregate.client_calls}, "
        f"mark_dirty={aggregate.mark_dirty_calls}, save_dirty={aggregate.save_dirty_calls}, virtual_cost={aggregate.virtual_cost}"
    )
    print()


def run(paths: List[Path]) -> int:
    install_orbital_module()
    outcomes = []
    for path in paths:
        total, rows, aggregate = evaluate_solution(path)
        print_report(path, total, rows, aggregate)
        outcomes.append((path.name, total))

    if len(paths) == 2 and {p.name for p in paths} == {"bad_solution.py", "best_solution.py"}:
        mapping = dict(outcomes)
        bad_score = mapping["bad_solution.py"]
        best_score = mapping["best_solution.py"]
        if not bad_score < 20:
            print(f"Invariant failed: bad_solution.py must be < 20, got {bad_score}")
            return 1
        if best_score != 100:
            print(f"Invariant failed: best_solution.py must be 100, got {best_score}")
            return 1
    return 0


def main(argv: List[str]) -> int:
    if len(argv) == 1:
        default_paths = [Path("bad_solution.py"), Path("best_solution.py")]
        return run(default_paths)
    if len(argv) == 2:
        return run([Path(argv[1])])
    print("Usage: python judge.py [candidate_solution.py]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
