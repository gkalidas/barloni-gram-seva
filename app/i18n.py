"""Lightweight UI internationalisation.

A pragmatic foundation rather than a full translation: the chrome shown on
every page (navigation, language switch) is translated, the active language is
remembered in a `lang` cookie, and templates can show a scheme's Hindi name
(`name_hi`) when Hindi is selected. Adding a language is just adding its code to
SUPPORTED and filling in the strings below (e.g. Marathi `"mr"`); untranslated
keys fall back to English, so a partial translation is always safe.
"""

DEFAULT = "en"

# code -> native label shown in the language switcher.
SUPPORTED = {
    "en": "English",
    "hi": "हिंदी",
}

# key -> {lang_code: text}. Missing languages fall back to English.
_STRINGS = {
    "nav_home": {"en": "Home", "hi": "मुख्य पृष्ठ"},
    "nav_schemes": {"en": "Schemes", "hi": "योजनाएँ"},
    "nav_complaints": {"en": "Complaints", "hi": "शिकायतें"},
    "nav_officials": {"en": "Officials", "hi": "अधिकारी"},
    "nav_help": {"en": "Help", "hi": "सहायता"},
    "nav_dashboard": {"en": "Dashboard", "hi": "डैशबोर्ड"},
    "nav_documents": {"en": "Documents", "hi": "दस्तावेज़"},
    "nav_admin": {"en": "Admin", "hi": "प्रशासन"},
    "nav_account": {"en": "Account", "hi": "खाता"},
    "nav_login": {"en": "Login", "hi": "लॉगिन"},
    "nav_logout": {"en": "Logout", "hi": "लॉगआउट"},
    "language": {"en": "Language", "hi": "भाषा"},
}


def normalize(lang) -> str:
    """Return a supported language code, defaulting to English."""
    return lang if lang in SUPPORTED else DEFAULT


def t(key: str, lang: str = DEFAULT) -> str:
    """Translate `key` into `lang`, falling back to English then the key itself."""
    entry = _STRINGS.get(key)
    if not entry:
        return key
    return entry.get(normalize(lang)) or entry.get(DEFAULT) or key
