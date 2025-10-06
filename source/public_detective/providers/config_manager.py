"""This module provides a manager for handling .env file configurations."""

from pathlib import Path

from dotenv import dotenv_values, set_key


class ConfigManager:
    """Manages reading and writing to a .env file."""

    def __init__(self, env_file: str | Path = ".env") -> None:
        """Initializes the ConfigManager.

        Args:
            env_file: The path to the .env file.
        """
        self.env_file = Path(env_file)
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        """Ensures the .env file exists, creating it if necessary."""
        if not self.env_file.exists():
            self.env_file.touch(mode=0o600)

    def get_all(self) -> dict[str, str | None]:
        """Reads all key-value pairs from the .env file.

        Returns:
            A dictionary of all key-value pairs.
        """
        return dotenv_values(self.env_file)

    def get(self, key: str) -> str | None:
        """Gets the value of a single key from the .env file.

        Args:
            key: The key to retrieve.

        Returns:
            The value of the key, or None if it doesn't exist.
        """
        return self.get_all().get(key)

    def set(self, key: str, value: str) -> None:
        """Sets a key-value pair in the .env file.

        Args:
            key: The key to set.
            value: The value to set.
        """
        set_key(self.env_file, key, value)

    def unset(self, key: str) -> None:
        """Removes a key from the .env file.

        Args:
            key: The key to remove.
        """
        lines = self.env_file.read_text().splitlines()
        new_lines = [line for line in lines if not line.startswith(f"{key}=")]
        self.env_file.write_text("\n".join(new_lines) + "\n")
