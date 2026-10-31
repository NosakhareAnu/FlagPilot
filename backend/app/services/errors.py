class DomainError(Exception):
    """Base class for expected errors mapped to HTTP responses by the API layer."""

    status_code = 400
    code = "bad_request"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"


class UnprocessableError(DomainError):
    status_code = 422
    code = "invalid_configuration"
