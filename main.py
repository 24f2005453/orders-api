from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from collections import defaultdict, deque
from uuid import uuid4
import time
import base64

app = FastAPI()

# ----------------------------
# Assignment values
# ----------------------------

TOTAL_ORDERS = 55
RATE_LIMIT = 17
WINDOW_SECONDS = 10

# ----------------------------
# CORS
# ----------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

# ----------------------------
# Fixed catalog
# ----------------------------

catalog = [
    {
        "id": i,
        "name": f"Order {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]

# ----------------------------
# In-memory stores
# ----------------------------

idempotency_store = {}

client_requests = defaultdict(deque)

# ----------------------------
# Rate Limiting Middleware
# ----------------------------

@app.middleware("http")
async def rate_limit(request: Request, call_next):

    client_id = request.headers.get("X-Client-Id", "anonymous")

    now = time.monotonic()

    bucket = client_requests[client_id]

    while bucket and now - bucket[0] >= WINDOW_SECONDS:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT:

        retry_after = max(
            1,
            int(WINDOW_SECONDS - (now - bucket[0])) + 1
        )

        response = JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded"
            }
        )

        response.headers["Retry-After"] = str(retry_after)

        return response

    bucket.append(now)

    return await call_next(request)

# ----------------------------
# POST /orders
# ----------------------------

@app.post("/orders")
async def create_order(
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key"
    )
):

    if idempotency_key:

        if idempotency_key in idempotency_store:

            return JSONResponse(
                status_code=201,
                content=idempotency_store[idempotency_key]
            )

    order = {
        "id": str(uuid4()),
        "status": "created"
    }

    if idempotency_key:
        idempotency_store[idempotency_key] = order

    return JSONResponse(
        status_code=201,
        content=order
    )

# ----------------------------
# GET /orders
# ----------------------------

@app.get("/orders")
async def list_orders(
    limit: int = 10,
    cursor: str | None = None
):

    limit = max(1, limit)

    if cursor:

        try:
            start = int(
                base64.urlsafe_b64decode(
                    cursor.encode()
                ).decode()
            )
        except Exception:
            start = 1

    else:
        start = 1

    end = min(start + limit - 1, TOTAL_ORDERS)

    items = catalog[start - 1:end]

    if end < TOTAL_ORDERS:

        next_cursor = base64.urlsafe_b64encode(
            str(end + 1).encode()
        ).decode()

    else:
        next_cursor = None

    return {
        "items": items,
        "next_cursor": next_cursor
    }

# ----------------------------
# Root
# ----------------------------

@app.get("/")
async def root():
    return {
        "message": "Orders API Running"
    }

# ----------------------------
# Health
# ----------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok"
    }
