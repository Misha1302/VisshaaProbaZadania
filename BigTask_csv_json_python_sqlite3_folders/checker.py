#!/usr/bin/env python3
"""
checker.py
Простой чекер для сравнения expected vs out.

Использование:
  python checker.py --expected EXPECTED_DIR --out OUT_DIR

Проверяет:
 - expected/product_summary.csv == out/product_summary.csv (числа с допуском 0.01)
 - expected/inconsistencies.json == out/inconsistencies.json (игнорирует порядок записей и порядок issues)
Выходной код 0 при успехе, 1 при ошибке.
"""
import os, sys, csv, json, argparse
from math import isclose

def load_csv_map(path):
    m = {}
    with open(path, encoding='utf-8') as f:
        r = csv.DictReader(f)
        for row in r:
            pid = row["product_id"]
            m[pid] = row
    return m

def normalize_inconsist(arr):
    # produce mapping (folder, branch_id) -> sorted list of issues (as tuples) for easy compare
    out = {}
    for e in arr:
        folder = e.get("folder")
        bid = e.get("branch_id")
        key = (folder, bid)
        iss = []
        for it in e.get("issues", []):
            # convert to tuple of sorted (k,v) for deterministic compare; lists sorted
            items = tuple(sorted(((k, tuple(v) if isinstance(v, list) else v) for k,v in it.items())))
            iss.append(items)
        iss_sorted = sorted(iss)
        out[key] = iss_sorted
    return out

def cmp_summaries(exp_path, out_path):
    exp = load_csv_map(exp_path)
    out = load_csv_map(out_path)
    ok = True
    # keys must match
    exp_keys = set(exp.keys())
    out_keys = set(out.keys())
    if exp_keys != out_keys:
        print("MISMATCH product ids between expected and out")
        print("only in expected:", sorted(exp_keys - out_keys)[:10])
        print("only in out:", sorted(out_keys - exp_keys)[:10])
        ok = False
    # compare values for common ids
    for pid in sorted(exp_keys & out_keys):
        er = exp[pid]
        orr = out[pid]
        # quantity exact integer
        try:
            eq = int(er["total_quantity_sold"])
            oq = int(orr["total_quantity_sold"])
            if eq != oq:
                print(f"qty mismatch {pid}: expected {eq} got {oq}")
                ok = False
        except Exception:
            print(f"qty parse error for {pid}")
            ok = False
        # revenue tolerant to 0.01
        try:
            ev = float(er["total_revenue"])
            ov = float(orr["total_revenue"])
            if not isclose(ev, ov, abs_tol=0.01):
                print(f"revenue mismatch {pid}: expected {ev} got {ov}")
                ok = False
        except Exception:
            print(f"revenue parse error for {pid}")
            ok = False
        # last_sale_timestamp compare as strings (allow both empty/"null")
        e_ts = er.get("last_sale_timestamp","")
        o_ts = orr.get("last_sale_timestamp","")
        if (e_ts in ("","null",None)) and (o_ts in ("","null",None)):
            pass
        else:
            if e_ts != o_ts:
                print(f"timestamp mismatch {pid}: expected '{e_ts}' got '{o_ts}'")
                ok = False
    return ok

def cmp_inconsist(exp_path, out_path):
    try:
        with open(exp_path, encoding='utf-8') as f:
            exp = json.load(f)
    except Exception:
        exp = []
    try:
        with open(out_path, encoding='utf-8') as f:
            out = json.load(f)
    except Exception:
        out = []
    ne = normalize_inconsist(exp)
    no = normalize_inconsist(out)
    if set(ne.keys()) != set(no.keys()):
        print("Inconsistencies keys (folder,branch_id) mismatch")
        print("only in expected:", set(ne.keys()) - set(no.keys()))
        print("only in out:", set(no.keys()) - set(ne.keys()))
        return False
    ok = True
    for k in ne:
        if ne[k] != no[k]:
            print("Mismatch in issues for", k)
            print("expected:", ne[k])
            print("got     :", no[k])
            ok = False
    return ok

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--expected", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    exp = args.expected
    out = args.out
    ok = True
    exp_sum = os.path.join(exp, "product_summary.csv")
    out_sum = os.path.join(out, "product_summary.csv")
    if not os.path.exists(exp_sum) or not os.path.exists(out_sum):
        print("Missing product_summary.csv in expected or out")
        sys.exit(1)
    if not cmp_summaries(exp_sum, out_sum):
        ok = False
    exp_inc = os.path.join(exp, "inconsistencies.json")
    out_inc = os.path.join(out, "inconsistencies.json")
    if not os.path.exists(exp_inc) or not os.path.exists(out_inc):
        print("Missing inconsistencies.json in expected or out")
        ok = False
    else:
        if not cmp_inconsist(exp_inc, out_inc):
            ok = False
    if ok:
        print("OK: outputs match expected (within tolerances)")
        sys.exit(0)
    else:
        print("FAIL: outputs differ")
        sys.exit(1)

if __name__ == "__main__":
    main()
