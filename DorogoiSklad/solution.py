def bin(l: int, r: int, api) -> int:
    ans = 0
    while l <= r:
        m = (l + r) // 2
        if not api.has_nonzero(l, m):
            l = m + 1
            ans = m
        else:
            r = m - 1
    return ans


def solve(api):
    n = api.size()
    ans = 0
    i = 0
    while i < n:
        f = api.get(i)
        if not f:
            i = bin(i, n - 1, api) + 1
        else:
            ans += f
            i += 1
    return ans

# 1 2 2 3 0 0 0 0 0 0 0 0 0 0 0 0 0 0 7 9 1 
# get = 30
# has_nonzero = 10
