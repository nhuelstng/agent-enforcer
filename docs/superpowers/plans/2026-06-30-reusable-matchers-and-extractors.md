# Reusable Matchers and Extractors — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `KeySetSyncMatcher`, a dataclass-based extractor library (env/TF/JSON/YAML/INI), a `StatusGate` combinator, and a `_build_shared_ctx` fix so consumers stop copy-pasting ~80-line custom matchers.

**Architecture:** Each piece lands in its existing-convention home — extractors in new `enforcer/extractors/` package, `KeySetSyncMatcher` in `enforcer/matchers/`, `StatusGate` in `enforcer/combinators/core.py`, and the shared_ctx fix in `enforcer/cli.py`. TDD throughout: failing test first, then minimal implementation.

**Tech Stack:** Python 3.14, pytest, stdlib `json`/`configparser`, lazy-imported PyYAML (already in dev env).

**Spec:** `docs/superpowers/specs/2026-06-30-reusable-matchers-and-extractors-design.md`

---

## File Structure

**Create:**
- `enforcer/extractors/__init__.py` — package exports
- `enforcer/extractors/core.py` — `Extractor` Protocol
- `enforcer/extractors/env_file.py` — `EnvFileKeys`
- `enforcer/extractors/terraform_block.py` — `TerraformBlockKeys`
- `enforcer/extractors/json_keys.py` — `JsonKeys`
- `enforcer/extractors/yaml_keys.py` — `YamlKeys`
- `enforcer/extractors/ini_section_keys.py` — `IniSectionKeys`
- `enforcer/matchers/keyset_sync.py` — `KeySetSyncMatcher`
- `examples/env_terraform_sync.py` — consumer migration example
- `tests/test_extractors/__init__.py` — test package init
- `tests/test_extractors/test_env_file.py`
- `tests/test_extractors/test_terraform_block.py`
- `tests/test_extractors/test_json_keys.py`
- `tests/test_extractors/test_yaml_keys.py`
- `tests/test_extractors/test_ini_section_keys.py`
- `tests/test_matchers/test_keyset_sync.py`
- `tests/test_combinators/test_status_gate.py`

**Modify:**
- `enforcer/combinators/core.py` — add `StatusGate` dataclass
- `enforcer/combinators/__init__.py` — export `StatusGate`
- `enforcer/matchers/__init__.py` — export `KeySetSyncMatcher`
- `enforcer/cli.py:156-170` — fix `_build_shared_ctx` to cache by path
- `enforcer_config.py` — add `extractor-test-paired` self-enforcement rule
- `tests/test_cli.py` — add multi-match `read_targets` test

---

### Task 1: Extractor Protocol + package skeleton

**Files:**
- Create: `enforcer/extractors/__init__.py`
- Create: `enforcer/extractors/core.py`
- Create: `tests/test_extractors/__init__.py`

- [ ] **Step 1: Create the Extractor Protocol**

Create `enforcer/extractors/core.py`:

```python
"""Extractor protocol: parses raw file text into a set of key strings. Pure function — no I/O."""
from __future__ import annotations
from typing import Protocol


class Extractor(Protocol):
    """Parses raw file text into a set of key strings. Pure function — no I/O."""
    def extract(self, raw: str) -> set[str]: ...
```

- [ ] **Step 2: Create the package __init__ (minimal — will grow as extractors are added)**

Create `enforcer/extractors/__init__.py`:

```python
"""Dataclass extractors: parse raw file text into key sets. One extractor per file format."""
from enforcer.extractors.core import Extractor

__all__ = ["Extractor"]
```

- [ ] **Step 3: Create the test package init**

Create `tests/test_extractors/__init__.py` (empty file).

- [ ] **Step 4: Verify imports work**

Run: `python -c "from enforcer.extractors import Extractor; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add enforcer/extractors/__init__.py enforcer/extractors/core.py tests/test_extractors/__init__.py
git commit -m "feat(extractors): add Extractor protocol and package skeleton"
```

---

### Task 2: EnvFileKeys extractor (TDD)

**Files:**
- Create: `enforcer/extractors/env_file.py`
- Test: `tests/test_extractors/test_env_file.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_extractors/test_env_file.py`:

```python
from enforcer.extractors import EnvFileKeys


def test_env_file_happy_path():
    raw = "FOO=bar\nBAZ=qux\n# comment\n\nQUUX= "
    assert EnvFileKeys().extract(raw) == {"FOO", "BAZ", "QUUX"}


def test_env_file_skips_comments_and_blanks():
    raw = "# header\n\nKEY=value\n  # indented comment\nOTHER=1"
    assert EnvFileKeys().extract(raw) == {"KEY", "OTHER"}


def test_env_file_empty_string():
    assert EnvFileKeys().extract("") == set()


def test_env_file_no_equals():
    raw = "JUST_A_KEY\nANOTHER"
    assert EnvFileKeys().extract(raw) == set()


def test_env_file_value_contains_equals():
    raw = "URL=http://example.com?x=1&y=2"
    assert EnvFileKeys().extract(raw) == {"URL"}


def test_env_file_strips_whitespace_around_key():
    raw = "  SPACED  =value\n\tTABBED\t=1"
    assert EnvFileKeys().extract(raw) == {"SPACED", "TABBED"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_extractors/test_env_file.py -v`
Expected: FAIL with `ImportError: cannot import name 'EnvFileKeys'`

- [ ] **Step 3: Implement EnvFileKeys**

Create `enforcer/extractors/env_file.py`:

