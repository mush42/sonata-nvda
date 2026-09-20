# coding: utf-8
"""
Tests for buildVars.py — validate that the addon manifest metadata
meets NVDA Add-on Store requirements.
"""

import re
import sys
import os

# Ensure repo root is on path so buildVars is importable directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import buildVars


INFO = buildVars.addon_info


class TestVersionFormat:
    """addon_version must be major.minor.patch with integer parts."""

    def test_version_has_three_parts(self):
        parts = INFO["addon_version"].split(".")
        assert len(parts) == 3, (
            f"Version '{INFO['addon_version']}' must have 3 parts (major.minor.patch)"
        )

    def test_version_parts_are_integers(self):
        parts = INFO["addon_version"].split(".")
        for part in parts:
            assert part.isdigit(), (
                f"Version part '{part}' in '{INFO['addon_version']}' is not an integer"
            )


class TestNVDAVersionFields:
    """minimumNVDAVersion and lastTestedNVDAVersion must be strings."""

    def test_minimum_nvda_version_is_string(self):
        val = INFO["addon_minimumNVDAVersion"]
        assert isinstance(val, str), (
            f"addon_minimumNVDAVersion must be a string, got {type(val).__name__}: {val!r}"
        )

    def test_last_tested_nvda_version_is_string(self):
        val = INFO["addon_lastTestedNVDAVersion"]
        assert isinstance(val, str), (
            f"addon_lastTestedNVDAVersion must be a string, got {type(val).__name__}: {val!r}"
        )

    def test_minimum_nvda_version_format(self):
        val = INFO["addon_minimumNVDAVersion"]
        parts = val.split(".")
        assert len(parts) >= 2, f"NVDA version '{val}' must have at least major.minor"
        for part in parts:
            assert part.isdigit(), f"NVDA version part '{part}' must be an integer"

    def test_last_tested_not_older_than_minimum(self):
        min_v = tuple(int(p) for p in INFO["addon_minimumNVDAVersion"].split("."))
        last_v = tuple(int(p) for p in INFO["addon_lastTestedNVDAVersion"].split("."))
        assert last_v >= min_v, (
            f"lastTestedNVDAVersion {last_v} must be >= minimumNVDAVersion {min_v}"
        )


class TestRequiredFields:
    """All fields required by the NVDA Add-on Store must be present and non-empty."""

    REQUIRED = [
        "addon_name",
        "addon_summary",
        "addon_description",
        "addon_version",
        "addon_author",
        "addon_url",
        "addon_sourceURL",
        "addon_minimumNVDAVersion",
        "addon_lastTestedNVDAVersion",
        "addon_license",
        "addon_licenseURL",
    ]

    def test_all_required_fields_present(self):
        missing = [f for f in self.REQUIRED if f not in INFO]
        assert not missing, f"Missing required fields: {missing}"

    def test_no_required_field_is_none(self):
        none_fields = [f for f in self.REQUIRED if INFO.get(f) is None]
        assert not none_fields, f"Required fields must not be None: {none_fields}"

    def test_no_required_field_is_empty_string(self):
        empty = [f for f in self.REQUIRED if INFO.get(f) == ""]
        assert not empty, f"Required fields must not be empty string: {empty}"


class TestURLFields:
    """URL fields must look like valid https URLs."""

    URL_FIELDS = ["addon_url", "addon_sourceURL", "addon_licenseURL"]

    def test_urls_start_with_https(self):
        for field in self.URL_FIELDS:
            url = INFO.get(field)
            if url is not None:
                assert url.startswith("https://"), (
                    f"'{field}' must start with https://, got: {url!r}"
                )

    def test_urls_have_domain(self):
        url_re = re.compile(r"^https://[a-zA-Z0-9.-]+(/.*)?$")
        for field in self.URL_FIELDS:
            url = INFO.get(field)
            if url is not None:
                assert url_re.match(url), f"'{field}' does not look like a valid URL: {url!r}"


class TestAddonName:
    """addon_name must be a valid Python identifier (used as directory name)."""

    def test_name_is_valid_identifier(self):
        name = INFO["addon_name"]
        assert name.isidentifier(), (
            f"addon_name '{name}' must be a valid Python identifier"
        )

    def test_name_is_lowercase(self):
        name = INFO["addon_name"]
        assert name == name.lower(), f"addon_name '{name}' should be lowercase"


class TestAuthorFormat:
    """Author field should follow 'Name <email>' convention."""

    def test_author_contains_email(self):
        author = INFO["addon_author"]
        assert "<" in author and ">" in author, (
            f"addon_author '{author}' should contain an email in angle brackets"
        )

    def test_author_email_is_valid(self):
        author = INFO["addon_author"]
        match = re.search(r"<([^>]+)>", author)
        assert match, f"Could not extract email from addon_author: {author!r}"
        email = match.group(1)
        assert "@" in email, f"Email '{email}' in addon_author does not contain '@'"
