from typing import Dict, NamedTuple, Optional

from twisted.internet.interfaces import IReactorCore


class RateLimiterLimit(NamedTuple):
    max_hits: int
    window_seconds: int


class RateLimiter:
    """ Implement a multi-key rate limiter using the leaky bucket algorithm.
    """

    # Stores the keys that are being limited and it's RateLimit
    keys: Dict[str, RateLimiterLimit]

    # Stores the last hit for each key
    hits: Dict[str, RateLimiterLimit]

    def __init__(self, reactor: Optional[IReactorCore] = None):
        self.keys = {}
        self.hits = {}
        if reactor is None:
            from twisted.internet import reactor as twisted_reactor
            reactor = twisted_reactor
        self.reactor = reactor

    def set_limit(self, key: str, max_hits: int, window_seconds: int):
        """ Set a limit to a given key, e.g., `max_hits = 10` and
        `window_seconds = 60` means at most 10 hits per minute.

        :param key: Name of key to set the rate limit
        :param max_hits: Maximum hits allowed for this key before the limit
        :param window_seconds: The maximum hits can be done in window_seconds
        """
        assert (window_seconds > 0)
        self.keys[key] = RateLimiterLimit(max_hits, window_seconds)

    def get_limit(self, key: str):
        """ Get a limit to a given key.
        """
        return self.keys.get(key, None)

    def unset_limit(self, key: str):
        """ Unset a limit to a given key. Next calls to `add_hit` with that key will be ignored.
        """
        self.reset(key)
        self.keys.pop(key, None)

    def add_hit(self, key: str, weight: int = 1):
        """ Add a hit to a given key. You can use `weight` to add more than one hit.
        Return `True` if threshold has not been reached, or `False` otherwise.

        :param weight: How many hits this 'hit' means
        """
        if key not in self.keys:
            return True
        (max_hits, window_seconds) = self.keys[key]

        if key not in self.hits:
            self.hits[key] = RateLimiterLimit(weight, self.reactor.seconds())
            return True

        hits, latest_time = self.hits[key]

        dt = self.reactor.seconds() - latest_time

        # rate = max_hits / window_seconds (hits per second)
        # x = dt * rate
        # leaked_hits = floor(x) (hits obtained after dt seconds)
        leaked_hits, remainder = divmod(dt * max_hits, window_seconds)

        # leaked_hits * window_seconds + remainder = dt * max_hits
        # dt - remainder / max_hits = leaked_hits / rate
        new_time = latest_time + dt - remainder / float(max_hits)

        # First, update the bucket subtracting the leakage amount.
        new_hits = hits - leaked_hits
        if new_hits < 0:
            new_hits = 0

        # Then, add the new hits and check if it overflows.
        new_hits += weight
        allowance = True
        if new_hits > max_hits:
            allowance = False
            new_hits = max_hits

        self.hits[key] = RateLimiterLimit(new_hits, new_time)
        return allowance

    def reset(self, key: str):
        """ Reset the hits of a given key.
        """
        self.hits.pop(key, None)
