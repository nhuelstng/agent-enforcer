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


import pytest
from enforcer.extractors import JsonKeys


@pytest.mark.parametrize("raw,key", [
    ('{"name": 1}', "name"),
    ('{"a": 1, "b": 2}', "b"),
    ('{"version": "1.0", "private": true}', "version"),
])
def test_concrete_extractor_extracts_key(raw, key):
    """A concrete Extractor (JsonKeys) surfaces top-level keys through the protocol."""
    assert key in JsonKeys().extract(raw)


@pytest.mark.parametrize("raw,key", [
    ('{"name": 1}', "missing"),
    ('{"a": 1}', "b"),
    ('[1, 2, 3]', "0"),
])
def test_concrete_extractor_absent_key(raw, key):
    """Keys not present in the source (or non-objects) are absent from the set."""
    assert not (key in JsonKeys().extract(raw))
