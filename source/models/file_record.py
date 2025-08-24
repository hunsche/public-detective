from pydantic import BaseModel


class FileRecord(BaseModel):
    """Represents the metadata of a single file discovered within a procurement's
    document collection, including files nested inside ZIP archives.

    Attributes:
        procurement_control_number: The unique identifier of the parent procurement.
        root_document_sequence: The sequence number of the original file
                                downloaded from the PNCP API.
        file_path: The full path of the file within its original archive,
                   including its name.
        file_name: The base name of the file.
        file_extension: The file's extension (e.g., 'pdf', 'zip', 'xlsx').
        nesting_level: The depth of the file within the ZIP structure (0 for root).
        file_size: The size of the file in bytes.
    """

    procurement_control_number: str
    root_document_sequence: int
    file_path: str
    file_name: str
    file_extension: str | None = None
    nesting_level: int
    file_size: int
    root_document_type: str
    root_document_is_active: bool
