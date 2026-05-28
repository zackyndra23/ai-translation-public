"""Static ISO 639-1 catalog (sub-proyek I).

40-entry starter - sufficient for the current demo (covers every Streamlit
dropdown language). Expansion to the full ISO 639-1 catalog (~180 entries)
is a deferred follow-up.
"""

from __future__ import annotations

from typing import Final


class IsoLanguageEntry:
    __slots__ = ("code", "name", "native_name")

    def __init__(self, code: str, name: str, native_name: str | None = None) -> None:
        self.code = code
        self.name = name
        self.native_name = native_name


ISO_LANGUAGES: Final[list[IsoLanguageEntry]] = [
    IsoLanguageEntry("en", "English", "English"),
    IsoLanguageEntry("id", "Indonesian", "Bahasa Indonesia"),
    IsoLanguageEntry("ms", "Malay", "Bahasa Melayu"),
    IsoLanguageEntry("ja", "Japanese", "Nihongo"),
    IsoLanguageEntry("zh", "Chinese", "Zhongwen"),
    IsoLanguageEntry("ko", "Korean", "Hangugeo"),
    IsoLanguageEntry("th", "Thai", "Thai"),
    IsoLanguageEntry("vi", "Vietnamese", "Tieng Viet"),
    IsoLanguageEntry("fr", "French", "Francais"),
    IsoLanguageEntry("de", "German", "Deutsch"),
    IsoLanguageEntry("es", "Spanish", "Espanol"),
    IsoLanguageEntry("it", "Italian", "Italiano"),
    IsoLanguageEntry("pt", "Portuguese", "Portugues"),
    IsoLanguageEntry("nl", "Dutch", "Nederlands"),
    IsoLanguageEntry("ru", "Russian", "Russkiy"),
    IsoLanguageEntry("ar", "Arabic", "Al-Arabiyyah"),
    IsoLanguageEntry("hi", "Hindi", "Hindi"),
    IsoLanguageEntry("tl", "Tagalog", "Tagalog"),
    IsoLanguageEntry("tr", "Turkish", "Turkce"),
    IsoLanguageEntry("pl", "Polish", "Polski"),
    IsoLanguageEntry("uk", "Ukrainian", "Ukrayinska"),
    IsoLanguageEntry("ro", "Romanian", "Romana"),
    IsoLanguageEntry("cs", "Czech", "Cestina"),
    IsoLanguageEntry("el", "Greek", "Ellinika"),
    IsoLanguageEntry("he", "Hebrew", "Ivrit"),
    IsoLanguageEntry("fa", "Persian", "Farsi"),
    IsoLanguageEntry("ur", "Urdu", "Urdu"),
    IsoLanguageEntry("bn", "Bengali", "Bangla"),
    IsoLanguageEntry("ta", "Tamil", "Tamil"),
    IsoLanguageEntry("te", "Telugu", "Telugu"),
    IsoLanguageEntry("sv", "Swedish", "Svenska"),
    IsoLanguageEntry("no", "Norwegian", "Norsk"),
    IsoLanguageEntry("da", "Danish", "Dansk"),
    IsoLanguageEntry("fi", "Finnish", "Suomi"),
    IsoLanguageEntry("hu", "Hungarian", "Magyar"),
    IsoLanguageEntry("bg", "Bulgarian", "Balgarski"),
    IsoLanguageEntry("hr", "Croatian", "Hrvatski"),
    IsoLanguageEntry("sk", "Slovak", "Slovencina"),
    IsoLanguageEntry("sl", "Slovenian", "Slovenscina"),
    IsoLanguageEntry("sw", "Swahili", "Kiswahili"),
]