```python
"""EnvFileKeys: extracts KEY names from env-style 'KEY=VALUE' lines."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class EnvFileKeys:
    """Extracts KEY names from env-style 'KEY=VALUE' lines.
    Skips blank lines, comments (#), and lines without '='. Key is the
    substring before the first '=', stripped."""
    def extract(self, raw: str) -> set[str]:
        keys: set[str] = set()
        for line in raw.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key = s.split("=", 1)[0].strip()
            if key:
                keys.add(key)
        return keys
```

- [ ] **Step 4: Export from package __init__**

Update `enforcer/extractors/__init__.py`:

```python
"""Dataclass extractors: parse raw file text into key sets. One extractor per file format."""
from enforcer.extractors.core import Extractor
from enforcer.extractors.env_file import EnvFileKeys

__all__ = ["Extractor", "EnvFileKeys"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_extractors/test_env_file.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add enforcer/extractors/env_file.py enforcer/extractors/__init__.py tests/test_extractors/test_env_file.py
git commit -m "feat(extractors): add EnvFileKeys extractor with tests"
```

---

### Task 3: TerraformBlockKeys extractor (TDD)

**Files:**
- Create: `enforcer/extractors/terraform_block.py`
- Test: `tests/test_extractors/test_terraform_block.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_extractors/test_terraform_block.py`:

```python
from enforcer.extractors import TerraformBlockKeys


def test_tf_block_happy_path():
    raw = '''
resource "aws_ecs_task_definition" "app" {
  app_environment = {
    FOO = "bar"
    BAZ = "qux"
  }
  app_secrets = {
    SECRET = "value"
  }
}
'''
    keys = TerraformBlockKeys(block_name="app_environment").extract(raw)
    assert keys == {"FOO", "BAZ"}


def test_tf_block_quoted_keys():
    raw = '''
app_environment = {
  "QUOTED_KEY" = "value"
  UNQUOTED = "other"
}
'''
    keys = TerraformBlockKeys(block_name="app_environment").extract(raw)
    assert keys == {"QUOTED_KEY", "UNQUOTED"}


def test_tf_block_missing_block():
    raw = "other_block = { FOO = 1 }"
    assert TerraformBlockKeys(block_name="app_environment").extract(raw) == set()


def test_tf_block_empty_string():
    assert TerraformBlockKeys(block_name="app_environment").extract("") == set()


def test_tf_block_skips_nested_blocks():
    raw = '''
app_environment = {
  OUTER = "val"
  nested = {
    INNER = "should-be-skipped"
  }
  AFTER = "val"
}
'''
    keys = TerraformBlockKeys(block_name="app_environment").extract(raw)
    assert keys == {"OUTER", "AFTER"}


def test_tf_block_skips_comments():
    raw = '''
app_environment = {
  # FOO = "commented"
  BAR = "real"
  #BAZ = "also-commented"
}
'''
    keys = TerraformBlockKeys(block_name="app_environment").extract(raw)
    assert keys == {"BAR"}


def test_tf_block_skips_non_uppercase_keys():
    raw = '''
app_environment = {
  VALID_KEY = "yes"
  lowercase = "no"
  MixedCase = "no"
}
'''
    keys = TerraformBlockKeys(block_name="app_environment").extract(raw)
    assert keys == {"VALID_KEY"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_extractors/test_terraform_block.py -v`
Expected: FAIL with `ImportError: cannot import name 'TerraformBlockKeys'`

- [ ] **Step 3: Implement TerraformBlockKeys**

Create `enforcer/extractors/terraform_block.py`:

```python
"""TerraformBlockKeys: extracts key names from a named Terraform block."""
from __future__ import annotations
import re
from dataclasses import dataclass


@dataclass
class TerraformBlockKeys:
    """Extracts key names from a named Terraform block (e.g. 'app_environment = { ... }').
    Finds the block by name via regex, walks its body by brace-depth counting,
    extracts 'KEY =' or '"KEY" =' assignments. Block must be top-level
    (depth 1 within the block). Nested blocks are skipped."""
    block_name: str

    def extract(self, raw: str) -> set[str]:
        pattern = rf"\b{re.escape(self.block_name)}\s*=\s*\{{"
        m = re.search(pattern, raw)
        if not m:
            return set()
        depth = 0
        body_chars: list[str] = []
        for ch in raw[m.end() - 1:]:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            if depth == 1:
                body_chars.append(ch)
        keys: set[str] = set()
        for line in "".join(body_chars).splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            km = re.match(r'"?([A-Z][A-Z0-9_]*)"?\s*=', s)
            if km:
                keys.add(km.group(1))
        return keys
```

- [ ] **Step 4: Export from package __init__**

Update `enforcer/extractors/__init__.py`:

```python
"""Dataclass extractors: parse raw file text into key sets. One extractor per file format."""
from enforcer.extractors.core import Extractor
from enforcer.extractors.env_file import EnvFileKeys
from enforcer.extractors.terraform_block import TerraformBlockKeys

__all__ = ["Extractor", "EnvFileKeys", "TerraformBlockKeys"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_extractors/test_terraform_block.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add enforcer/extractors/terraform_block.py enforcer/extractors/__init__.py tests/test_extractors/test_terraform_block.py
git commit -m "feat(extractors): add TerraformBlockKeys extractor with tests"
```

---

### Task 4: JsonKeys extractor (TDD)

**Files:**
- Create: `enforcer/extractors/json_keys.py`
- Test: `tests/test_extractors/test_json_keys.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_extractors/test_json_keys.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_extractors/test_json_keys.py -v`
Expected: FAIL with `ImportError: cannot import name 'JsonKeys'`

