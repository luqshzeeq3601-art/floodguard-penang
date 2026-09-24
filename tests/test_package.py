import sys
from importlib.metadata import version

import floodguard


def test_package_version_matches_installed_metadata() -> None:
    assert floodguard.__version__ == version("floodguard")


def test_supported_python_runtime() -> None:
    assert sys.version_info >= (3, 11)
