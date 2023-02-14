import locale
from typing import NewType

LanguageCode = NewType("LanguageCode", str)
DEFAULT_LANGUAGE = LanguageCode("en")
DEFAULT_LOCALE = "en_US"


def get_locale():
    """Get the current locale."""
    try:
        # Use the operating system's locale.
        current_locale, encoding = locale.getdefaultlocale()
        # Get the language code.
        if current_locale is None:
            return DEFAULT_LOCALE
    except ValueError:  # pragma: no cover
        return DEFAULT_LOCALE
    return current_locale


def get_locale_code() -> LanguageCode:
    """Get the current locale code."""
    current_locale = get_locale()
    return LanguageCode(current_locale[:2])
