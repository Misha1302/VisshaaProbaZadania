#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence


MAX_N = 100_000
MAX_A = 10**9
MAX_NONZERO_RATIO = 0.02
MAX_BLOCKS = 40


@dataclass
class TestSpec:
    name: str
    array: List[int]
    meta: dict


def count_nonzero_blocks(arr: Sequence[int]) -> int:
    blocks = 0
    inside = False

    for x in arr:
        if x != 0:
            if not inside:
                blocks += 1
                inside = True
        else:
            inside = False

    return blocks


def validate_array(arr: Sequence[int]) -> None:
    if not isinstance(arr, Sequence):
        raise TypeError("Array must be a sequence")

    n = len(arr)
    if not (0 <= n <= MAX_N):
        raise ValueError(f"Invalid n={n}, expected 0 <= n <= {MAX_N}")

    nonzero = 0
    for i, x in enumerate(arr):
        if not isinstance(x, int):
            raise TypeError(f"arr[{i}] is not int: {type(x).__name__}")
        if not (0 <= x <= MAX_A):
            raise ValueError(f"arr[{i}]={x} is out of range [0, {MAX_A}]")
        if x != 0:
            nonzero += 1

    max_nonzero = int(MAX_NONZERO_RATIO * n)
    if nonzero > max_nonzero:
        raise ValueError(
            f"Too many nonzero elements: {nonzero}, allowed at most {max_nonzero}"
        )

    blocks = count_nonzero_blocks(arr)
    if blocks > MAX_BLOCKS:
        raise ValueError(
            f"Too many nonzero blocks: {blocks}, allowed at most {MAX_BLOCKS}"
        )


def save_test(spec: TestSpec, out_dir: Path) -> None:
    validate_array(spec.array)

    payload = {
        "array": spec.array,
        "meta": spec.meta,
    }

    json_path = out_dir / f"{spec.name}.json"
    with json_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False)

    ans_path = out_dir / f"{spec.name}.ans"
    with ans_path.open("w", encoding="utf-8") as file:
        file.write(str(sum(spec.array)) + "\n")


def random_value(rng: random.Random, max_value: int = MAX_A) -> int:
    return rng.randint(1, max_value)


def make_array_with_positions(
    n: int,
    positions: Sequence[int],
    values: Sequence[int],
) -> List[int]:
    if len(positions) != len(values):
        raise ValueError("positions and values must have the same length")

    arr = [0] * n
    for pos, value in zip(positions, values):
        if not (0 <= pos < n):
            raise ValueError(f"Invalid position {pos} for n={n}")
        if value == 0:
            raise ValueError("Nonzero positions must have nonzero values")
        arr[pos] = value

    validate_array(arr)
    return arr


def place_blocks(
    n: int,
    block_lengths: Sequence[int],
    rng: random.Random,
    value_mode: str = "random",
) -> List[int]:
    if n < 0:
        raise ValueError("n must be non-negative")
    if any(length <= 0 for length in block_lengths):
        raise ValueError("All block lengths must be positive")

    total_nonzero = sum(block_lengths)
    if total_nonzero > n:
        raise ValueError("Total block lengths exceed n")

    gaps_count = len(block_lengths) + 1
    min_required_zeros = max(0, len(block_lengths) - 1)
    free_zeros = n - total_nonzero - min_required_zeros
    if free_zeros < 0:
        raise ValueError("Not enough space to separate blocks")

    gaps = [0] * gaps_count

    for i in range(1, len(block_lengths)):
        gaps[i] = 1

    for _ in range(free_zeros):
        gaps[rng.randrange(gaps_count)] += 1

    arr = [0] * n
    pos = gaps[0]

    for block_index, block_len in enumerate(block_lengths):
        for offset in range(block_len):
            if value_mode == "random":
                value = random_value(rng)
            elif value_mode == "small":
                value = rng.randint(1, 20)
            elif value_mode == "ones":
                value = 1
            elif value_mode == "powers":
                value = 1 << rng.randint(0, 29)
            elif value_mode == "alternating_big":
                value = MAX_A if (offset % 2 == 0) else 1
            else:
                raise ValueError(f"Unknown value_mode={value_mode}")

            arr[pos + offset] = value

        pos += block_len
        if block_index + 1 < len(block_lengths):
            pos += gaps[block_index + 1]

    validate_array(arr)
    return arr


def add_test(
    tests: List[TestSpec],
    name: str,
    arr: List[int],
    group: str,
    note: str,
    sub_group: str = "",
) -> None:
    tests.append(
        TestSpec(
            name=name,
            array=arr,
            meta={
                "group": group,
                "sub_group": sub_group,
                "note": note,
                "n": len(arr),
                "nonzero": sum(1 for x in arr if x != 0),
                "blocks": count_nonzero_blocks(arr),
            },
        )
    )


