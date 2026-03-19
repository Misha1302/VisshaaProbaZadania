import math
import random


def binpow(a: int, n: int, m: int):
    if not n:
        return 1
    if n % 2 != 0:
        return binpow(a, n - 1, m) * a % m
    ans = binpow(a, n // 2, m)
    return ans * ans % m


def f(n: int):
    if n <= 5:
       if n <= 1: return False
       if n == 2: return True
       if n == 3: return True
       if n == 4: return False
       if n == 5: return True
    for _ in range(30):
        if binpow(random.randint(2, n), n - 1, n) == 1:
            continue
        else:
            return False
    return True


def solve(api: WarehouseAPI):
    n = api.size()
    total = 0
    m = api.batch_get([i for i in range(n)])
    for i in range(n):
        if f(m[i]):
            total += m[i]
    return total
