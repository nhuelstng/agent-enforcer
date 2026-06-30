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


def test_tf_block_brace_inside_quoted_value():
    """A } inside a quoted string value must not close the block."""
    raw = '''app_environment = {
  FOO = "1"
  URL = "http://example.com/}"
  BAR = "2"
}
'''
    keys = TerraformBlockKeys(block_name="app_environment").extract(raw)
    assert keys == {"FOO", "URL", "BAR"}


def test_tf_block_brace_inside_comment():
    """A } inside a comment must not close the block."""
    raw = '''app_environment = {
  # This } is in a comment
  FOO = "1"
  BAR = "2"
}
'''
    keys = TerraformBlockKeys(block_name="app_environment").extract(raw)
    assert keys == {"FOO", "BAR"}


def test_tf_block_brace_inside_nested_string():
    """Multiple braces inside strings should not affect depth."""
    raw = '''app_environment = {
  FOO = "}{}}{}"
  BAR = "2"
}
'''
    keys = TerraformBlockKeys(block_name="app_environment").extract(raw)
    assert keys == {"FOO", "BAR"}


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
