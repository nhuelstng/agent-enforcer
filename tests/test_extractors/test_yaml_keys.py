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


def test_yaml_missing_pyyaml_returns_empty(monkeypatch):
    """When PyYAML is not installed, extract returns set() — no hard dependency."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("No module named 'yaml'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    raw = "key: value\n"
    assert YamlKeys().extract(raw) == set()
