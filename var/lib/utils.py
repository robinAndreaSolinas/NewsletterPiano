import abc
import re
from typing import Dict, Any


class APIException(Exception):
    pass


class APIClientException(APIException):
    pass


class AbstractAPIClient(abc.ABC):
    ENDPOINT:str

    @abc.abstractmethod
    def call_api(self, path: str, method: str = "GET", **kwargs) -> Dict[str, Any]:
        pass


class Singleton:
    """
    Implementation of the Singleton Design Pattern.

    This base class ensures that only one instance exists per unique key.
    Subclasses can override `_get_instance_key()` to customize the key generation logic.

    Features:
    - Multiple instances per class, keyed by `_get_instance_key()` result
    - Instance isolation between different subclasses
    - First initialization wins: subsequent __init__ calls with the same key are ignored
    - Retrieve existing instances via `get_instance(key)`
    """
    _instances: dict = {}
    _initialized = False

    def __init_subclass__(cls, **kwargs):
        """
        Hook called when a subclass is created.

        Ensures each subclass has its own isolated `_instances` dictionary
        and wraps the subclass's __init__ to prevent re-initialization.
        """
        super().__init_subclass__(**kwargs)
        # Each subclass gets its own instance registry
        cls._instances = {}

        # Wrap __init__ to prevent multiple initialization of the same instance
        original_init = cls.__dict__.get("__init__")
        if original_init:
            def guarded_init(self, *args, **kwargs):
                # Skip __init__ if this instance was already initialized
                if getattr(self, "_initialized", False):
                    return
                original_init(self, *args, **kwargs)
                self._initialized = True

            cls.__init__ = guarded_init

    def __new__(cls, *args, **kwargs):
        """
        Control instance creation.

        Returns an existing instance if one already exists for the given key,
        otherwise creates a new instance and stores it in the registry.
        """
        key = cls._get_instance_key(*args, **kwargs)
        if key not in cls._instances:
            cls._instances[key] = super().__new__(cls)
        return cls._instances[key]

    @classmethod
    def _get_instance_key(cls, *args, **kwargs):
        """
        Generate the key used to identify unique instances.

        Default implementation uses the first positional argument as the key.
        Subclasses should override this to customize key generation logic.

        Returns:
            The key identifying this instance, or None if no arguments provided.
        """
        return args[0] if args else None

    @classmethod
    def get_instance(cls, key):
        """
        Retrieve an existing instance by its key.

        Args:
            key: The key identifying the desired instance.

        Returns:
            The instance associated with the given key.

        Raises:
            ValueError: If no instance exists for the given key.
        """
        instance = cls._instances.get(key)
        if instance is None:
            raise ValueError(f"No {cls.__name__} instance found with key={key!r}")
        return instance


def camel_to_snake(string: str) -> str:
    return re.sub(r'(?<![_])(?<!^)(?=[A-Z])(?!_)', '_', string).lower()