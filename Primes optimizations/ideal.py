from math import *
from random import *

def binpow(a, p, m):
    if p == 0: return 1
    if p % 2 == 1: return (a * binpow(a, p - 1, m)) % m
    v = binpow(a, p // 2, m)
    return (v * v) % m

def is_prime(n):
    if n <= 5:
       if n <= 1: return False
       if n == 2: return True
       if n == 3: return True
       if n == 4: return False
       if n == 5: return True
    for x in range(0, 30):
        if binpow(randint(2, n - 1), n - 1, n) != 1:
            return False
    return True

def solve(api: WarehouseAPI):
    n = api.size()
    arr = api.batch_get([x for x in range(0, n)])
    total = 0
    for i in range(n):
        x = arr[i]
        total += x if is_prime(x) else 0
    return total
