"""
types for statsd_client version 1.0.7

only includes classes & methods in use
(sample_rate args included, tho not used)

Phil Budne, October 2022
"""

from typing import Optional

SampleRate = Optional[float]

class StatsdClient:
    def __init__(self,
                 host: Optional[str] = None,
                 port: Optional[int] = None,
                 prefix: Optional[str] = None,
                 sample_rate: SampleRate = None): ...

    def incr(self, bucket: str, delta: int = 1,
             sample_rate: SampleRate = None) -> None: ...

    def gauge(self, bucket: str, value: float,
              sample_rate: SampleRate = None) -> None: ...

    def timing(self, bucket: str, ms: float,
              sample_rate: SampleRate = None) -> None: ...
