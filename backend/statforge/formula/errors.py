"""Formula-wide validation errors; these are distinct from unavailable row values."""


class FormulaValidationError(ValueError):
    """A readable error with a stable code and optional 1-based character position."""

    def __init__(self, code: str, message: str, column: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.column = column

    def to_dict(self) -> dict[str, str | int | None]:
        """JSON-safe payload suitable for FastAPI's HTTPException(detail=...)."""
        return {"code": self.code, "message": self.message, "column": self.column}
