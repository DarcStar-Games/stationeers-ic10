"""Reference semantics for ASYNC_REQUEST_V1."""
from dataclasses import dataclass

# A scanning caller posts once per position under one request it serves, and a
# coherence check can restart its scan, so a position alone does not name a
# posting: the second posting for one position would carry the token the callee
# already answered, the callee would never latch it, and the caller would consume
# the earlier reply (issue #148). The token is derived from a per-request posting
# counter instead, `request * POSTING_SPAN + posting`, reset when the request is
# answered and bounded so one request's tokens never reach the next request's.
POSTING_SPAN = 512

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

def posting_token(request_token:int, posting:int, span:int=POSTING_SPAN)->int:
    """Token of the `posting`-th request a caller posts downstream while serving `request_token`.

    Postings count from 1; the span-th posting is refused, which the programs
    answer with a failed request, so the counter never carries into the token
    space of the request that follows.
    """
    if not 1<=posting<span: raise ValueError(f'posting {posting} is outside 1..{span-1}')
    return request_token*span+posting
