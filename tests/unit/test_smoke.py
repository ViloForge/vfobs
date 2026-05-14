import pytest

from vfobs import __version__


@pytest.mark.unit
def test_package_importable():
    assert __version__ == "0.0.1"
