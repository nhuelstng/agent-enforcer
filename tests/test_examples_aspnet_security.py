"""End-to-end tests for the examples/aspnet_security.py controller-auth rule."""
import pytest
from examples.aspnet_security import ASPNET_SECURITY_RULES
from enforcer.types import FileContext, Needs
from enforcer.parsers.tree_sitter import parse

_RULE = ASPNET_SECURITY_RULES[0]


def _check(src: str):
    if parse("class C { }", Needs.AST_CSHARP) is None:
        pytest.skip("tree-sitter c-sharp grammar not available")
    ctx = FileContext(path="Controllers/UsersController.cs", raw=src,
                      ast=parse(src, Needs.AST_CSHARP))
    ctx.changed_lines = None  # diff_only defaults False; ensure not filtered
    return _RULE.check(ctx, {})


@pytest.mark.parametrize("src", [
    "public class UsersController : ControllerBase { }\n",
    "public class OrdersController : Controller { }\n",
    "[ApiController]\npublic class ItemsController : ControllerBase { }\n",
])
def test_unguarded_controller_flags(src: str):
    """A controller deriving ControllerBase/Controller with no auth attribute is flagged."""
    assert _check(src)


@pytest.mark.parametrize("src", [
    "[Authorize]\npublic class UsersController : ControllerBase { }\n",
    "[AllowAnonymous]\npublic class PublicController : ControllerBase { }\n",
    "[Authorize(Roles = \"Admin\")]\npublic class AdminController : Controller { }\n",
    "public class UserService { }\n",
    "public class WidgetController { }\n",
])
def test_guarded_or_non_controller_clean(src: str):
    """[Authorize]/[AllowAnonymous] controllers, non-controllers, and base-less
    *Controller classes raise no violation."""
    assert not _check(src)