- [ ] **Step 3: Implement JsonKeys**

Create `enforcer/extractors/json_keys.py`:

```python
"""JsonKeys: extracts top-level keys of a JSON object."""
from __future__ import annotations
import json
from dataclasses import dataclass


@dataclass
class JsonKeys:
    """Extracts top-level keys of a JSON object. Arrays and primitives return {}.
    Designed for flat config objects (package.json, tsconfig.json, .vscode/settings.json)."""
    # ponytail: top-level only; add jsonpath selector if nested sync needed
    def extract(self, raw: str) -> set[str]:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return set()
        if isinstance(data, dict):
            return set(data.keys())
        return set()
```

- [ ] **Step 4: Export from package __init__**

Update `enforcer/extractors/__init__.py`:

```python
"""Dataclass extractors: parse raw file text into key sets. One extractor per file format."""
from enforcer.extractors.core import Extractor
from enforcer.extractors.env_file import EnvFileKeys
from enforcer.extractors.terraform_block import TerraformBlockKeys
from enforcer.extractors.json_keys import JsonKeys

__all__ = ["Extractor", "EnvFileKeys", "TerraformBlockKeys", "JsonKeys"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_extractors/test_json_keys.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add enforcer/extractors/json_keys.py enforcer/extractors/__init__.py tests/test_extractors/test_json_keys.py
git commit -m "feat(extractors): add JsonKeys extractor with tests"
```

---

### Task 5: YamlKeys extractor (TDD)

**Files:**
- Create: `enforcer/extractors/yaml_keys.py`
- Test: `tests/test_extractors/test_yaml_keys.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_extractors/test_yaml_keys.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_extractors/test_yaml_keys.py -v`
Expected: FAIL with `ImportError: cannot import name 'YamlKeys'`

- [ ] **Step 3: Implement YamlKeys**

Create `enforcer/extractors/yaml_keys.py`:

```python
"""YamlKeys: extracts top-level keys of a YAML mapping (lazy PyYAML import)."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class YamlKeys:
    """Extracts top-level keys of a YAML mapping. Lists and scalars return {}.
    PyYAML imported lazily — users not using this extractor pay no dependency cost.
    Designed for flat config (docker-compose service env, GitHub Actions inputs/outputs)."""
    # ponytail: silent no-op if PyYAML absent; add hard dep if YAML sync becomes core use case
    def extract(self, raw: str) -> set[str]:
        try:
            import yaml  # lazy: avoid hard PyYAML dep for non-YAML users
        except ImportError:
            return set()
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError:
            return set()
        if isinstance(data, dict):
            return set(data.keys())
        return set()
```

- [ ] **Step 4: Export from package __init__**

Update `enforcer/extractors/__init__.py`:

```python
"""Dataclass extractors: parse raw file text into key sets. One extractor per file format."""
from enforcer.extractors.core import Extractor
from enforcer.extractors.env_file import EnvFileKeys
from enforcer.extractors.terraform_block import TerraformBlockKeys
from enforcer.extractors.json_keys import JsonKeys
from enforcer.extractors.yaml_keys import YamlKeys

__all__ = ["Extractor", "EnvFileKeys", "TerraformBlockKeys", "JsonKeys", "YamlKeys"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_extractors/test_yaml_keys.py -v`
Expected: PASS (8 tests)

- [ ] **Step 6: Commit**

```bash
git add enforcer/extractors/yaml_keys.py enforcer/extractors/__init__.py tests/test_extractors/test_yaml_keys.py
git commit -m "feat(extractors): add YamlKeys extractor with lazy PyYAML import"
```

---

### Task 6: IniSectionKeys extractor (TDD)

**Files:**
- Create: `enforcer/extractors/ini_section_keys.py`
- Test: `tests/test_extractors/test_ini_section_keys.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_extractors/test_ini_section_keys.py`:

```python
from enforcer.extractors import IniSectionKeys


def test_ini_happy_path():
    raw = "[default]\nfoo = bar\nbaz = qux\n\n[other]\nkey = val\n"
    assert IniSectionKeys(section="default").extract(raw) == {"foo", "baz"}


def test_ini_other_section():
    raw = "[default]\nfoo = bar\n\n[other]\nkey = val\n"
    assert IniSectionKeys(section="other").extract(raw) == {"key"}


def test_ini_missing_section():
    raw = "[default]\nfoo = bar\n"
    assert IniSectionKeys(section="nonexistent").extract(raw) == set()


def test_ini_empty_string():
    assert IniSectionKeys(section="default").extract("") == set()


def test_ini_malformed():
    raw = "not an ini file\njust text\n"
    assert IniSectionKeys(section="default").extract(raw) == set()


def test_ini_section_with_no_keys():
    raw = "[default]\n\n[other]\nkey = val\n"
    assert IniSectionKeys(section="default").extract(raw) == set()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_extractors/test_ini_section_keys.py -v`
Expected: FAIL with `ImportError: cannot import name 'IniSectionKeys'`

- [ ] **Step 3: Implement IniSectionKeys**

Create `enforcer/extractors/ini_section_keys.py`:

```python
"""IniSectionKeys: extracts keys within a named INI section."""
from __future__ import annotations
import configparser
from dataclasses import dataclass


@dataclass
class IniSectionKeys:
    """Extracts keys within a named INI section. Useful for .editorconfig, .flake8,
    setup.cfg-style configs where keys must stay in sync across files."""
    section: str

    def extract(self, raw: str) -> set[str]:
        parser = configparser.ConfigParser()
        try:
            parser.read_string(raw)
        except configparser.Error:
            return set()
        if parser.has_section(self.section):
            return set(parser.options(self.section))
        return set()
```

