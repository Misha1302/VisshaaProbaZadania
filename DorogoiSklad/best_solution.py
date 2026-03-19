def solve(api):
    n = api.size()
    if n == 0:
        return 0

    def find_first_nonzero(left, right):
        """
        Preconditions:
            left <= right
            there exists at least one nonzero element in [left, right]
        Returns:
            the first index pos in [left, right] such that A[pos] != 0
        """
        while left < right:
            mid = (left + right) // 2
            if api.has_nonzero(left, mid):
                right = mid
            else:
                left = mid + 1
        return left

    answer = 0
    current = 0

    while current < n:
        if not api.has_nonzero(current, n - 1):
            break

        start = find_first_nonzero(current, n - 1)

        pos = start
        while pos < n:
            value = api.get(pos)
            if value == 0:
                current = pos + 1
                break

            answer += value
            pos += 1
        else:
            current = n

    return answer
