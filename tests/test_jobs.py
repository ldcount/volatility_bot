import unittest

from bot.services.jobs import parse_rate_threshold


class ParseRateThresholdTests(unittest.TestCase):
    def test_accepts_negative_percent_with_comma(self) -> None:
        self.assertAlmostEqual(parse_rate_threshold("-1,2"), -0.012)

    def test_converts_positive_input_to_negative_threshold(self) -> None:
        self.assertAlmostEqual(parse_rate_threshold("1.5"), -0.015)

    def test_rejects_zero_or_invalid_range(self) -> None:
        with self.assertRaises(ValueError):
            parse_rate_threshold("0")

        with self.assertRaises(ValueError):
            parse_rate_threshold("-120")
