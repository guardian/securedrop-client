"""
Tests for the app module, which sets things up and runs the application.
"""

from tests.helper import app  # noqa: F401
from securedrop_client.locale import get_locale_code


def test_application_sets_en_as_default_language_code(mocker):
    mocker.patch("locale.getdefaultlocale", return_value=(None, None))
    language_code = get_locale_code()
    assert language_code == "en"