def make_manual_tests() -> List[TestSpec]:
    tests: List[TestSpec] = []

    add_test(tests, "manual_001_empty", [], "manual", "Empty array")
    add_test(tests, "manual_002_one_zero", [0], "manual", "Single zero")
    add_test(tests, "manual_003_small_all_zero", [0, 0, 0, 0, 0], "manual", "Small zero-only")
    add_test(tests, "manual_004_n49_all_zero", [0] * 49, "manual", "n<50 => nonzero impossible")
    add_test(
        tests,
        "manual_005_n50_one_center",
        make_array_with_positions(50, [25], [17]),
        "manual",
        "First size where one nonzero is allowed",
    )
    add_test(
        tests,
        "manual_006_n100_two_singletons",
        make_array_with_positions(100, [10, 90], [3, 5]),
        "manual",
        "Two singleton blocks",
    )
    add_test(
        tests,
        "manual_007_n150_prefix_block",
        make_array_with_positions(150, [0, 1, 2], [7, 8, 9]),
        "manual",
        "Prefix block",
    )
    add_test(
        tests,
        "manual_008_n150_suffix_block",
        make_array_with_positions(150, [147, 148, 149], [5, 6, 7]),
        "manual",
        "Suffix block",
    )
    add_test(
        tests,
        "manual_009_n200_middle_dense",
        make_array_with_positions(200, [98, 99, 100, 101], [1, 2, 3, 4]),
        "manual",
        "Middle dense block",
    )
    add_test(
        tests,
        "manual_010_n200_big_values",
        make_array_with_positions(200, [20, 70, 150], [MAX_A, MAX_A - 1, 123456789]),
        "manual",
        "Large values",
    )

    return tests


def make_small_random_tests(rng: random.Random) -> List[TestSpec]:
    tests: List[TestSpec] = []

    for idx in range(12):
        n = rng.randint(1, 120)
        max_nonzero = int(MAX_NONZERO_RATIO * n)

        if max_nonzero == 0:
            arr = [0] * n
        else:
            blocks = rng.randint(1, max(1, min(MAX_BLOCKS, max_nonzero)))
            block_lengths = [1] * blocks
            remaining = max_nonzero - blocks
            for _ in range(remaining):
                block_lengths[rng.randrange(blocks)] += 1
            arr = place_blocks(
                n,
                block_lengths,
                rng,
                value_mode=rng.choice(["small", "random", "ones"]),
            )

        add_test(
            tests,
            f"small_{idx:03d}",
            arr,
            "small",
            "Small random correctness test",
            "small_random",
        )

    for idx in range(8):
        n = rng.randint(50, 300)
        max_nonzero = int(MAX_NONZERO_RATIO * n)
        if max_nonzero == 0:
            arr = [0] * n
        else:
            shape_type = rng.choice(["one", "few", "many"])
            if shape_type == "one":
                block_lengths = [rng.randint(1, max_nonzero)]
            elif shape_type == "few":
                blocks = rng.randint(1, min(4, max_nonzero))
                block_lengths = [1] * blocks
                for _ in range(max_nonzero - blocks):
                    block_lengths[rng.randrange(blocks)] += 1
            else:
                blocks = min(max_nonzero, rng.randint(1, min(10, max_nonzero)))
                block_lengths = [1] * blocks

            arr = place_blocks(
                n,
                block_lengths,
                rng,
                value_mode=rng.choice(["small", "powers"]),
            )

        add_test(
            tests,
            f"small_weird_{idx:03d}",
            arr,
            "small",
            "Small weird-shape correctness test",
            "small_weird",
        )

    return tests


def make_large_generated_tests(rng: random.Random) -> List[TestSpec]:
    tests: List[TestSpec] = []

    for n in [1000, 5000, 20000, 50000, 100000]:
        add_test(
            tests,
            f"large_all_zero_{n}",
            [0] * n,
            "large",
            "Large all-zero test",
            "all_zero",
        )

    for idx in range(10):
        n = 100000
        max_nonzero = int(MAX_NONZERO_RATIO * n)
        arr = place_blocks(n, [max_nonzero], rng, value_mode="random")
        add_test(
            tests,
            f"large_one_huge_block_{idx:03d}",
            arr,
            "large",
            "Single huge block near nonzero limit",
            "one_huge_block",
        )

    for idx in range(14):
        n = 100000
        arr = place_blocks(n, [1] * MAX_BLOCKS, rng, value_mode="ones")
        add_test(
            tests,
            f"large_max_blocks_singletons_{idx:03d}",
            arr,
            "large",
            "Maximum number of singleton blocks",
            "max_blocks_singletons",
        )

    for idx in range(18):
        n = 100000
        max_nonzero = int(MAX_NONZERO_RATIO * n)
        blocks = rng.randint(8, MAX_BLOCKS)
        block_lengths = [1] * blocks
        remaining = max_nonzero - blocks
        for _ in range(remaining):
            block_lengths[rng.randrange(blocks)] += 1

        arr = place_blocks(
            n,
            block_lengths,
            rng,
            value_mode=rng.choice(["random", "alternating_big", "powers"]),
        )
        add_test(
            tests,
            f"large_near_limit_{idx:03d}",
            arr,
            "large",
            "Near nonzero limit with many irregular blocks",
            "near_limit",
        )

    for idx in range(10):
        n = 100000
        blocks = rng.randint(25, MAX_BLOCKS)
        max_nonzero = int(MAX_NONZERO_RATIO * n)
        block_lengths = [1] * blocks
        extra = rng.randint(blocks, min(max_nonzero, 700))
        remaining = extra - blocks
        for _ in range(remaining):
            block_lengths[rng.randrange(blocks)] += 1

        arr = place_blocks(
            n,
            block_lengths,
            rng,
            value_mode=rng.choice(["small", "random"]),
        )
        add_test(
            tests,
            f"large_many_short_blocks_{idx:03d}",
            arr,
            "large",
            "Many short blocks spread across the array",
            "many_short_blocks",
        )

    return tests


