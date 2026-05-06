

class RegistryMeta(type):
    __registry = {}

    def __init__(cls, name, bases, attrs):
        super().__init__(name, bases, attrs)
        RegistryMeta.__registry[name] = set()

    def get(cls) -> tuple[object]:
        return tuple(RegistryMeta.__registry.get(cls.__name__, set()).copy())

    @property
    def registry(cls):
        return RegistryMeta.__registry


class Registry(metaclass=RegistryMeta):

    def register(self):
        self.__class__.registry[self.__class__.__name__].add(self)