- [ ] **Step 4: Export from package __init__**

Update `enforcer/extractors/__init__.py`:

```python
"""Dataclass extractors: parse raw file text into key sets. One extractor per file format."""
from enforcer.extractors.core import Extractor
from enforcer.extractors.env_file import EnvFileKeys
from enforcer.extractors.terraform_block import TerraformBlockKeys
from enforcer.extractors.json_keys import JsonKeys
from enforcer.extractors.yaml_keys import YamlKeys
from enforcer.extractors.ini_section_keys import IniSectionKeys

__all__ = [
    "Extractor", "EnvFileKeys", "TerraformBlockKeys",
    "JsonKeys", "YamlKeys", "IniSectionKeys",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_extractors/test_ini_section_keys.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Run full extractor test suite**

Run: `pytest tests/test_extractors/ -v`
Expected: PASS (all 34 extractor tests across all files)

- [ ] **Step 7: Commit**

```bash
git add enforcer/extractors/ini_section_keys.py enforcer/extractors/__init__.py tests/test_extractors/test_ini_section_keys.py
git commit -m "feat(extractors): add IniSectionKeys extractor with tests"
```

---

### Task 7: KeySetSyncMatcher (TDD)

**Files:**
- Create: `enforcer/matchers/keyset_sync.py`
- Modify: `enforcer/matchers/__init__.py:1-42`
- Test: `tests/test_matchers/test_keyset_sync.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_matchers/test_keyset_sync.py`:

```python
import pytest
from enforcer import FileContext, Needs, Match
from enforcer.matchers import KeySetSyncMatcher
from enforcer.extractors import EnvFileKeys, TerraformBlockKeys


def _ctx(path, raw):
    return FileContext(path=path, raw=raw)


def test_keyset_sync_finds_missing_keys():
    source = _ctx(".env.config.example", "FOO=bar\nBAZ=qux\nMISSING=1\n")
    tf_raw = "app_environment = {\n  FOO = \"a\"\n  BAZ = \"b\"\n}\n"
    shared = {"infra/dev/main.tf": _ctx("infra/dev/main.tf", tf_raw)}
    matcher = KeySetSyncMatcher(
        source_extractor=EnvFileKeys(),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["infra/*/main.tf"],
    )
    matches = matcher.find(source, shared)
    assert len(matches) == 1
    assert matches[0].matched_value == "MISSING"
    assert matches[0].file == ".env.config.example"
    assert matches[0].line == 0


def test_keyset_sync_all_present():
    source = _ctx(".env", "FOO=1\nBAZ=2\n")
    tf_raw = "app_environment = {\n  FOO = \"a\"\n  BAZ = \"b\"\n}\n"
    shared = {"infra/dev/main.tf": _ctx("infra/dev/main.tf", tf_raw)}
    matcher = KeySetSyncMatcher(
        source_extractor=EnvFileKeys(),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["infra/*/main.tf"],
    )
    assert matcher.find(source, shared) == []


def test_keyset_sync_exclude_keys_removed_from_used():
    source = _ctx(".env", "FOO=1\nDEV_ONLY=2\n")
    tf_raw = "app_environment = {\n  FOO = \"a\"\n}\n"
    shared = {"infra/dev/main.tf": _ctx("infra/dev/main.tf", tf_raw)}
    matcher = KeySetSyncMatcher(
        source_extractor=EnvFileKeys(),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["infra/*/main.tf"],
        exclude_keys={"DEV_ONLY"},
    )
    assert matcher.find(source, shared) == []


def test_keyset_sync_multiple_globs_union():
    source = _ctx(".env", "A=1\nB=2\nC=3\n")
    shared = {
        "dev/main.tf": _ctx("dev/main.tf", "app_environment = {\n  A = \"1\"\n}\n"),
        "prod/main.tf": _ctx("prod/main.tf", "app_environment = {\n  B = \"2\"\n  C = \"3\"\n}\n"),
    }
    matcher = KeySetSyncMatcher(
        source_extractor=EnvFileKeys(),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["dev/*.tf", "prod/*.tf"],
    )
    assert matcher.find(source, shared) == []


def test_keyset_sync_multiple_files_per_glob():
    source = _ctx(".env", "A=1\nB=2\n")
    shared = {
        "infra/dev/main.tf": _ctx("infra/dev/main.tf", "app_environment = {\n  A = \"1\"\n}\n"),
        "infra/prod/main.tf": _ctx("infra/prod/main.tf", "app_environment = {\n  B = \"2\"\n}\n"),
    }
    matcher = KeySetSyncMatcher(
        source_extractor=EnvFileKeys(),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["infra/*/main.tf"],
    )
    assert matcher.find(source, shared) == []


def test_keyset_sync_empty_shared_ctx():
    source = _ctx(".env", "FOO=1\n")
    matcher = KeySetSyncMatcher(
        source_extractor=EnvFileKeys(),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["infra/*/main.tf"],
    )
    assert matcher.find(source, {}) == []


def test_keyset_sync_skips_double_underscore_keys():
    source = _ctx(".env", "FOO=1\n")
    shared = {
        "__rules__": _ctx("__rules__", "app_environment = {\n  FOO = \"1\"\n}\n"),
        "__workspace__": ".",
    }
    matcher = KeySetSyncMatcher(
        source_extractor=EnvFileKeys(),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["*"],
    )
    matches = matcher.find(source, shared)
    assert len(matches) == 1
    assert matches[0].matched_value == "FOO"


