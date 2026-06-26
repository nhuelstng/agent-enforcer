import pytest
from enforcer import FileContext

@pytest.fixture
def sample_ts_file():
    return FileContext(
        path="src/app/x.ts",
        raw="const x = #fff;\nconst y = 1;\nconsole.log('hello');\n",
    )

@pytest.fixture
def sample_scss_file():
    return FileContext(
        path="src/styles/colors.scss",
        raw="--color-primary: #fff;\n--color-secondary: #000;\n",
    )

@pytest.fixture
def sample_readme():
    return FileContext(
        path="README.md",
        raw="\n".join(f"line {i}" for i in range(1, 201)),
    )
