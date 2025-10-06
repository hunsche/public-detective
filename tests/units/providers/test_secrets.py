import pytest
from public_detective.providers.secrets import is_secret_key, mask_value


@pytest.mark.parametrize(
    "key, expected",
    [
        ("API_KEY", True),
        ("SECRET_TOKEN", True),
        ("MY_PASSWORD", True),
        ("REGULAR_KEY", False),
        ("something", False),
        ("GCP_SERVICE_ACCOUNT_CREDENTIALS", True),
    ],
)
def test_is_secret_key(key: str, expected: bool) -> None:
    """Tests the is_secret_key function."""
    assert is_secret_key(key) is expected


def test_mask_value() -> None:
    """Tests the mask_value function."""
    assert mask_value("1234567890") == "•••••••••••••••••••• (last 4: 7890)"
    assert mask_value("123") == "****"
    assert mask_value(None) == "Not set"
    assert mask_value("") == "****"
