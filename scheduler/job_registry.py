from __future__ import annotations
import hashlib
from typing import Literal
from lib import Registry
import logging


class JobRegistry(Registry):
    """
    Registry for scheduled jobs with configurable triggers and automatic ID generation.
    
    This class extends the base Registry to manage scheduled jobs with support for
    different trigger types (date, interval, cron). Each job is uniquely identified
    by a hash generated from its name, trigger type, and configuration parameters.
    
    Attributes:
        __algo (str): Hash algorithm used for generating job IDs (default: "sha256").
        trigger (Literal["date", "interval", "cron"]): The type of job trigger.
        kwargs (dict): Additional keyword arguments for the job configuration.
        function (callable): The function to be executed by the job.
    
    Note:
        - this class is designed to be used as a decorator, e.g., `@JobRegistry('interval', seconds=10)`.
        - the 'id' and 'name' parameters are automatically removed from the kwargs dictionary.
        - the 'id' attribute provides a unique identifier for the job.
        - this class supports multiple instances of the same job with different configurations.
        - this class is an alias for the 'job' function, which can be used as a decorator.
    
    Example:
        >>> @JobRegistry('interval', seconds=10) # OR: @job('interval', seconds=10)
        ... def my_job():
        ...     print('Hello World!')
    """
    __algo: str = "sha256"
    __slots__ = ("trigger", "kwargs", "function", "_logger")

    def __init__(self, trigger: Literal["date", "interval", "cron"],
                 logger: logging.Logger = None,
                 **kwargs):
        """
        Initialize a new JobRegistry instance.
        
        Args:
            trigger: The type of trigger for the job. Must be one of "date", "interval", or "cron".
            logger: Optional logger instance. If not provided, a default logger is created.
            **kwargs: Additional keyword arguments for job configuration (e.g., seconds, minutes, etc.).
                     The 'id' and 'name' parameters are automatically removed as they are generated.
        
        Raises:
            ValueError: If an invalid trigger type is provided.
        """
        self._logger = logger or logging.getLogger(f"{self.__class__.__name__}")

        if trigger not in ("date", "interval", "cron"):
            raise ValueError(f"Invalid trigger: {trigger}")

        self.trigger = trigger

        self.kwargs = kwargs
        self.kwargs.pop("id", None)
        self.kwargs.pop("name", None)

    @classmethod
    def set_algo(cls, algo: str):
        """
        Set the hash algorithm used for generating job IDs.
        
        Args:
            algo: The name of the hash algorithm to use. Must be available in hashlib.
                  If invalid, falls back to "sha256".
        
        Note:
            This is a class-level setting that affects all JobRegistry instances.
            Invalid algorithms trigger an error log and automatic fallback to sha256.
        """
        logger = logging.getLogger(f"{cls.__name__}")
        if algo not in hashlib.algorithms_available:
            algo = "sha256"
            logger.error(
                f"Invalid hash algorithm: {algo!r}\nAvailable algorithms: {hashlib.algorithms_available!r}\nFalling back to default: sha256")

        logger.info(f"Setting hash algorithm from {cls.__algo!r} to: {algo!r}")
        cls.__algo = algo

    @property
    def id(self) -> str:
        """
        Generate a unique identifier for the job based on its configuration.
        
        Returns:
            A hexadecimal hash string generated from the job's name, trigger, and kwargs.
        
        Note:
            The ID is deterministic - identical configurations will produce identical IDs.
        """
        encoded_string = f"{self.name}{self.trigger}{self.kwargs}".encode("utf-8")
        algo = self.__algo
        return hashlib.new(algo, encoded_string).hexdigest()

    @property
    def name(self) -> str:
        """
        Get the fully qualified name of the registered function.
        
        Returns:
            The function name in the format "module.function_name".
        """
        return f"{self.function.__module__}.{self.function.__name__}"

    def __repr__(self):
        return f"<Job(id={self.id[:8]!r}, function={self.function.__name__!r}, trigger={self.trigger!r}, {', '.join(f'{k}={v!r}' for k, v in self.kwargs.items())})>"

    ## This needs to be implemented for set() to work and drop duplicates
    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return self.id == other.id

    def __call__(self, fn, *_a, **_k):
        """
        Register a function as a scheduled job (decorator pattern).
        
        Args:
            fn: The callable function to be registered as a job.
            *_a: Positional arguments (unused, for compatibility).
            **_k: Keyword arguments (unused, for compatibility).
        
        Returns:
            The original function, allowing it to be used normally after decoration.
        
        Raises:
            TypeError: If the provided argument is not callable.
        
        Example:
            >>> @JobRegistry('interval', seconds=10)
            ... def my_task():
            ...     print("Task executed")
        """
        if not callable(fn):
            raise TypeError(f"Expected a callable function, got {type(fn).__name__}")
        self.function = fn

        self._logger.info(f"Registering job: {self}")
        self.register()
        return self.function


job = JobRegistry

__all__ = ("job", "JobRegistry")
