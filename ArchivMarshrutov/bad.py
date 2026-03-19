def solve(api: GraphAPI):
	n = api.size()
	dp = [0] * n
	for v in range(n):
		best = 0
		for u in range(v):
			if api.has_edge(u, v):
				cand = dp[u] + 1
				if cand > best:
					best = cand
		dp[v] = best
	ans = 0
	for v in range(n):
		if dp[v] > ans:
			ans = dp[v]
	return ans
