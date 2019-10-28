"""Domain and API errors.

Every error raised deliberately by Ledgerline derives from
:class:`LedgerlineError`; the API layer renders them as::

    {"error": {"type": "...", "code": "...", "message": "...", "param": "..."}}
"""


class LedgerlineError(Exception):
    status_code = 400
    error_type = "api_error"
    default_code = None

    def __init__(self, message, param=None, code=None):
        super().__init__(message)
        self.message = message
        self.param = param
        self.code = code or self.default_code

    def to_dict(self):
        body = {"type": self.error_type, "message": self.message}
        if self.code:
            body["code"] = self.code
        if self.param:
            body["param"] = self.param
        return {"error": body}


class InvalidRequestError(LedgerlineError):
    status_code = 400
    error_type = "invalid_request_error"


class NotFoundError(InvalidRequestError):
    status_code = 404
    default_code = "resource_missing"


class AuthenticationError(LedgerlineError):
    status_code = 401
    error_type = "authentication_error"
