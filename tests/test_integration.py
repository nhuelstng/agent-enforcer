import os
import re
import pytest
from enforcer import Severity
from enforcer.context import FileContextBuilder
from enforcer.runner import RuleRunner
from enforcer.reporter import Reporter
from enforcer.matchers import RegexMatcher, LineCountMatcher, AllowlistMatcher
from enforcer.rule import Rule

def test_full_run_on_fixture_repo(tmp_path):
    """End-to-end: fixture repo with known violations."""
    (tmp_path / "colors.scss").write_text("--color-primary: #fff;\n--color-secondary: #000;\n")
    (tmp_path / "component.ts").write_text(
        "background: #c8e6c9;\n"
        "color: var(--color-primary);\n"
        "border: var(--color-undefined);\n"
    )
    (tmp_path / "component.spec.ts").write_text("background: #fff;\n")
    (tmp_path / "README.md").write_text("\n".join(["line"] * 250))

    rules = [
        Rule(
            id="no-raw-hex",
            severity=Severity.ERROR,
            matchers=[RegexMatcher(r"#[0-9a-fA-F]{3,6}\b")],
            file_globs=["**/*.ts", "**/*.scss"],
            exclude_globs=["**/*.spec.ts", "**/colors.scss"],
            read_targets=["**/colors.scss"],
            message="Raw hex '{matched_value}'",
        ),
        Rule(
            id="only-defined-css-vars",
            severity=Severity.ERROR,
            matchers=[AllowlistMatcher(
                extractor=lambda raw: set(re.findall(r'--([\w-]+):', raw)),
                consumer=lambda raw: set(re.findall(r'var\(--([\w-]+)\)', raw)),
                read_target="**/colors.scss",
            )],
            file_globs=["**/*.ts"],
            read_targets=["**/colors.scss"],
            message="Undefined: --{matched_value}",
        ),
        Rule(
            id="max-lines",
            severity=Severity.WARN,
            matchers=[LineCountMatcher(max_lines=200)],
            file_globs=["README.md"],
            message="{matched_value} lines",
        ),
    ]

    builder = FileContextBuilder(rules, workspace=str(tmp_path))
    shared_ctx = {}
    colors_path = os.path.join(str(tmp_path), "colors.scss")
    if os.path.exists(colors_path):
        ctx = builder.build("colors.scss")
        shared_ctx["colors.scss"] = ctx

    runner = RuleRunner(rules, workspace=str(tmp_path), no_llm=True)
    all_matches = []
    for f in ["colors.scss", "component.ts", "component.spec.ts", "README.md"]:
        ctx = builder.build(f)
        matches = runner.run_rules_for_file(ctx, shared_ctx)
        all_matches.extend(matches)

    hex_matches = [m for m in all_matches if m.rule_id == "no-raw-hex"]
    assert len(hex_matches) == 1
    assert hex_matches[0].matched_value == "#c8e6c9"

    var_matches = [m for m in all_matches if m.rule_id == "only-defined-css-vars"]
    assert len(var_matches) == 1
    assert var_matches[0].matched_value == "color-undefined"

    spec_matches = [m for m in all_matches if ".spec." in m.file]
    assert spec_matches == []

    readme_matches = [m for m in all_matches if m.rule_id == "max-lines"]
    assert len(readme_matches) == 1

    assert Reporter().exit_code(all_matches) == 1

def test_full_run_clean_repo(tmp_path):
    """No violations -> exit 0."""
    (tmp_path / "component.ts").write_text("color: var(--color-primary);\n")
    (tmp_path / "colors.scss").write_text("--color-primary: #fff;\n")

    rules = [
        Rule(
            id="no-raw-hex",
            severity=Severity.ERROR,
            matchers=[RegexMatcher(r"#[0-9a-fA-F]{3,6}\b")],
            file_globs=["**/*.ts"],
            exclude_globs=["**/colors.scss"],
            message="Raw hex",
        ),
    ]

    builder = FileContextBuilder(rules, workspace=str(tmp_path))
    runner = RuleRunner(rules, workspace=str(tmp_path), no_llm=True)
    all_matches = []
    for f in ["component.ts", "colors.scss"]:
        ctx = builder.build(f)
        matches = runner.run_rules_for_file(ctx, {})
        all_matches.extend(matches)

    assert all_matches == []
    assert Reporter().exit_code(all_matches) == 0
