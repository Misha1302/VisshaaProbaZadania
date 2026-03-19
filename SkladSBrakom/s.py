def solve(api: WarehouseAPI) -> int:
    n = api.size()
    total = 0

    for i in range(n):
        total += api.get(i)

    return total
