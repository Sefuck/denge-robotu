import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from denge.parametreler import Tasarim  # noqa: E402


@pytest.fixture(scope="session")
def tasarim() -> Tasarim:
    return Tasarim.yukle()


@pytest.fixture(scope="session")
def p(tasarim):
    """Nominal (kutulu, önerilen yuva) model parametreleri."""
    return tasarim.model(kutulu=True)


@pytest.fixture(scope="session")
def p_kutusuz(tasarim):
    return tasarim.model(kutulu=False)
