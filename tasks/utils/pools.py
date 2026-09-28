"""
Run-level balanced trial pools.

Rationale
---------
Balancing inside a single small block is often impossible:
a 4-trial block cannot contain 3 ink colours in equal numbers.

The solution is to build ONE balanced pool per condition for the whole
run, then deal the items out to the blocks. Balance then holds at the
run level, which is what matters for the GLM, and the residual
deviation is at most 1 item per category.
"""

from __future__ import annotations

import random
from collections import Counter


def balanced_pool(categories: list, n_total: int,
                  rng: random.Random) -> list:
    """
    Return n_total items drawn from *categories* as evenly as possible.

    With 3 categories and n_total=32 the result is 11/11/10, and which
    category receives the extra item is randomised.

    The final list is shuffled.
    """
    if not categories or n_total <= 0:
        return []

    k = len(categories)
    base, remainder = divmod(n_total, k)

    order = list(categories)
    rng.shuffle(order)                 # randomise who gets the extras

    pool: list = []
    for i, cat in enumerate(order):
        pool.extend([cat] * (base + (1 if i < remainder else 0)))

    rng.shuffle(pool)
    return pool


def deal_to_blocks(pool: list, block_sizes: list[int]) -> list[list]:
    """
    Split a pool into consecutive chunks of the given sizes.

    Raises if the pool is too small, so a design error is caught
    before the scanner starts rather than mid-run.
    """
    if sum(block_sizes) != len(pool):
        raise ValueError(
            f"Pool size {len(pool)} does not match the requested "
            f"{sum(block_sizes)} trials."
        )
    out, i = [], 0
    for size in block_sizes:
        out.append(pool[i:i + size])
        i += size
    return out


def max_run_length(seq: list) -> int:
    """Length of the longest run of identical consecutive values."""
    if not seq:
        return 0
    best = run = 1
    for a, b in zip(seq, seq[1:]):
        run = run + 1 if a == b else 1
        best = max(best, run)
    return best


def counts(seq: list) -> dict:
    """Occurrence count per distinct value, sorted by key."""
    return dict(sorted(Counter(seq).items(), key=lambda kv: str(kv[0])))


def enforce_max_run(items: list, key, max_run: int = 2,
                    rng: random.Random | None = None,
                    protect=None, max_attempts: int = 4000) -> list:
    """
    Reorder *items* so that no value of key() repeats more than max_run
    times in a row.

    Args:
        key:     callable extracting the value to constrain
        protect: optional callable; swaps are only allowed between items
                 with the same protect() value. Use it to preserve an
                 existing constraint (e.g. trial-type alternation).

    The list is modified by targeted swaps, so category counts are
    never altered. Returns the same list object.
    """
    rng = rng or random.Random()
    n = len(items)
    if n <= max_run:
        return items

    for _ in range(max_attempts):
        bad = -1
        for i in range(max_run, n):
            window = [key(items[j]) for j in range(i - max_run, i + 1)]
            if len(set(window)) == 1:
                bad = i
                break
        if bad < 0:
            return items                     # constraint satisfied

        cands = [
            j for j in range(n)
            if key(items[j]) != key(items[bad])
            and (protect is None or protect(items[j]) == protect(items[bad]))
        ]
        if not cands:
            return items                     # impossible, give up cleanly
        j = rng.choice(cands)
        items[bad], items[j] = items[j], items[bad]

    return items


def interleave_no_repeat(items: list, key,
                         rng: random.Random | None = None) -> list:
    """
    Reorder so that no two consecutive items share the same key().

    Greedy: always take from the largest remaining pool that differs
    from the previous key. Always succeeds when no category holds more
    than ceil(n/2) items, which is the case for balanced designs.
    """
    rng = rng or random.Random()
    pools: dict = {}
    for it in items:
        pools.setdefault(key(it), []).append(it)
    for p in pools.values():
        rng.shuffle(p)

    out, last = [], None
    for _ in range(len(items)):
        avail = [k for k, v in pools.items() if v and k != last]
        if not avail:
            avail = [k for k, v in pools.items() if v]
            if not avail:
                break
        chosen = max(avail, key=lambda k: len(pools[k]))
        out.append(pools[chosen].pop())
        last = chosen
    return out