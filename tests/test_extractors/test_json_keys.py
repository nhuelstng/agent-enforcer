import json
from enforcer.extractors import JsonKeys


def test_json_happy_path():
    raw = json.dumps({"name": "app", "version": "1.0", "private": True})
    assert JsonKeys().extract(raw) == {"name", "version", "private"}


def test_json_empty_object():
    assert JsonKeys().extract("{}") == set()


def test_json_array_returns_empty():
    assert JsonKeys().extract("[1, 2, 3]") == set()


def test_json_primitive_returns_empty():
    assert JsonKeys().extract('"just a string"') == set()
    assert JsonKeys().extract("42") == set()
    assert JsonKeys().extract("null") == set()


def test_json_empty_string():
    assert JsonKeys().extract("") == set()


def test_json_malformed():
    assert JsonKeys().extract("{not valid json") == set()


def test_json_nested_keys_top_level_only():
    raw = json.dumps({"top": "val", "nested": {"inner": "should-be-skipped"}})
    assert JsonKeys().extract(raw) == {"top", "nested"}


import pytest


@pytest.mark.parametrize("raw,key", [
    ('{"name": "x"}', "name"),
    ('{"a": 1, "b": 2, "c": 3}', "b"),
    ('{"version": "1.0", "private": true}', "private"),
])
def test_json_extracts_key(raw, key):
    """Top-level object keys are present in the extracted set."""
    assert key in JsonKeys().extract(raw)


@pytest.mark.parametrize("raw,key", [
    ('{"name": "x"}', "surname"),
    ('{}', "anything"),
    ('[1, 2, 3]', "0"),
])
def test_json_absent_key(raw, key):
    """Missing keys, empty objects, and non-objects yield no such key."""
    assert not (key in JsonKeys().extract(raw))
