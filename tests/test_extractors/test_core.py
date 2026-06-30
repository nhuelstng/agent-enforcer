"""Tests for the Extractor protocol."""
from enforcer.extractors import Extractor


class _Concrete:
    """Minimal concrete extractor satisfying the Extractor protocol."""
    def extract(self, raw: str) -> set[str]:
        return {raw}


def test_extractor_protocol_satisfied_structurally():
    """A class with an extract method satisfies the Extractor protocol."""
    obj = _Concrete()
    assert isinstance(obj, Extractor)


def test_extractor_returns_set_of_strings():
    """The extract method returns a set of strings."""
    obj = _Concrete()
    result = obj.extract("hello")
    assert result == {"hello"}
