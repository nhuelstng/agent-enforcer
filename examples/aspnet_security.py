"""ASP.NET Core security-by-default rules.

Copy the rules you want into your enforcer_config.py. They enforce a
"deny by default" posture that no Roslyn analyzer ships out of the box:
authentication is *mandatory* on every MVC controller unless it explicitly
opts out with [AllowAnonymous].

Recipe composition (see AGENTS.md#language-support):
  AstNodeMatcher(class_declaration)   — every C# class
  + NodeNamePredicate(r"Controller$") — keep the controllers
  + NotP(HasAttributePredicate(...))  — that carry no auth attribute
so a match survives only when a controller has neither [Authorize] nor
[AllowAnonymous] — i.e. a route that would ship unauthenticated by accident.
"""
from enforcer import Rule, Severity, Needs
from enforcer.matchers import AstNodeMatcher, EndpointAuthMatcher
from enforcer.predicates import NodeNamePredicate, HasAttributePredicate, HasBaseTypePredicate, NotP

CONTROLLER_GLOBS = ["**/*Controller.cs", "**/Controllers/**/*.cs"]
ENDPOINT_GLOBS = ["**/Program.cs", "**/Endpoints/**/*.cs"]

ASPNET_SECURITY_RULES = [
    Rule(
        id="controller-requires-auth",
        severity=Severity.ERROR,
        matchers=[AstNodeMatcher(node_type="class_declaration", needs=Needs.AST_CSHARP)],
        predicates=[
            NodeNamePredicate(pattern=r"Controller$"),
            HasBaseTypePredicate(pattern=r"Controller(Base)?$"),
            NotP(HasAttributePredicate(pattern=r"Authorize|AllowAnonymous")),
        ],
        file_globs=CONTROLLER_GLOBS,
        message="Controller at {file}:{line} declares no [Authorize] or [AllowAnonymous] — it would ship unauthenticated.",
        fix_instruction="Add [Authorize] to the controller (or [AllowAnonymous] if the endpoint is intentionally public).",
        rationale=(
            "Security by default: a new controller with no auth attribute exposes "
            "its actions unauthenticated. The compiler and stock analyzers never "
            "flag this — the policy that 'auth is mandatory unless opted out' is "
            "project intent, so it must be enforced structurally."
        ),
    ),
    Rule(
        id="minimal-api-endpoint-requires-auth",
        severity=Severity.ERROR,
        matchers=[EndpointAuthMatcher()],
        file_globs=ENDPOINT_GLOBS,
        message="Minimal-API endpoint {matched_value} at {file}:{line} has no inline .RequireAuthorization()/.AllowAnonymous().",
        fix_instruction="Chain .RequireAuthorization() onto the endpoint (or .AllowAnonymous() if intentionally public), or guard the group via app.MapGroup(...).RequireAuthorization().",
        rationale=(
            "The minimal-API counterpart to controller authorization: a bare "
            "app.MapGet(...) registers an unauthenticated route. The guard must be "
            "in the same fluent chain — group-level or stored-endpoint guards are "
            "not tracked, so prefer inline .RequireAuthorization() at the call site."
        ),
    ),
]

RULES = ASPNET_SECURITY_RULES
WORKSPACE = "."
SEVERITY_ACTIONS = {
    Severity.ERROR: "block",
    Severity.WARN: "block_warn",
    Severity.INFO: "hint",
}
