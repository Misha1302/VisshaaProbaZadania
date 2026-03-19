def solve(api):
    n = api.size()
    dp = [0] * n

    for u in range(n):
        for v in api.out_neighbors(u):
            cand = dp[u] + 1
            if cand > dp[v]:
                dp[v] = cand

    ans = 0
    for x in dp:
        if x > ans:
            ans = x

    return ans
