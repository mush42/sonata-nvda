from typing import TypedDict, Protocol



class AddonInfo(TypedDict):
	addon_name: str
	addon_summary: str
	addon_description: str
	addon_version: str
	addon_changelog: str
	addon_author: str
	addon_url: str | None
	addon_sourceURL: str | None
	addon_docFileName: str
	addon_minimumNVDAVersion: str | None
	addon_lastTestedNVDAVersion: str | None
	addon_updateChannel: str | None
	addon_license: str | None
	addon_licenseURL: str | None


class BrailleTableAttributes(TypedDict):
    displayName: str
    contracted: bool
    output: bool
    input: bool


class SymbolDictionaryAttributes(TypedDict):
    displayName: str
    mandatory: bool


BrailleTables = dict[str, BrailleTableAttributes]
SymbolDictionaries = dict[str, SymbolDictionaryAttributes]


class Strable(Protocol):
	def __str__(self) -> str: ...
