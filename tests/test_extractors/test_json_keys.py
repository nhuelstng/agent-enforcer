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
