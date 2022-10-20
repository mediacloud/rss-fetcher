"""
types for statsd_client version 1.0.7
Phil Budne, October 2022
"""

from typing import Optional

class StatsdClient:
    def __init__(self,
                 host: Optional[str] = None,
                 port: Optional[int] = None,
                 prefix: Optional[str] = None,
                 sample_rate: Optional[float] = None): ...

    def incr(self, bucket: str, delta: int = 1,
             sample_rate: Optional[float] = None) -> None: ...

    def gauge(self, bucket: str, value: float,
              sample_rate: Optional[float] = None) -> None: ...
