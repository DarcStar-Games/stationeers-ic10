"""Reference semantics for ASYNC_REQUEST_V1."""
from dataclasses import dataclass

@dataclass
class Publication:
    token:int=0
    state:int=0
    error:int=0

def accept(request_token:int, initial_state:int=2)->Publication:
    """LIVE_CURRENT acceptance: reset state/error, then make token authoritative."""
    return Publication(request_token, initial_state, 0)

def consume(expected_token:int, publication:Publication):
    """Return request-specific state only after exact identity match."""
    return None if publication.token!=expected_token else (publication.state,publication.error)

def terminal(request_token:int, state:int, error:int=0)->Publication:
    """TERMINAL_RESPONSE model: result fields precede the response token."""
    return Publication(request_token,state,error)

def consume_terminal(expected_token:int, publication:Publication):
    return consume(expected_token,publication)
