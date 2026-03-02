#!/usr/bin/env python3
"""
Минимальное решение задачи "Агрегатор продаж по филиалам".

Запуск:
  python solution_minimal.py --root PATH_TO_ROOT --k 10 --out OUT_DIR

Что делает:
 - Явный DFS (стек) по папкам, ищет файлы sales.db, items.csv, branch_meta.json, config.yaml
 - Читает products и transactions из SQLite (sales.db)
 - Читает items.csv
 - Строит агрегат продаж по product_id
 - Собирает inconsistencies (missing_in_db, price mismatch, transaction_for_missing_product (один объект на tx_id))
 - Пишет product_summary.csv и inconsistencies.json и manifest.json
 - Печатает TOP-K по выручке
"""
import os, csv, json, sqlite3, argparse

# --- Вспомогательные функции (простые, надёжные) ---

def dfs_find(root):
    """Явный DFS по дереву: возвращает список записей {folder:..., 'sales.db':path, ...} и manifest list."""
    stack = [os.path.abspath(root)]
    found = []
    manifest = []
    while stack:
        cur = stack.pop()
        try:
            names = sorted(os.listdir(cur), reverse=True)  # deterministic-ish
        except Exception:
            continue
        # добавляем папки в стек (DFS)
        for n in names:
            p = os.path.join(cur, n)
            if os.path.isdir(p):
                stack.append(p)
        # проверяем нужные файлы в текущей папке
        rec = {"folder": os.path.abspath(cur)}
        anyfile = False
        for fname in ("sales.db", "items.csv", "branch_meta.json", "config.yaml"):
            p = os.path.join(cur, fname)
            if os.path.exists(p):
                rec[fname] = p
                manifest.append(p)
                anyfile = True
        if anyfile:
            found.append(rec)
    manifest.append(os.path.abspath(root))
    return found, manifest

def read_items_csv(path):
    """Читает items.csv -> dict pid -> (name, price_or_none)"""
    out = {}
    try:
        with open(path, encoding='utf-8', newline='') as f:
            r = csv.DictReader(f)
            for row in r:
                pid = row.get("product_id")
                if not pid:
                    continue
                name = row.get("name") or ""
                price = None
                try:
                    up = row.get("unit_price")
                    if up not in (None, ""):
                        price = float(up)
                except Exception:
                    price = None
                out[str(pid)] = (name, price)
    except Exception:
        pass
    return out

def read_db(path):
    """Читает sales.db -> products dict и transactions list.
    products: pid -> (name, price_or_none)
    transactions: list of (tx_id:int, pid:str, qty:int, price:float, ts:str)
    """
    products = {}
    transactions = []
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        try:
            cur.execute("SELECT product_id, name, unit_price FROM products")
            for pid, name, price in cur.fetchall():
                products[str(pid)] = (name or "", float(price) if price is not None else None)
        except Exception:
            pass
        try:
            cur.execute("SELECT tx_id, product_id, quantity, unit_price_at_sale, timestamp FROM transactions")
            for tx_id, pid, qty, price, ts in cur.fetchall():
                transactions.append((int(tx_id), str(pid), int(qty), float(price) if price is not None else 0.0, ts))
        except Exception:
            pass
        conn.close()
    except Exception:
        pass
    return products, transactions

def read_branch_id(path):
    """Простой читатель branch_meta.json: возвращает branch_id или None."""
    try:
        with open(path, encoding='utf-8') as f:
            j = json.load(f)
            return j.get("branch_id") or j.get("id")
    except Exception:
        return None

# --- Основная логика ---

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    found, manifest = dfs_find(args.root)

    # agg: product_id -> {"qty":int, "rev":float, "last":str_or_None, "branches": set()}
    agg = {}
    # имя продукта (предпочитаем имя из DB, если есть; иначе из CSV)
    name_by_pid = {}
    inconsistencies = []

    for rec in found:
        folder = rec["folder"]
        branch_id = None
        if "branch_meta.json" in rec:
            branch_id = read_branch_id(rec["branch_meta.json"])
        if not branch_id:
            branch_id = os.path.basename(folder)

        products, transactions = ({}, [])
        if "sales.db" in rec:
            products, transactions = read_db(rec["sales.db"])
            for pid, (n, _) in products.items():
                if pid not in name_by_pid and n:
                    name_by_pid[pid] = n

        items = {}
        if "items.csv" in rec:
            items = read_items_csv(rec["items.csv"])
            for pid, (n, _) in items.items():
                if pid not in name_by_pid and n:
                    name_by_pid[pid] = n

        issues = []

        # 1) compare CSV vs DB
        for pid, (_, csv_price) in items.items():
            if pid not in products:
                issues.append({"product_id": pid, "missing_in_db": True})
            else:
                db_price = products[pid][1]
                if db_price is not None and csv_price is not None and abs(db_price - csv_price) > 1e-6:
                    issues.append({"product_id": pid, "price_in_db": db_price, "price_in_csv": csv_price})

        # 2) process transactions (aggregate + check tx for missing product)
        for tx_id, pid, qty, price, ts in transactions:
            recagg = agg.setdefault(pid, {"qty": 0, "rev": 0.0, "last": None, "branches": set()})
            recagg["qty"] += qty
            recagg["rev"] += qty * price
            recagg["branches"].add(branch_id)
            if ts and (recagg["last"] is None or ts > recagg["last"]):
                recagg["last"] = ts
            if pid not in products:
                # ВАЖНО: одно issue на каждую транзакцию (ключ tx_id), так требует тест-генератор
                issues.append({"product_id": pid, "transaction_for_missing_product": True, "tx_id": tx_id})

        if issues:
            inconsistencies.append({"folder": folder, "branch_id": branch_id, "issues": issues})

    # Записываем product_summary.csv (только продукты с транзакциями)
    out_csv = os.path.join(args.out, "product_summary.csv")
    with open(out_csv, "w", encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(["product_id","product_name","total_quantity_sold","total_revenue","last_sale_timestamp","num_branches_sold"])
        for pid in sorted(agg.keys()):
            v = agg[pid]
            name = name_by_pid.get(pid, "<UNKNOWN>")
            qty = v["qty"]
            rev = round(v["rev"] + 1e-9, 2)  # округление, чтобы совпасть с эталоном
            last = v["last"] or "null"
            branches = len(v["branches"])
            w.writerow([pid, name, qty, f"{rev:.2f}", last, branches])

    # Записываем inconsistencies.json
    out_inc = os.path.join(args.out, "inconsistencies.json")
    with open(out_inc, "w", encoding='utf-8') as f:
        json.dump(inconsistencies, f, ensure_ascii=False, indent=2)

    # manifest.json (перечисление файлов, найденных в dfs_find)
    with open(os.path.join(args.out, "manifest.json"), "w", encoding='utf-8') as f:
        json.dump({"files": manifest}, f, ensure_ascii=False, indent=2)

    # TOP-K by revenue печать в stdout
    ranked = sorted(agg.items(), key=lambda kv: (-round(kv[1]["rev"], 2), kv[0]))
    print("TOP K BY REVENUE:")
    for i, (pid, v) in enumerate(ranked[:args.k], start=1):
        print(f"{i}. {pid} | {name_by_pid.get(pid,'<UNKNOWN>')} | {v['rev']:.2f} | {v['qty']}")

if __name__ == "__main__":
    main()
