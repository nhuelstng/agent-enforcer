import os
import stat
from click.testing import CliRunner
from enforcer.cli import cli


def _hook_path(cwd):
    return os.path.join(cwd, ".git", "hooks", "commit-msg")


def test_install_creates_hook(tmp_path):
    os.makedirs(tmp_path / ".git" / "hooks")
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=str(tmp_path)):
        os.makedirs(".git/hooks", exist_ok=True)
        result = runner.invoke(cli, ["install"])
        assert result.exit_code == 0
        assert os.path.exists(".git/hooks/commit-msg")
        mode = os.stat(".git/hooks/commit-msg").st_mode
        assert mode & stat.S_IXUSR
        assert (mode & 0o777) == 0o755


def test_install_refuses_without_force(tmp_path):
    os.makedirs(tmp_path / ".git" / "hooks")
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=str(tmp_path)):
        os.makedirs(".git/hooks", exist_ok=True)
        existing = ".git/hooks/commit-msg"
        with open(existing, "w") as f:
            f.write("# existing hook\n")
        os.chmod(existing, 0o755)
        result = runner.invoke(cli, ["install"])
        assert result.exit_code != 0
        assert "already exists" in result.output


def test_install_force_overwrites(tmp_path):
    os.makedirs(tmp_path / ".git" / "hooks")
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=str(tmp_path)):
        os.makedirs(".git/hooks", exist_ok=True)
        existing = ".git/hooks/commit-msg"
        with open(existing, "w") as f:
            f.write("# old hook\n")
        os.chmod(existing, 0o755)
        result = runner.invoke(cli, ["install", "--force"])
        assert result.exit_code == 0
        with open(existing) as f:
            content = f.read()
        assert "old hook" not in content
        assert "enforcer" in content
