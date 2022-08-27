class InvalidRequestError(Exception):
    """Incorrect request parameters being blocked."""
    def __init__(self, reson: str, value):
        self.reason = reson
        self.value = value
        self.msg = "Request blocked: invalid request parameter {reason}: {value}"
    
    def __str__(self):
        return self.msg.format(reason=self.reason, value=self.value)