def make_adversarial_tests(rng: random.Random) -> List[TestSpec]:
    tests: List[TestSpec] = []
    n = 100000
    max_nonzero = int(MAX_NONZERO_RATIO * n)

    prefix = [random_value(rng) for _ in range(max_nonzero)] + [0] * (n - max_nonzero)
    add_test(tests, "adv_prefix_heavy", prefix, "adversarial", "Whole useful part in prefix")

    suffix = [0] * (n - max_nonzero) + [random_value(rng) for _ in range(max_nonzero)]
    add_test(tests, "adv_suffix_heavy", suffix, "adversarial", "Whole useful part in suffix")

    middle = [0] * n
    start = (n - max_nonzero) // 2
    for i in range(max_nonzero):
        middle[start + i] = random_value(rng)
    add_test(tests, "adv_middle_heavy", middle, "adversarial", "Whole useful part in middle")

    arr = place_blocks(n, [1] * MAX_BLOCKS, rng, value_mode="random")
    add_test(tests, "adv_sparse_far_apart", arr, "adversarial", "Singletons far apart")

    tight = [0] * n
    pos = 1000
    for _ in range(MAX_BLOCKS):
        tight[pos] = random_value(rng)
        pos += 2
    validate_array(tight)
    add_test(tests, "adv_blocks_tightly_packed", tight, "adversarial", "Blocks separated by one zero")

    for idx in range(10):
        blocks = MAX_BLOCKS
        block_lengths = [1] * blocks
        for _ in range(500):
            block_lengths[rng.randrange(blocks)] += 1

        arr = place_blocks(n, block_lengths, rng, value_mode="alternating_big")
        add_test(
            tests,
            f"adv_alt_big_{idx:03d}",
            arr,
            "adversarial",
            "Many blocks with alternating huge/small values",
            "alternating_big",
        )

    for idx in range(12):
        blocks = rng.randint(30, MAX_BLOCKS)
        block_lengths = [1] * blocks
        total = rng.randint(1200, max_nonzero)
        remaining = total - blocks
        for _ in range(remaining):
            block_lengths[rng.randrange(blocks)] += 1

        arr = place_blocks(n, block_lengths, rng, value_mode="powers")
        add_test(
            tests,
            f"adv_powers_{idx:03d}",
            arr,
            "adversarial",
            "Many blocks with power-of-two values",
            "powers",
        )

    return tests


def generate_all_tests(seed: int) -> List[TestSpec]:
    rng = random.Random(seed)

    tests: List[TestSpec] = []
    tests.extend(make_manual_tests())
    tests.extend(make_small_random_tests(rng))
    tests.extend(make_large_generated_tests(rng))
    tests.extend(make_adversarial_tests(rng))

    seen = set()
    for spec in tests:
        if spec.name in seen:
            raise ValueError(f"Duplicate test name: {spec.name}")
        seen.add(spec.name)
        validate_array(spec.array)

    return tests


def print_summary(tests: Sequence[TestSpec]) -> None:
    total_n = sum(len(t.array) for t in tests)
    total_nonzero = sum(sum(1 for x in t.array if x != 0) for t in tests)

    print(f"Generated tests: {len(tests)}")
    print(f"Total elements across all tests: {total_n}")
    print(f"Total nonzero elements across all tests: {total_nonzero}")

    by_group = {}
    for test in tests:
        group = test.meta.get("group", "unknown")
        by_group[group] = by_group.get(group, 0) + 1

    for group, count in sorted(by_group.items()):
        print(f"  {group}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test generator for the WarehouseAPI optimization problem"
    )
    parser.add_argument(
        "out_dir",
        type=str,
        help="Directory where generated tests will be stored",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260314,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing .json/.ans files before generation",
    )

    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.clean:
        for path in out_dir.iterdir():
            if path.is_file() and path.suffix.lower() in {".json", ".ans"}:
                path.unlink()

    tests = generate_all_tests(args.seed)

    for spec in tests:
        save_test(spec, out_dir)

    print_summary(tests)


if __name__ == "__main__":
    main()
