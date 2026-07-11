class DocumindError(Exception):
    """Base class for domain errors raised by the service."""


class DocumentNotFoundError(DocumindError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Document '{name}' not found")
        self.name = name


class DocumentNameConflictError(DocumindError):
    def __init__(self, name: str) -> None:
        super().__init__(f"An active document named '{name}' already exists")
        self.name = name


class InvalidDocumentError(DocumindError):
    """The uploaded file is not a supported or readable document."""


class EmptyDocumentError(InvalidDocumentError):
    def __init__(self) -> None:
        super().__init__("No extractable text was found in the document")
