
import gettext
from pathlib import Path

import markdown

from .typings import AddonInfo



def md2html(
		source: str | Path,
		dest: str | Path,
		*,
		moFile: str | Path|None,
		mdExtensions: list[str],
		addon_info: AddonInfo
	):
	if isinstance(source, str):
		source = Path(source)
	if isinstance(dest, str):
		dest = Path(dest)
	if isinstance(moFile, str):
		moFile = Path(moFile)

	try:
		with moFile.open("rb") as f:
			_ = gettext.GNUTranslations(f).gettext
	except Exception:
		summary = addon_info["addon_summary"]
	else:
		summary = _(addon_info["addon_summary"])
	version = addon_info["addon_version"]
	title = f"{summary} {version}"
	lang = source.parent.name.replace("_", "-")
	headerDic = {
		'[[!meta title="': "# ",
		'"]]': " #",
	}
	with source.open("r", encoding="utf-8") as f:
		mdText = f.read()
	for k, v in headerDic.items():
		mdText = mdText.replace(k, v, 1)
	htmlText = markdown.markdown(mdText, extensions=mdExtensions)
	# Optimization: build resulting HTML text in one go instead of writing parts separately.
	docText = "\n".join(
		(
			"<!DOCTYPE html>",
			f'<html lang="{lang}">',
			"<head>",
			'<meta charset="UTF-8">',
			'<meta name="viewport" content="width=device-width, initial-scale=1.0">',
			'<link rel="stylesheet" type="text/css" href="../style.css" media="screen">',
			f"<title>{title}</title>",
			"</head>\n<body>",
			htmlText,
			"</body>\n</html>",
		)
	)
	with dest.open("w", encoding="utf-8") as f:
		f.write(docText) # type: ignore
