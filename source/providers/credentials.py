import os
import tempfile


def setup_google_credentials():
    """
    Sets up Google credentials from a JSON string in an environment variable.

    This function checks for the `GOOGLE_APPLICATION_CREDENTIALS_JSON`
    environment variable. If found, it writes the JSON content to a
    temporary file and sets the `GOOGLE_APPLICATION_CREDENTIALS`
    environment variable to the path of this file.
    """
    credentials_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if credentials_json:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as temp_file:
            temp_file.write(credentials_json.encode("utf-8"))
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_file.name
