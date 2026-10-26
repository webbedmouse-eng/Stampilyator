"""Тесты проверки версий и обновлений."""

from __future__ import annotations

import unittest

from pdfstamp.updates import is_newer, parse_version


class UpdateTests(unittest.TestCase):
    def test_parse_version(self) -> None:
        self.assertEqual(parse_version("v1.3.1"), (1, 3, 1))
        self.assertEqual(parse_version("release 2.0.10"), (2, 0, 10))
        self.assertIsNone(parse_version("latest"))

    def test_is_newer(self) -> None:
        self.assertTrue(is_newer("1.3.2", "1.3.1"))
        self.assertFalse(is_newer("1.3.1", "1.3.1"))
        self.assertFalse(is_newer("1.3.0", "1.3.1"))
        self.assertFalse(is_newer("not-a-version", "1.3.1"))

    def test_current_version_is_semver(self) -> None:
        from pdfstamp import __version__

        self.assertIsNotNone(parse_version(__version__))


if __name__ == "__main__":
    unittest.main()