def test_keyset_sync_self_matching_guard():
    """Source file appearing in target_globs must not satisfy its own check."""
    source = _ctx("config.tf", "app_environment = {\n  FOO = \"1\"\n}\n")
    shared = {"config.tf": source}
    matcher = KeySetSyncMatcher(
        source_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["*.tf"],
    )
    # Source has FOO; without the guard, it would satisfy itself → []. With the
    # guard, no target contributes → FOO is missing → 1 match.
    matches = matcher.find(source, shared)
    assert len(matches) == 1
    assert matches[0].matched_value == "FOO"


def test_keyset_sync_empty_target_globs_raises():
    with pytest.raises(ValueError, match="target_globs"):
        KeySetSyncMatcher(
            source_extractor=EnvFileKeys(),
            target_extractor=TerraformBlockKeys(block_name="app_environment"),
            target_globs=[],
        )


def test_keyset_sync_needs_raw():
    matcher = KeySetSyncMatcher(
        source_extractor=EnvFileKeys(),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["*.tf"],
    )
    assert matcher.needs == Needs.RAW


def test_keyset_sync_sorted_output():
    source = _ctx(".env", "ZEBRA=1\nALPHA=2\nMIKE=3\n")
    shared = {
        "dev/main.tf": _ctx("dev/main.tf", "app_environment = {\n}\n"),
    }
    matcher = KeySetSyncMatcher(
        source_extractor=EnvFileKeys(),
        target_extractor=TerraformBlockKeys(block_name="app_environment"),
        target_globs=["dev/*.tf"],
    )
    matches = matcher.find(source, shared)
    values = [m.matched_value for m in matches]
    assert values == ["ALPHA", "MIKE", "ZEBRA"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_matchers/test_keyset_sync.py -v`
Expected: FAIL with `ImportError: cannot import name 'KeySetSyncMatcher'`

- [ ] **Step 3: Implement KeySetSyncMatcher**

Create `enforcer/matchers/keyset_sync.py`:

```python
"""KeySetSyncMatcher: cross-file key-set sync. Keys in source must appear in target files."""
from __future__ import annotations
from dataclasses import dataclass, field
from enforcer.types import Match, FileContext, Needs


@dataclass
class KeySetSyncMatcher:
    """Cross-file key-set sync. Keys extracted from this file via source_extractor
    must appear (after exclude_keys removal) in the union of keys extracted from
    target files via target_extractor. Emits one Match per missing key.

    Target files are resolved from shared_ctx by glob-matching the keys populated
    by the runner's read_targets mechanism. No direct file I/O — fully testable
    via an injected shared_ctx dict.
    """
    source_extractor: "object"
    target_extractor: "object"
    target_globs: list[str]
    exclude_keys: set[str] = field(default_factory=set)
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        shared_ctx = shared_ctx or {}
        if not file_ctx.raw:
            return []
        used = self.source_extractor.extract(file_ctx.raw) - self.exclude_keys
        allowed: set[str] = set()
        for glob in self.target_globs:
            for path, ctx in self._matching_targets(glob, shared_ctx, file_ctx.path):
                if ctx.raw:
                    allowed |= self.target_extractor.extract(ctx.raw)
        return [
            Match(file=file_ctx.path, line=0, matched_value=key)
            for key in sorted(used - allowed)
        ]

    def _matching_targets(self, glob, shared_ctx, source_path):
        from enforcer.rule import _glob_match
        for key, ctx in shared_ctx.items():
            if key.startswith("__"):
                continue
            if key == source_path:
                continue
            if _glob_match(key, glob):
                yield key, ctx

    def __post_init__(self):
        if not self.target_globs:
            raise ValueError("target_globs must be non-empty — empty list emits a match for every source key")
```

Note: `source_extractor`/`target_extractor` are typed as `"object"` (not `"Extractor"`) to avoid importing `Extractor` at module load — keeps the matcher decoupled from the extractors package and avoids any circular import risk. The `Extractor` Protocol is structural; any object with `.extract(raw) -> set[str]` satisfies it at runtime.

- [ ] **Step 4: Export from matchers __init__**

Modify `enforcer/matchers/__init__.py` — add the import after line 20 (`from enforcer.matchers.doc_sync import DocSyncMatcher`):

```python
from enforcer.matchers.keyset_sync import KeySetSyncMatcher
```

Add `"KeySetSyncMatcher",` to `__all__` (after `"DocSyncMatcher",`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_matchers/test_keyset_sync.py -v`
Expected: PASS (11 tests)

- [ ] **Step 6: Commit**

```bash
git add enforcer/matchers/keyset_sync.py enforcer/matchers/__init__.py tests/test_matchers/test_keyset_sync.py
git commit -m "feat(matchers): add KeySetSyncMatcher for cross-file key-set sync"
```

---

### Task 8: StatusGate combinator (TDD)

**Files:**
- Modify: `enforcer/combinators/core.py` (add `StatusGate` after `NoneOf` at line 117)
- Modify: `enforcer/combinators/__init__.py:1-4`
- Test: `tests/test_combinators/test_status_gate.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_combinators/test_status_gate.py`:

```python
from enforcer import FileContext
from enforcer.matchers import RegexMatcher
from enforcer.combinators import StatusGate


def test_status_gate_runs_when_status_allowed():
    ctx = FileContext(path="x.py", raw="print('hello')\n", status="added")
    inner = RegexMatcher(r"print\(")
    gate = StatusGate(inner, allowed_statuses={"added"})
    matches = gate.find(ctx)
    assert len(matches) == 1


def test_status_gate_skips_when_status_not_allowed():
    ctx = FileContext(path="x.py", raw="print('hello')\n", status="modified")
    inner = RegexMatcher(r"print\(")
    gate = StatusGate(inner, allowed_statuses={"added"})
    assert gate.find(ctx) == []


def test_status_gate_default_allowed_is_added():
    ctx_added = FileContext(path="x.py", raw="print()\n", status="added")
    ctx_modified = FileContext(path="x.py", raw="print()\n", status="modified")
    gate = StatusGate(RegexMatcher(r"print\("))
    assert len(gate.find(ctx_added)) == 1
    assert gate.find(ctx_modified) == []


def test_status_gate_custom_statuses():
    ctx = FileContext(path="x.py", raw="print()\n", status="deleted")
    gate = StatusGate(RegexMatcher(r"print\("), allowed_statuses={"added", "deleted"})
    assert len(gate.find(ctx)) == 1


def test_status_gate_passes_shared_ctx_to_inner():
    from enforcer.matchers import AllowlistMatcher
    import re
    target_raw = "--color-primary: #fff;"
    file_raw = "var(--color-primary);"
    shared = {"colors.scss": FileContext(path="colors.scss", raw=target_raw)}
    ctx = FileContext(path="x.ts", raw=file_raw, status="added")
    inner = AllowlistMatcher(
        extractor=lambda raw: set(re.findall(r'--([\w-]+):', raw)),
        consumer=lambda raw: set(re.findall(r'var\(--([\w-]+)\)', raw)),
        read_target="**/colors.scss",
    )
    gate = StatusGate(inner)
    matches = gate.find(ctx, shared)
    assert matches == []


def test_status_gate_finalizer_collected():
    """A matcher with finalize_duplicates inside StatusGate must still be collected by _collect_finalizers."""
    from enforcer.combinators.core import _collect_finalizers
    from enforcer.matchers import RegexMatcher

    class FakeFinalizerMatcher:
        needs = None
        def find(self, file_ctx, shared_ctx=None):
            return []
        def finalize_duplicates(self, matches, shared_ctx):
            return matches

    gate = StatusGate(FakeFinalizerMatcher())
    finalizers = _collect_finalizers(gate)
    assert any(hasattr(f, "finalize_duplicates") for f in finalizers)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_combinators/test_status_gate.py -v`
Expected: FAIL with `ImportError: cannot import name 'StatusGate'`

- [ ] **Step 3: Implement StatusGate**

Modify `enforcer/combinators/core.py` — add after the `NoneOf` class (after line 117):

```python
@dataclass
class StatusGate:
    """Runs inner matcher only when file_ctx.status is in allowed_statuses.
    Returns [] otherwise. Composes any matcher — PairedFileMatcher, KeySetSyncMatcher,
    RegexMatcher, anything. Replaces hand-rolled NewFilePairedFileMatcher wrapper
    in agent-skill-management-library."""
    matcher: object
    allowed_statuses: set[str] = field(default_factory=lambda: {"added"})
    needs: Needs = Needs.RAW

    def find(self, file_ctx: FileContext, shared_ctx: dict | None = None) -> list[Match]:
        """Run inner matcher only if file_ctx.status is allowed, else return []."""
        if file_ctx.status not in self.allowed_statuses:
            return []
        return _run(self.matcher, file_ctx, shared_ctx)
```

- [ ] **Step 4: Export from combinators __init__**

Modify `enforcer/combinators/__init__.py`:

```python
"""Logical combinators for matchers: AllOf, AnyOf, OneOf, Not, NoneOf, StatusGate."""
from enforcer.combinators.core import AllOf, AnyOf, OneOf, Not, NoneOf, StatusGate

__all__ = ["AllOf", "AnyOf", "OneOf", "Not", "NoneOf", "StatusGate"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_combinators/test_status_gate.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add enforcer/combinators/core.py enforcer/combinators/__init__.py tests/test_combinators/test_status_gate.py
git commit -m "feat(combinators): add StatusGate to gate matchers by file status"
```

---

### Task 9: Fix `_build_shared_ctx` to cache all glob matches by path

**Files:**
- Modify: `enforcer/cli.py:156-170`
- Test: `tests/test_cli.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_build_shared_ctx_caches_all_glob_matches(tmp_path):
    """_build_shared_ctx must cache FileContext for every file matching a read_target glob, not just the first."""
    from enforcer.cli import _build_shared_ctx
    from enforcer.config import Config
    from enforcer.context import FileContextBuilder
    from enforcer import Rule, Severity
    from enforcer.matchers import RegexMatcher

    (tmp_path / "dev").mkdir()
    (tmp_path / "prod").mkdir()
    (tmp_path / "dev" / "main.tf").write_text("app_environment = {\n  FOO = \"1\"\n}\n")
    (tmp_path / "prod" / "main.tf").write_text("app_environment = {\n  BAR = \"2\"\n}\n")

    config = Config(
        rules=[Rule(
            id="x",
            severity=Severity.ERROR,
            matchers=[RegexMatcher(r"FOO")],
            file_globs=["*.tf"],
            read_targets=["*/main.tf"],
        )],
        workspace=str(tmp_path),
    )
    builder = FileContextBuilder(config.rules, workspace=str(tmp_path))
    ctx = _build_shared_ctx(config, builder, str(tmp_path))

    assert "dev/main.tf" in ctx
    assert "prod/main.tf" in ctx
    assert ctx["dev/main.tf"].raw is not None
    assert "FOO" in ctx["dev/main.tf"].raw
    assert "BAR" in ctx["prod/main.tf"].raw


def test_build_shared_ctx_overlapping_globs_dedupe(tmp_path):
    """Two rules with overlapping globs build each file's context only once."""
    from enforcer.cli import _build_shared_ctx
    from enforcer.config import Config
    from enforcer.context import FileContextBuilder
    from enforcer import Rule, Severity
    from enforcer.matchers import RegexMatcher

    (tmp_path / "shared.tf").write_text("FOO = 1\n")

    config = Config(
        rules=[
            Rule(id="r1", severity=Severity.ERROR, matchers=[RegexMatcher(r"X")], file_globs=["*.tf"], read_targets=["*.tf"]),
            Rule(id="r2", severity=Severity.ERROR, matchers=[RegexMatcher(r"Y")], file_globs=["*.tf"], read_targets=["*.tf"]),
        ],
        workspace=str(tmp_path),
    )
    builder = FileContextBuilder(config.rules, workspace=str(tmp_path))
    ctx = _build_shared_ctx(config, builder, str(tmp_path))

    file_keys = [k for k in ctx if not k.startswith("__")]
    assert file_keys == ["shared.tf"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py::test_build_shared_ctx_caches_all_glob_matches tests/test_cli.py::test_build_shared_ctx_overlapping_globs_dedupe -v`
Expected: FAIL — `dev/main.tf` missing from `shared_ctx` (only the glob string is cached under the old code).

- [ ] **Step 3: Apply the fix**

Modify `enforcer/cli.py` — replace the `_build_shared_ctx` function (lines 156-170) with:

```python
def _build_shared_ctx(config, builder, ws: str) -> dict:
    """Build shared context dict from rule read_targets. Caches FileContext per matched path (not per glob string)."""
    shared_ctx: dict = {}
    shared_ctx["__rules__"] = config.rules
    shared_ctx["__workspace__"] = config.workspace or ws
    for rule in config.rules:
        for target in getattr(rule, "read_targets", []):
            root = Path(ws)
            for match in root.glob(target):
                rel = str(match.relative_to(ws)) if match.is_relative_to(ws) else str(match)
                if rel not in shared_ctx:
                    shared_ctx[rel] = builder.build(rel)
    return shared_ctx
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `pytest tests/test_cli.py::test_build_shared_ctx_caches_all_glob_matches tests/test_cli.py::test_build_shared_ctx_overlapping_globs_dedupe -v`
Expected: PASS

- [ ] **Step 5: Run the existing shared_ctx test to verify no regression**

Run: `pytest tests/test_cli.py::test_build_shared_ctx_stashes_rules -v`
Expected: PASS

- [ ] **Step 6: Run full test suite for regressions**

Run: `pytest --tb=short -q`
Expected: PASS (all existing tests still green)

- [ ] **Step 7: Commit**

```bash
git add enforcer/cli.py tests/test_cli.py
git commit -m "fix(cli): cache all read_target glob matches by path, not just the first"
```

---

### Task 10: Self-enforcement — add `extractor-test-paired` rule

**Files:**
- Modify: `enforcer_config.py` (add rule after `core-test-paired` at line 138)

- [ ] **Step 1: Add the rule to enforcer_config.py**

In `enforcer_config.py`, after the `core-test-paired` Rule block (after line 138, before the `# ─── Naming:` comment), insert:

```python

    # ─── Test pairing: every extractor has a test ──────────────────────
    Rule(
        id="extractor-test-paired",
        severity=Severity.ERROR,
        matchers=[PairedFileMatcher(
            source_glob="enforcer/extractors/*.py",
            derived_glob="tests/test_extractors/test_{stem}*.py",
            exclude_stems=["__init__", "core"],
        )],
        file_globs=["enforcer/extractors/*.py"],
        exclude_globs=["enforcer/extractors/__init__.py", "enforcer/extractors/core.py"],
        message="Extractor {file} has no paired test. Create tests/test_extractors/test_{stem}*.py",
        fix_instruction="Add a test file covering happy path, empty/malformed input, and format-specific edge cases.",
        diff_only=True,
        rationale="Extractors are pure string transforms — trivial to test. Missing tests mean regressions in key extraction go unnoticed.",
    ),
```

- [ ] **Step 2: Run the enforcer against its own config to verify no self-violations**

Run: `python -m enforcer.cli check --all --config enforcer_config.py`
Expected: exit code 0 (no violations — all extractors have paired tests from Tasks 2-6)

- [ ] **Step 3: Run full test suite**

Run: `pytest --tb=short -q`
Expected: PASS

- [ ] **Step 4: Regenerate CONVENTIONS.md**

Run: `python -m enforcer.cli sync-doc --config enforcer_config.py`
Expected: `CONVENTIONS.md` updated with the new `extractor-test-paired` rule.

- [ ] **Step 5: Commit**

```bash
git add enforcer_config.py CONVENTIONS.md
git commit -m "feat(self-enforce): add extractor-test-paired rule for extractors package"
```

---

### Task 11: Consumer migration example

**Files:**
- Create: `examples/env_terraform_sync.py`

- [ ] **Step 1: Create the example file**

Create `examples/env_terraform_sync.py`:

```python
"""Env-file <-> Terraform block key sync. Replaces the 80-line
EnvTerraformSyncMatcher in agent-skill-management-library's enforcer_config.py.

Copy this into your enforcer_config.py, adjust the paths and exclude_keys to
match your project, and the two rules enforce env<->TF key consistency.
"""
from enforcer import Rule, Severity
from enforcer.matchers import KeySetSyncMatcher
from enforcer.extractors import EnvFileKeys, TerraformBlockKeys

TF_FILES = "infrastructure/aws/service/*/main.tf"

# Keys present in .env.config.example that are intentionally absent from
# Terraform app_environment because they are dev-only or have universal
# code defaults that make cluster injection unnecessary.
CONFIG_DEV_LOCAL_KEYS = {
    "ANTHROPIC_BASE_URL",
    "LLM_DEBUG_PROMPTS",
    "AUTO_APPROVE_DEFAULT_THRESHOLD",
    "AUTO_APPROVE_DEFAULT_COOLDOWN_MINUTES",
    "MCP_OAUTH_ENABLED",
    "DEV__AUTH__ADMIN_URL",
    "DEV__AUTH__ADMIN_REALM",
    "DEV__AUTH__ADMIN_USER",
    "DEV__AUTH__TARGET_REALM",
}

# Keys present in .env.secrets.example that are intentionally absent from
# Terraform app_secrets (dev-local credentials never pushed to clusters).
SECRETS_DEV_LOCAL_KEYS = {
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "DEV__AUTH__ADMIN_PASSWORD",
}

RULES = [
    Rule(
        id="env-config-example-tf-sync",
        severity=Severity.ERROR,
        matchers=[KeySetSyncMatcher(
            source_extractor=EnvFileKeys(),
            target_extractor=TerraformBlockKeys(block_name="app_environment"),
            target_globs=[TF_FILES],
            exclude_keys=CONFIG_DEV_LOCAL_KEYS,
        )],
        file_globs=[".env.config.example"],
        read_targets=[TF_FILES],
        message="Key '{matched_value}' is active in .env.config.example but missing from app_environment in Terraform.",
        fix_instruction=(
            "Add the key to infrastructure/aws/service/dev/main.tf and "
            "infrastructure/aws/service/prod/main.tf app_environment blocks. "
            "If it is intentionally dev-local, add it to CONFIG_DEV_LOCAL_KEYS."
        ),
        rationale=(
            "Every non-sensitive config key in .env.config.example must appear in "
            "Terraform app_environment. Agents update the env file for local dev "
            "but forget Terraform — the cluster then fails on the next deploy."
        ),
    ),
    Rule(
        id="env-secrets-example-tf-sync",
        severity=Severity.ERROR,
        matchers=[KeySetSyncMatcher(
            source_extractor=EnvFileKeys(),
            target_extractor=TerraformBlockKeys(block_name="app_secrets"),
            target_globs=[TF_FILES],
            exclude_keys=SECRETS_DEV_LOCAL_KEYS,
        )],
        file_globs=[".env.secrets.example"],
        read_targets=[TF_FILES],
        message="Key '{matched_value}' is active in .env.secrets.example but missing from app_secrets in Terraform.",
        fix_instruction=(
            "Add the key to infrastructure/aws/service/dev/main.tf and "
            "infrastructure/aws/service/prod/main.tf app_secrets blocks. "
            "If it is intentionally dev-local, add it to SECRETS_DEV_LOCAL_KEYS."
        ),
        rationale=(
            "Every cluster-facing secret in .env.secrets.example must appear in "
            "Terraform app_secrets. Agents populate the env file for local dev "
            "but forget Terraform — the deployed service starts without the credential."
        ),
    ),
]

WORKSPACE = "."
SEVERITY_ACTIONS = {
    Severity.ERROR: "block",
    Severity.WARN: "block_warn",
    Severity.INFO: "hint",
}
```

- [ ] **Step 2: Verify the example loads as a valid config**

Run: `python -c "from enforcer.config import load_config; c = load_config('examples/env_terraform_sync.py'); print(f'{len(c.rules)} rules loaded')"`
Expected: `2 rules loaded`

- [ ] **Step 3: Commit**

```bash
git add examples/env_terraform_sync.py
git commit -m "docs(examples): add env_terraform_sync example using KeySetSyncMatcher"
```

---

### Task 12: Final verification

- [ ] **Step 1: Run the full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass (existing + 34 extractor tests + 11 keyset_sync tests + 6 status_gate tests + 2 new cli tests).

- [ ] **Step 2: Run the enforcer against its own config**

Run: `python -m enforcer.cli check --all --config enforcer_config.py`
Expected: exit code 0 (no self-violations).

- [ ] **Step 3: Verify CONVENTIONS.md is in sync**

Run: `python -m enforcer.cli sync-doc --config enforcer_config.py && git diff --exit-code CONVENTIONS.md`
Expected: no diff (already regenerated in Task 10).

- [ ] **Step 4: Verify all new exports are importable**

Run:
```bash
python -c "
from enforcer.matchers import KeySetSyncMatcher
from enforcer.combinators import StatusGate
from enforcer.extractors import Extractor, EnvFileKeys, TerraformBlockKeys, JsonKeys, YamlKeys, IniSectionKeys
print('all imports ok')
"
```
Expected: `all imports ok`

- [ ] **Step 5: Final commit (if any stray changes remain)**

```bash
git status
git diff
```

If clean, done. If not, stage and commit any remaining changes with an appropriate message.
