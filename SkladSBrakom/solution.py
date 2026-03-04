def solve(api):
    n = api.size()
    if n == 0:
        return 0

    # Считаем число нулей в A[l..r] (включительно).
    # Ключевой факт: все "хорошие" значения строго положительные,
    # поэтому sum_range(l,r) == 0  <=>  весь диапазон состоит из нулей.
    def count_zeros(l, r):
        if l == r:
            return 1 if api.get_item(l) == 0 else 0

        s = api.sum_range(l, r)  # 30 попугаев
        if s == 0:
            return r - l + 1      # весь диапазон — нули
        if l == r:
            return 0              # s>0 и один элемент => он положительный

        m = (l + r) // 2
        return count_zeros(l, m) + count_zeros(m + 1, r)

    return count_zeros(0, n - 1)
