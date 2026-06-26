from enforcer import Severity, Needs, Match, FileContext, LLMConsequence

def test_severity_values():
    assert Severity.ERROR.value == "error"
    assert Severity.WARN.value == "warn"
    assert Severity.INFO.value == "info"

def test_needs_values():
    assert Needs.RAW.value == "raw"
    assert Needs.AST_TS.value == "ast_ts"

def test_match_defaults():
    m = Match(file="x.ts", line=1)
    assert m.column == 0
    assert m.message == ""
    assert m.severity == Severity.WARN
    assert m.matched_value == ""

def test_file_context():
    ctx = FileContext(path="x.ts")
    assert ctx.raw is None
    assert ctx.ast is None

def test_llm_consequence():
    c = LLMConsequence(provider="p", model="m", prompt="x")
    assert c.timeout == 30
