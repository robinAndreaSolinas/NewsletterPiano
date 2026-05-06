from __future__ import annotations
import hashlib
from typing import Literal
from lib import Registry

class JobRegistry(Registry):
    def __init__(self, trigger:Literal["date", "interval", "cron"], **kwargs):
        if trigger not in ("date", "interval", "cron"):
            raise ValueError(f"Invalid trigger: {trigger}")

        self.trigger = trigger

        self._algo = kwargs.pop("algo", None)
        if self._algo and self._algo not in hashlib.algorithms_available:
            raise ValueError(f"Invalid hash algorithm: {self._algo}\nAvailable algorithms: {hashlib.algorithms_available}")

        self.kwargs = kwargs
        self.kwargs.pop("id", None)
        self.kwargs.pop("name", None)

    @property
    def id(self) -> str:
        encoded_string = f"{self.function.__name__}{self.trigger}{self.kwargs}".encode("utf-8")
        algo = self._algo or "sha256"
        return hashlib.new(algo, encoded_string).hexdigest()

    @property
    def name(self) -> str:
        return f"{self.__class__.__name__}.{self.function.__name__}"

    def __repr__(self):
        return f"<Job(id={self.id[:8]!r}, function={self.function.__name__!r}, trigger={self.trigger!r}, {', '.join(f'{k}={v!r}' for k, v in self.kwargs.items())})>"

    ## This needs to be implemented for set() to work and drop duplicates
    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return self.id == other.id

    def __call__(self, fn, *a, **k):
        if not callable(fn):
            raise TypeError(f"Expected a callable function, got {type(fn).__name__}")
        self.function = fn
        self.register()
        return self.function


job = JobRegistry


__all__ = ("job",JobRegistry)