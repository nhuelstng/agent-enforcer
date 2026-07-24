"""Tests for check_service: the shared check ring behind the CLI and MCP."""
from types import SimpleNamespace
from enforcer.check_service import run_check, verify_fix_matches, CheckRequest
from enforcer.rule import Rule
from enforcer.types import Severity, LLMConfig
from enforcer.matchers import RegexMatcher


def _config(tmp_path, rules):
    return SimpleNamespace(rules=list(rules), workspace=str(tmp_path), llm_config=LLMConfig())


def _print_rule():
    return Rule(id="no-print", severity=Severity.ERROR, matchers=[RegexMatcher(r"print\(")],
                file_globs=["*.py"], message="print at {file}:{line}")


def test_run_check_paths_mode_flags(tmp_path):
    (tmp_path / "a.py").write_text("print('x')\n")
    matches = run_check(_config(tmp_path, [_print_rule()]), CheckRequest(paths=("a.py",)))
    assert any(m.rule_id == "no-print" for m in matches)


def test_run_check_rule_id_narrows_in_place(tmp_path):
    (tmp_path / "a.py").write_text("print('x')\nTODO\n")
    todo = Rule(id="no-todo", severity=Severity.ERROR, matchers=[RegexMatcher(r"TODO")],
                file_globs=["*.py"], message="todo")
    cfg = _config(tmp_path, [_print_rule(), todo])
    matches = run_check(cfg, CheckRequest(paths=("a.py",), rule_id="no-todo"))
    assert {m.rule_id for m in matches} == {"no-todo"}
    assert [r.id for r in cfg.rules] == ["no-todo"]


def test_run_check_applies_enforcerignore(tmp_path):
    (tmp_path / "keep.py").write_text("print('x')\n")
    (tmp_path / "skip.py").write_text("print('y')\n")
    (tmp_path / ".enforcerignore").write_text("skip.py\n")
    matches = run_check(_config(tmp_path, [_print_rule()]),
                        CheckRequest(paths=("keep.py", "skip.py")))
    files = {m.file for m in matches}
    assert "keep.py" in files
    assert "skip.py" not in files


def test_verify_fix_matches_known_rule(tmp_path):
    (tmp_path / "a.py").write_text("print('x')\n")
    matches = verify_fix_matches(_config(tmp_path, [_print_rule()]), "a.py", "no-print", no_llm=True)
    assert matches and matches[0].rule_id == "no-print"


def test_verify_fix_matches_respects_file_globs(tmp_path):
    (tmp_path / "a.txt").write_text("print('x')\n")
    # no-print targets *.py; a .txt file must yield no matches (glob gate via check_rule)
    matches = verify_fix_matches(_config(tmp_path, [_print_rule()]), "a.txt", "no-print", no_llm=True)
    assert matches == []


def test_verify_fix_matches_unknown_rule_is_none(tmp_path):
    assert verify_fix_matches(_config(tmp_path, [_print_rule()]), "a.py", "nope", no_llm=True) is None
