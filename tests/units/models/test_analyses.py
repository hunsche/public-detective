from decimal import Decimal
from typing import Any

import pytest
from public_detective.models.analyses import RedFlag, Source


class TestSource:
    """Tests for the Source model."""

    @pytest.mark.parametrize(
        "input_value,expected",
        [
            (10.5, Decimal("10.5")),
            (10, Decimal("10")),
            ("10.50", Decimal("10.50")),
            ("100", Decimal("100")),
            (None, None),
            ("N/A", None),
            ("n/a", None),
            ("NA", None),
            ("None", None),
            ("Nenhum", None),
            ("NENHUMA", None),
            ("  n/a  ", None),
        ],
    )
    def test_parse_reference_price_valid(self, input_value: Any, expected: Decimal | None) -> None:
        """Tests parsing of valid reference prices."""
        assert Source.parse_reference_price(input_value) == expected

    def test_parse_reference_price_invalid(self) -> None:
        """Tests parsing of invalid reference prices."""
        assert Source.parse_reference_price("invalid") is None
        assert Source.parse_reference_price("10.5.5") is None


class TestRedFlag:
    """Tests for the RedFlag model."""

    @pytest.mark.parametrize(
        "input_value,expected",
        [
            (1000.50, Decimal("1000.50")),
            (1000, Decimal("1000")),
            ("1000.50", Decimal("1000.50")),
            ("1000", Decimal("1000")),
            (None, None),
            ("R$ 1.000,00", Decimal("1000.00")),
            ("1.000,00", Decimal("1000.00")),
            ("1000,00", Decimal("1000.00")),
            ("1.000", Decimal("1.000")),  # Decimal treats this as 1.0
            ("R$ 1.234.567,89", Decimal("1234567.89")),
        ],
    )
    def test_parse_potential_savings_valid(self, input_value: Any, expected: Decimal | None) -> None:
        """Tests parsing of valid potential savings."""
        assert RedFlag.parse_potential_savings(input_value) == expected

    def test_parse_potential_savings_invalid(self) -> None:
        """Tests parsing of invalid potential savings."""
        assert RedFlag.parse_potential_savings("invalid") is None
        assert RedFlag.parse_potential_savings("abc") is None
