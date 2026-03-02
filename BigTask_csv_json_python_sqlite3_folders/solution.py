import argparse
import csv
import json
import os
import sqlite3

import yaml

parser = argparse.ArgumentParser()
parser.add_argument('--k')
parser.add_argument('--root')
parser.add_argument('--out')
args = parser.parse_args()
k = int(args.k or 5)
root = args.root or "/home/micodiy/razakov/python/VisshaaProbaZabania/BigTask_csv_json_python_sqlite3_folders/tests/sales_root"
out = args.out or "/home/micodiy/razakov/python/VisshaaProbaZabania/BigTask_csv_json_python_sqlite3_folders/OUTDIR"

id_to_name = {}
received = {}
sold = {}

bad_values = []


def handle_database(file_path):
    conn = sqlite3.connect(file_path)
    cur = conn.cursor()
    transactions = cur.execute('select * from transactions').fetchall()
    products = cur.execute('select * from products').fetchall()

    for x in products:
        id = x[0]
        name = x[1]

        if id not in id_to_name:
            id_to_name[id] = name
        elif name != id_to_name[id]:
            bad_values.append((id, name))

    for x in transactions:
        if x[1] not in received: received[x[1]] = 0
        if x[1] not in sold: sold[x[1]] = 0

        received[x[1]] += int(x[3]) * int(x[2])
        sold[x[1]] += int(x[2])


def handle_meta(file_path):
    with open(file_path) as fp:
        obj = json.load(fp)
        name = obj['branch_id']
        if name != file_path.split('/')[-2]:
            bad_values.append(name)


def handle_yaml(file_path):
    with open(file_path) as fp:
        obj = yaml.load(fp, Loader=yaml.FullLoader)
        name = obj['branch_code']
        if name != file_path.split('/')[-2]:
            bad_values.append(name)


def handle_csv(file_path):
    with open(file_path) as fp:
        obj = csv.DictReader(fp)
        for d in obj:
            if 'name' not in d or 'product_id' not in d:
                continue

            id = d['product_id']
            name = d['name']
            if id not in id_to_name:
                id_to_name[id] = name
            elif name != id_to_name[id]:
                bad_values.append((id, name))


def handle_file(file_path):
    assert os.path.isfile(file_path)
    assert os.path.exists(file_path)

    if file_path.endswith(".db"):
        handle_database(file_path)
    elif file_path.endswith(".json") and "meta" in file_path:
        handle_meta(file_path)
    elif file_path.endswith(".yaml"):
        handle_yaml(file_path)
    elif file_path.endswith(".csv"):
        handle_csv(file_path)


def dfs(p):
    if os.path.isfile(p):
        handle_file(p)
        return

    names = os.listdir(p)
    for x in names:
        dfs(p + "/" + x)


def printk():
    print("K BEST:")
    res = []
    for id in received:
        res.append([id, id_to_name[id] if id in id_to_name else "UNKNOWN", received[id], sold[id]])

    res = sorted(res, key=lambda x: (x[2], x[0]), reverse=True)

    for i in range(min(k, len(res))):
        x = res[i]
        print(f'{i + 1}. {x[0]} | {x[1]} | {x[2]} | {x[3]}')


def print_bad():
    global bad_values

    print("BAD VALUES:")
    bad_values = list(set(bad_values))
    for name in bad_values:
        print(name)


dfs(root)
printk()
print_bad()
