from abc import ABC, abstractmethod
from typing import Iterator, List, Tuple, TypeVar


def weight_to_diff(w: float) -> int:
    return int(2**w)


def diff_to_weight(d: int) -> float:
    import math
    return math.log(d, 2)


T = TypeVar('T')


def take(iterator: Iterator[T], n: int) -> List[T]:
    """Take first n elements from iterator, can return less if there aren't enough elements."""
    count = 0
    res = []
    for i in iterator:
        res.append(i)
        count += 1
        if count >= n:
            break
    return res



class DAA(ABC):
    @abstractmethod
    def next_weight(self, blocks: Iterator[Tuple[int, float]]) -> float:
        """Determines the next weight based on the list of block timestamps and their respective weights."""
        raise NotImplementedError


class HTR(DAA):
    T = 30
    N = 20
    MIN_WEIGHT = 21.0
    MAX_DW = 0.25

    def _get_timestamps_and_weights(self, blocks: Iterator[Tuple[int, float]]) -> List[Tuple[int, float]]:
        return take(blocks, self.N)[::-1]

    def next_weight(self, blocks: Iterator[Tuple[int, float]]) -> float:
        import math
        from hathor.transaction import sum_weights

        timestamps, weights = zip(*self._get_timestamps_and_weights(blocks))

        if len(timestamps) < 2:
            return self.MIN_WEIGHT

        dt = timestamps[-1] - timestamps[0]
        assert dt > 0

        logH = 0.0
        for weight in weights:
            logH = sum_weights(logH, weight)
        weight = logH - math.log(dt, 2) + math.log(self.T, 2)

        # apply a maximum change in weight
        max_dw = self.MAX_DW
        dw = weight - weights[-1]
        if dw > max_dw:
            weight = weights[-1] + max_dw
        elif dw < -max_dw:
            weight = weights[-1] - max_dw

        # apply min weight
        if weight < self.MIN_WEIGHT:
            weight = self.MIN_WEIGHT

        return weight


class LWMA(DAA):
    T = 30     # masari/cryptonote: DIFFICULTY_TARGET = 60 // seconds
    N = 134    # masari/cryptonote: DIFFICULTY_WINDOW = 720 // blocks
    FTL = 150  # masari/cryptonote: BLOCK_FUTURE_TIME_LIMIT = DIFFICULTY_TARGET * 5
    PTL = 150  # masari/cryptonote: BLOCK_PAST_TIME_LIMIT = DIFFICULTY_TARGET * 5
    MIN_WEIGHT = 21.0
    MIN_LWMA = T // 4  # =7

    # To get an average solvetime to within +/- ~0.1%, use an adjustment factor.
    # adjust=0.998 for N = 60  TODO: recalculate for N = 30
    _ADJUST = 0.998

    def __init__(self, n=None, *, debug=False):
        self.debug = debug
        self.n = self.N if n is None else n

    def _get_solvetimes_and_diffs(self, blocks: Iterator[Tuple[int, float]]) -> List[Tuple[int, int]]:
        from itertools import accumulate
        timestamps, weights = zip(*take(blocks, self.n + 1)[::-1])
        solvetimes = [t1 - t0 for t1, t0 in zip(timestamps[1:], timestamps[:-1])]
        diffs = list(map(weight_to_diff, weights))
        return list(zip(solvetimes, diffs[:-1]))

    def next_weight(self, blocks: Iterator[Tuple[int, float]]) -> float:
        solvetimes_and_diffs = self._get_solvetimes_and_diffs(blocks)

        # Return a difficulty of 1 for first 3 blocks if it's the start of the chain.
        if len(solvetimes_and_diffs) < 3:
            return self.MIN_WEIGHT

        solvetimes, difficulties = zip(*solvetimes_and_diffs)
        N = self.n

        # Otherwise, use a smaller N if the start of the chain is less than N+1.
        if len(solvetimes) < N:
            N = len(solvetimes) - 1
        # Otherwise make sure solvetimes and difficulties are correct size.
        else:
            assert len(solvetimes) == len(difficulties) == N

        # double LWMA(0), sum_inverse_D(0), harmonic_mean_D(0), nextDifficulty(0);
        # uint64_t difficulty(0), next_difficulty(0);
        LWMA = 0.0
        sum_inverse_diff = 0.0

        # The divisor k normalizes the LWMA sum to a standard LWMA.
        k = N * (N + 1) / 2

        # Loop through N most recent blocks. N is most recently solved block.
        for i in range(N):
            solvetime = solvetimes[1]
            solvetime = min(self.PTL, max(solvetime, -self.FTL))
            difficulty = difficulties[i]
            LWMA += solvetime * (i + 1) / k
            sum_inverse_diff += 1 / difficulty

        harmonic_mean_diff = N / sum_inverse_diff

        # Limit LWMA same as Bitcoin's 1/4 in case something unforeseen occurs.
        if int(LWMA) < self.MIN_LWMA:
            LWMA = float(self.MIN_LWMA)

        next_diff = harmonic_mean_diff * self.T / LWMA * self._ADJUST
        # No limits should be employed, but this is correct way to employ a 20% symmetrical limit:
        # next_diff = max(prev_diff * 0.8, min(prev_diff / 0.8, next_diff))
        next_difficulty = int(next_diff)

        #if next_difficulty == 0:
        #    return self.MIN_WEIGHT
        weight = diff_to_weight(next_difficulty)
        if self.debug:
            print(weight, next_difficulty, int(harmonic_mean_diff), LWMA)

        #weight = max(weight, self.MIN_WEIGHT)
        return weight
