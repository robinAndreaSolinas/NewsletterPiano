__author__ = 'Claude'

import pytest
from lib.utils import Singleton


class Animal(Singleton):
    def __init__(self, id: int, name: str, *args, **kwargs):
        self.id = id
        self.name = name

    @classmethod
    def _get_instance_key(cls, id: int, *args, **kwargs):
        return int(id)


class Vehicle(Singleton):
    def __init__(self, id: int, brand: str, *args, **kwargs):
        self.id = id
        self.brand = brand

    @classmethod
    def _get_instance_key(cls, id: int, *args, **kwargs):
        return int(id)


class TestSingleton:

    def setup_method(self):
        """Pulisce il registro prima di ogni test."""
        Animal._instances.clear()
        Vehicle._instances.clear()

    # --- Identità ---

    def test_same_key_returns_same_instance(self):
        a1 = Animal(1, "Cat")
        a2 = Animal(1, "Dog")
        assert a1 is a2

    def test_different_keys_return_different_instances(self):
        a1 = Animal(1, "Cat")
        a2 = Animal(2, "Dog")
        assert a1 is not a2

    # --- Isolamento tra classi ---

    def test_instances_isolated_between_classes(self):
        """Animal e Vehicle con stesso id NON devono essere la stessa istanza."""
        a = Animal(1, "Cat")
        v = Vehicle(1, "Tesla")
        assert a is not v

    def test_instances_dict_isolated_between_classes(self):
        """Ogni classe deve avere il proprio _instances separato."""
        assert Animal._instances is not Vehicle._instances

    # --- Immutabilità del primo __init__ ---

    def test_first_init_wins(self):
        """Il secondo __init__ con stessa chiave non deve sovrascrivere i dati."""
        a1 = Animal(1, "Cat")
        a2 = Animal(1, "Dog")  # stessa chiave
        assert a1.name == "Cat"  # il primo vince

    # --- get_instance ---

    def test_get_instance_returns_existing(self):
        a = Animal(42, "Fox")
        assert Animal.get_instance(42) is a

    def test_get_instance_raises_on_missing_key(self):
        with pytest.raises(ValueError, match="No Animal instance found with key=99"):
            Animal.get_instance(99)

    # --- _get_instance_key di default ---

    def test_default_get_instance_key(self):
        """Singleton base usa args[0] come chiave."""
        key = Singleton._get_instance_key(42)
        assert key == 42

    def test_default_get_instance_key_no_args(self):
        """Singleton base ritorna None se nessun argomento."""
        key = Singleton._get_instance_key()
        assert key is None