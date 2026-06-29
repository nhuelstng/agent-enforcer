"""TDD tests for MCP server parity with CLI. These fail until mcp_server reuses cli helpers."""
import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from enforcer.mcp_server import check_conventions, verify_fix


def _write_config(tmpdir: str, rules_src: str) -> Path:
    config = f'''
from enforcer import Rule, Severity
{rules_src}
RULES = _RULES
WORKSPACE = "."
SEVERITY_ACTIONS = {{
    Severity.ERROR: "block",
    Severity.WARN: "print",
    Severity.INFO: "hint",
}}
'''
    config_path = Path(tmpdir, "enforcer_config.py")
    config_path.write_text(config)
    return config_path


def _run_in_workspace(tmpdir: str, env_overrides: dict | None = None):
    env = dict(os.environ)
    env["ENFORCER_CONFIG"] = str(Path(tmpdir, "enforcer_config.py"))
    if env_overrides:
        env.update(env_overrides)
    return env


def test_check_conventions_runs_metadata_rules(tmp_path, monkeypatch):
    """MCP check_conventions must run METADATA rules. Currently it skips them — test fails."""
    (tmp_path / "app.py").write_text("x = 1\n")
    monkeypatch.chdir(tmp_path)

    rules_src = '''
from enforcer.matchers import AlwaysMatcher
from enforcer.types import RuleType
_RULES = [
    Rule(id="meta-fires", severity=Severity.ERROR,
         matchers=[AlwaysMatcher(matched_value="META_HIT")],
         file_globs=["*"], rule_type=RuleType.METADATA,
         message="metadata rule fired"),
]
'''
    _write_config(str(tmp_path), rules_src)
    monkeypatch.setenv("ENFORCER_CONFIG", str(tmp_path / "enforcer_config.py"))

    result = json.loads(check_conventions(paths=["app.py"]))
    rule_ids = [i["rule_id"] for i in result["issues"]]
    assert "meta-fires" in rule_ids, "metadata rule must run via MCP"


def test_check_conventions_applies_enforcerignore(tmp_path, monkeypatch):
    """MCP check_conventions must apply .enforcerignore. Currently it doesn't — test fails."""
    (tmp_path / "keep.py").write_text("print('x')\n")
    (tmp_path / "skip.py").write_text("print('y')\n")
    (tmp_path / ".enforcerignore").write_text("skip.py\n")
    monkeypatch.chdir(tmp_path)

    rules_src = '''
from enforcer.matchers import RegexMatcher
_RULES = [
    Rule(id="no-print", severity=Severity.ERROR,
         matchers=[RegexMatcher(r"print\\(")],
         file_globs=["*.py"], message="print() at {file}:{line}"),
]
'''
    _write_config(str(tmp_path), rules_src)
    monkeypatch.setenv("ENFORCER_CONFIG", str(tmp_path / "enforcer_config.py"))

    result = json.loads(check_conventions(paths=["keep.py", "skip.py"]))
    files = {i["file"] for i in result["issues"]}
    assert "keep.py" in files
    assert "skip.py" not in files, "MCP must respect .enforcerignore"


def test_check_conventions_runs_cross_file_finalizers(tmp_path, monkeypatch):
    """MCP check_conventions must call run_cross_file_finalizers. Currently it doesn't — test fails."""
    dup_src = "def foo():\n    a = 1\n    b = 2\n    c = 3\n    d = 4\n    e = 5\n    return a + b + c + d + e\n"
    (tmp_path / "a.py").write_text(dup_src)
    (tmp_path / "b.py").write_text(dup_src)
    monkeypatch.chdir(tmp_path)

    rules_src = '''
from enforcer.matchers import DuplicateCodeMatcher
_RULES = [
    Rule(id="dup", severity=Severity.WARN,
         matchers=[DuplicateCodeMatcher(min_tokens=8, min_overlap=0.8, workspace=".")],
         file_globs=["*.py"], message="duplicate code with {matched_value}"),
]
'''
    _write_config(str(tmp_path), rules_src)
    monkeypatch.setenv("ENFORCER_CONFIG", str(tmp_path / "enforcer_config.py"))

    result = json.loads(check_conventions(paths=["a.py", "b.py"]))
    rule_ids = {i["rule_id"] for i in result["issues"]}
    assert "dup" in rule_ids, "cross-file finalizer must run via MCP"


def test_check_conventions_uses_path_glob_not_replace_hack(tmp_path, monkeypatch):
    """read_targets with **/ glob must be resolved via Path.glob, not target.replace('**/','')."""
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "allowlist.txt").write_text("allowed_thing\n")
    (tmp_path / "checked.py").write_text("x = 1\n")
    monkeypatch.chdir(tmp_path)

    rules_src = '''
from enforcer.matchers import FileExistsMatcher
from enforcer.combinators import Not
_RULES = [
    Rule(id="need-allowlist", severity=Severity.WARN,
         matchers=[Not(FileExistsMatcher(read_target="**/allowlist.txt", workspace="."))],
         file_globs=["*.py"], message="no allowlist", read_targets=["**/allowlist.txt"]),
]
'''
    _write_config(str(tmp_path), rules_src)
    monkeypatch.setenv("ENFORCER_CONFIG", str(tmp_path / "enforcer_config.py"))

    result = json.loads(check_conventions(paths=["checked.py"]))
    rule_ids = {i["rule_id"] for i in result["issues"]}
    assert "need-allowlist" not in rule_ids, "read_targets **/ must glob correctly"


def test_verify_fix_uses_path_glob_for_read_targets(tmp_path, monkeypatch):
    """verify_fix must also use Path.glob for read_targets, not the replace hack."""
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "allowlist.txt").write_text("allowed\n")
    (tmp_path / "checked.py").write_text("x = 1\n")
    monkeypatch.chdir(tmp_path)

    rules_src = '''
from enforcer.matchers import FileExistsMatcher
from enforcer.combinators import Not
_RULES = [
    Rule(id="need-allowlist", severity=Severity.WARN,
         matchers=[Not(FileExistsMatcher(read_target="**/allowlist.txt", workspace="."))],
         file_globs=["*.py"], message="no allowlist", read_targets=["**/allowlist.txt"]),
]
'''
    _write_config(str(tmp_path), rules_src)
    monkeypatch.setenv("ENFORCER_CONFIG", str(tmp_path / "enforcer_config.py"))

    result = json.loads(verify_fix(path="checked.py", rule_id="need-allowlist"))
    assert result["summary"]["total"] == 0, "verify_fix read_targets must glob correctly"
