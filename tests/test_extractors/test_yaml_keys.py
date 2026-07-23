import pytest
from enforcer.extractors import YamlKeys


def test_yaml_happy_path():
    raw = "name: app\nversion: 1.0\nprivate: true\n"
    assert YamlKeys().extract(raw) == {"name", "version", "private"}


def test_yaml_empty_mapping():
    assert YamlKeys().extract("{}") == set()


def test_yaml_list_returns_empty():
    assert YamlKeys().extract("- a\n- b\n") == set()


def test_yaml_scalar_returns_empty():
    assert YamlKeys().extract("just a string\n") == set()
    assert YamlKeys().extract("42\n") == set()


def test_yaml_empty_string():
    assert YamlKeys().extract("") == set()


def test_yaml_malformed():
    assert YamlKeys().extract(":\n -\n  : bad") == set()


def test_yaml_nested_keys_top_level_only():
    raw = "top: val\nnested:\n  inner: skipped\n"
    assert YamlKeys().extract(raw) == {"top", "nested"}


def test_yaml_missing_pyyaml_raises_import_error(monkeypatch):
    """Missing PyYAML should raise ImportError, not silently return empty set.

    Silent set() causes false-positives when YamlKeys feeds KeySetSyncMatcher:
    every source key reported 'missing' because target extraction yielded nothing.
    """
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("No module named 'yaml'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError, match="PyYAML"):
        YamlKeys().extract("key: value\n")


@pytest.mark.parametrize("raw,key", [
    ("name: app\n", "name"),
    ("a: 1\nb: 2\n", "b"),
    ("version: 1.0\nprivate: true\n", "private"),
])
def test_yaml_extracts_key(raw, key):
    """Top-level mapping keys are present in the extracted set."""
    assert key in YamlKeys().extract(raw)


@pytest.mark.parametrize("raw,key", [
    ("name: app\n", "surname"),
    ("- a\n- b\n", "a"),
    ("{}", "anything"),
])
def test_yaml_absent_key(raw, key):
    """Missing keys, lists, and empty mappings yield no such key."""
    assert not (key in YamlKeys().extract(raw))
