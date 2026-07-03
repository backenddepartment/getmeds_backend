import time

from fastapi import APIRouter, HTTPException, Request, Response

from app.data.sanity_queries import SANITY_QUERIES
from app.services.sanity_service import sanity_service

router = APIRouter()

# Best-effort caching/rate-limiting. Note: on serverless (Vercel), each cold
# start gets fresh memory and concurrent invocations don't share this dict, so
# this is a supplementary layer only — it reduces duplicate origin hits within
# a warm instance and adds a Cache-Control header the CDN can honor, but it is
# NOT a substitute for edge-level bot management / rate limiting.
_CACHE_TTL_SECONDS = 30
_cache: dict[str, tuple[float, object]] = {}

_RATE_LIMIT_MAX_REQUESTS = 120
_RATE_LIMIT_WINDOW_SECONDS = 60
_rate_state: dict[str, list[float]] = {}


def _enforce_rate_limit(client_ip: str) -> None:
    now = time.time()
    window_start = now - _RATE_LIMIT_WINDOW_SECONDS
    hits = [t for t in _rate_state.get(client_ip, []) if t > window_start]
    if len(hits) >= _RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(status_code=429, detail="Too many requests, slow down.")
    hits.append(now)
    _rate_state[client_ip] = hits


def _cache_key(name: str, raw_params: dict) -> str:
    return name + "|" + "&".join(f"{k}={raw_params[k]}" for k in sorted(raw_params))


@router.get("/sanity/{name}")
async def run_named_sanity_query(name: str, request: Request, response: Response):
    """
    Executes one of a fixed, server-defined GROQ queries against Sanity.

    The browser only ever sees a query *name* here — never the Sanity project
    ID/dataset or the raw GROQ text — and `name` must match an entry in
    SANITY_QUERIES, so arbitrary client-supplied GROQ can never be executed.
    """
    client_ip = request.client.host if request.client else "unknown"
    _enforce_rate_limit(client_ip)

    entry = SANITY_QUERIES.get(name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Unknown query: {name}")

    raw_params = dict(request.query_params)
    array_params = entry.get("array_params", [])

    groq_params = {}
    for key, value in raw_params.items():
        groq_params[f"${key}"] = value.split(",") if key in array_params else value

    cache_key = _cache_key(name, raw_params)
    cached = _cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _CACHE_TTL_SECONDS:
        result = cached[1]
    else:
        result = await sanity_service.query_sanity(entry["query"], groq_params)
        _cache[cache_key] = (time.time(), result)

    response.headers["Cache-Control"] = "public, max-age=15, s-maxage=60, stale-while-revalidate=300"
    return {"result": result}
