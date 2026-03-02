#!/usr/bin/env python3
"""
generate_tests.py
Генератор тестовой директории для задачи "Агрегатор продаж по филиалам".

Создаёт:
 - вложенную структуру папок (регион/город/branch_xxx)
 - в каждой ветке (с вероятностью) sqlite файл sales.db с таблицами products и transactions
 - items.csv (локальный каталог) — иногда с расхождениями
 - branch_meta.json, config.yaml
 - expected/ — эталонные product_summary.csv и inconsistencies.json и topk.txt
 - manifest.json (перечисление всех файлов)

Не требует внешних библиотек.
"""
import os
import csv
import json
import random
import sqlite3
from datetime import datetime, timedelta
import argparse
from pathlib import Path

def ensure_dir(p):
    os.makedirs(p, exist_ok=True)

def write_yaml_simple(path, mapping):
    # Простой writer — не требует PyYAML
    lines = []
    for k, v in mapping.items():
        if isinstance(v, str):
            lines.append(f"{k}: {v}")
        else:
            lines.append(f"{k}: {json.dumps(v)}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def create_sqlite_db(path, products, transactions):
    """
    products: list of (product_id, name, unit_price)
    transactions: list of (tx_id, product_id, quantity, unit_price_at_sale, timestamp_iso)
    """
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE products(
        product_id TEXT PRIMARY KEY,
        name TEXT,
        unit_price REAL
    )
    """)
    cur.execute("""
    CREATE TABLE transactions(
        tx_id INTEGER PRIMARY KEY,
        product_id TEXT,
        quantity INTEGER,
        unit_price_at_sale REAL,
        timestamp TEXT
    )
    """)
    cur.executemany("INSERT INTO products(product_id,name,unit_price) VALUES (?,?,?)", products)
    cur.executemany("INSERT INTO transactions(tx_id,product_id,quantity,unit_price_at_sale,timestamp) VALUES (?,?,?,?,?)", transactions)
    conn.commit()
    conn.close()

def generate_testset(root, branches=10, products_total=50, seed=0):
    random.seed(seed)
    ensure_dir(root)
    regions = ["North", "South", "East", "West"]
    # Generate global product catalog (IDs P001..)
    global_products = []
    for i in range(1, products_total+1):
        pid = f"P{str(i).zfill(3)}"
        name = f"Product_{i}"
        base_price = round(random.uniform(5.0, 200.0), 2)
        global_products.append((pid, name, base_price))
    # We'll assign random subset of products to branches and generate transactions
    manifest = []
    expected_transactions = []  # (branch_id, tx_id, product_id, quantity, unit_price_at_sale, timestamp)
    expected_products_info = {}  # map product_id -> name preference
    branch_list = []
    tx_global_id = 1
    for b in range(1, branches+1):
        region = random.choice(regions)
        city = f"city_{random.randint(1,10)}"
        branch_id = f"branch_{str(b).zfill(3)}"
        # make nested path: root/region/city/branch_id
        branch_path = os.path.join(root, region, city, branch_id)
        ensure_dir(branch_path)
        branch_list.append((branch_id, branch_path))
        # write branch_meta.json
        meta = {"branch_id": branch_id, "region": region, "manager": f"mgr_{b}"}
        meta_path = os.path.join(branch_path, "branch_meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        manifest.append(meta_path)
        # write config.yaml (simple)
        cfg = {"currency": "EUR", "timezone": "UTC", "branch_code": branch_id}
        cfg_path = os.path.join(branch_path, "config.yaml")
        write_yaml_simple(cfg_path, cfg)
        manifest.append(cfg_path)
        # Choose subset of products for this branch catalog:
        num_products_branch = random.randint(max(5, products_total//10), max(10, products_total//3))
        prods_in_branch = random.sample(global_products, k=num_products_branch)
        # Create slight price variances per branch
        products_for_db = []
        items_csv_rows = []
        for pid, name, base_price in prods_in_branch:
            # price in DB
            db_price = round(base_price * random.uniform(0.9, 1.15), 2)
            products_for_db.append((pid, name, db_price))
            # CSV price: sometimes same, sometimes different, sometimes missing (to create inconsistencies)
            if random.random() < 0.85:  # 85% include in CSV
                # with small chance write different price
                if random.random() < 0.15:
                    csv_price = round(db_price * random.uniform(0.8, 1.2), 2)
                else:
                    csv_price = db_price
                items_csv_rows.append((pid, name, csv_price))
        # Possibly add some csv-only items (missing in db)
        if random.random() < 0.25:
            extras = random.randint(1,3)
            for _ in range(extras):
                i = random.randint(1, products_total)
                pid = f"P{str(i).zfill(3)}"
                name = f"Product_{i}_csvonly"
                csv_price = round(random.uniform(1.0, 250.0), 2)
                items_csv_rows.append((pid, name, csv_price))
        # Write items.csv (if any)
        if items_csv_rows:
            csv_path = os.path.join(branch_path, "items.csv")
            with open(csv_path, "w", newline='', encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["product_id","name","unit_price"])
                for r in items_csv_rows:
                    w.writerow(r)
            manifest.append(csv_path)
        # Create sales.db (with some probability; sometimes branches have no DB)
        if random.random() < 0.95:
            # generate transactions: per branch, random number of transactions
            tx_count = random.randint(5, 40)
            transactions = []
            for _ in range(tx_count):
                prod = random.choice(products_for_db + [random.choice(global_products) if random.random() < 0.05 else None])
                if prod is None:
                    continue
                pid = prod[0]
                # choose unit_price_at_sale near branch db price or base price
                unit_price = round((prod[2] if len(prod)==3 else prod[2]) * random.uniform(0.85, 1.15), 2)
                qty = random.randint(1, 10)
                ts = (datetime.utcnow() - timedelta(days=random.randint(0, 365), seconds=random.randint(0,86400))).isoformat(timespec='seconds') + "Z"
                transactions.append((tx_global_id, pid, qty, unit_price, ts))
                expected_transactions.append((branch_id, tx_global_id, pid, qty, unit_price, ts))
                tx_global_id += 1
            # Occasionally add transactions for product not present in products table to introduce inconsistency
            if random.random() < 0.12:
                pid = f"P{str(random.randint(products_total+1, products_total+5)).zfill(3)}"  # likely missing
                unit_price = round(random.uniform(1.0, 100.0), 2)
                qty = random.randint(1,5)
                ts = datetime.utcnow().isoformat(timespec='seconds') + "Z"
                transactions.append((tx_global_id, pid, qty, unit_price, ts))
                expected_transactions.append((branch_id, tx_global_id, pid, qty, unit_price, ts))
                tx_global_id += 1
            # write sqlite db
            db_path = os.path.join(branch_path, "sales.db")
            create_sqlite_db(db_path, products_for_db, transactions)
            manifest.append(db_path)
    # Build expected aggregated results from expected_transactions
    agg = {}
    branches_per_product = {}
    for (branch_id, tx_id, pid, qty, unit_price, ts) in expected_transactions:
        if pid not in agg:
            agg[pid] = {"total_quantity_sold":0, "total_revenue":0.0, "last_sale_timestamp":None}
        agg[pid]["total_quantity_sold"] += qty
        agg[pid]["total_revenue"] += qty * unit_price
        if (agg[pid]["last_sale_timestamp"] is None) or (ts > agg[pid]["last_sale_timestamp"]):
            agg[pid]["last_sale_timestamp"] = ts
        branches_per_product.setdefault(pid, set()).add(branch_id)
    # Product names preferences: if appears in any branch products_for_db use that name, else UNKNOWN
    product_names = {}
    # scan manifest databases to get product names
    for f in manifest:
        if f.endswith("sales.db"):
            try:
                conn = sqlite3.connect(f)
                cur = conn.cursor()
                cur.execute("SELECT product_id,name FROM products")
                for pid, name in cur.fetchall():
                    if pid not in product_names:
                        product_names[pid] = name
                conn.close()
            except Exception as e:
                pass
    # fallback to global_products
    for pid, name, price in global_products:
        if pid not in product_names:
            product_names[pid] = name
    # Compose expected product_summary.csv
    expected_dir = os.path.join(root, "expected")
    ensure_dir(expected_dir)
    summary_path = os.path.join(expected_dir, "product_summary.csv")
    with open(summary_path, "w", newline='', encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["product_id","product_name","total_quantity_sold","total_revenue","last_sale_timestamp","num_branches_sold"])
        for pid in sorted(agg.keys()):
            v = agg[pid]
            qty = v["total_quantity_sold"]
            rev = round(v["total_revenue"] + 1e-9, 2)
            last_ts = v["last_sale_timestamp"]
            num_br = len(branches_per_product.get(pid, set()))
            name = product_names.get(pid, "<UNKNOWN>")
            w.writerow([pid, name, qty, f"{rev:.2f}", last_ts, num_br])
    # Build expected inconsistencies.json by checking CSV vs DB per branch
    inconsistencies = []
    # walk branches again to inspect local files
    for branch_id, branch_path in branch_list:
        entry = {"folder": os.path.abspath(branch_path), "branch_id": branch_id, "issues": []}
        db_path = os.path.join(branch_path, "sales.db")
        csv_path = os.path.join(branch_path, "items.csv")
        products_in_db = {}
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                cur.execute("SELECT product_id,name,unit_price FROM products")
                for pid, name, price in cur.fetchall():
                    products_in_db[pid] = {"name": name, "price": price}
                # get transactions referencing missing product
                cur.execute("SELECT tx_id,product_id FROM transactions")
                for tx_id, pid in cur.fetchall():
                    if pid not in products_in_db:
                        entry["issues"].append({"product_id": pid, "transaction_for_missing_product": True, "tx_id": tx_id})
                conn.close()
            except Exception as e:
                pass
        if os.path.exists(csv_path):
            with open(csv_path, "r", encoding="utf-8") as f:
                rdr = csv.DictReader(f)
                for row in rdr:
                    pid = row["product_id"]
                    try:
                        csv_price = float(row["unit_price"])
                    except:
                        csv_price = None
                    if pid not in products_in_db:
                        entry["issues"].append({"product_id": pid, "missing_in_db": True})
                    else:
                        db_price = products_in_db[pid]["price"]
                        if csv_price is not None and abs(db_price - csv_price) > 1e-6:
                            entry["issues"].append({"product_id": pid, "price_in_db": db_price, "price_in_csv": csv_price})
        if entry["issues"]:
            inconsistencies.append(entry)
    # Save expected inconsistencies
    inconsist_path = os.path.join(expected_dir, "inconsistencies.json")
    with open(inconsist_path, "w", encoding="utf-8") as f:
        json.dump(inconsistencies, f, ensure_ascii=False, indent=2)
    # Top-K by revenue
    k = min(10, len(agg))
    ranked = sorted(agg.items(), key=lambda kv: (-round(kv[1]["total_revenue"],2), kv[0]))
    topk_path = os.path.join(expected_dir, "topk.txt")
    with open(topk_path, "w", encoding="utf-8") as f:
        f.write("TOP K BY REVENUE (expected):\n")
        for i, (pid, v) in enumerate(ranked[:k], start=1):
            name = product_names.get(pid, "<UNKNOWN>")
            rev = round(v["total_revenue"] + 1e-9, 2)
            f.write(f"{i}. {pid} | {name} | {rev:.2f} | qty={v['total_quantity_sold']}\n")
    manifest_path = os.path.join(root, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"files": manifest}, f, ensure_ascii=False, indent=2)
    print(f"Generated testset at {os.path.abspath(root)}")
    print(f"Expected outputs in {os.path.abspath(expected_dir)}")
    return

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate test data for aggregator task")
    parser.add_argument("--root", default="./tests/sales_root", help="Root folder for tests")
    parser.add_argument("--branches", type=int, default=10, help="Number of branches to generate")
    parser.add_argument("--products", type=int, default=50, help="Global number of products")
    parser.add_argument("--seed", type=int, default=0, help="Random seed")
    parser.add_argument("--k", type=int, default=10, help="Top-K (for expected topk file)")
    args = parser.parse_args()
    generate_testset(args.root, branches=args.branches, products_total=args.products, seed=args.seed)
