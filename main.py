from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from collections import defaultdict, deque
from uuid import uuid4
import time
import base64


app = FastAPI()


# Assigned values
TOTAL_ORDERS = 55
RATE_LIMIT = 17
WINDOW_SECONDS = 10


# -----------------------------
# CORS
# -----------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://exam.sanand.workers.dev",
        "https://app-6baaqu.example.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# Fixed catalog 1..55
# -----------------------------

catalog = [
    {
        "id": i,
        "name": f"Order {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]


# -----------------------------
# Idempotency storage
# -----------------------------

idempotency_store = {}


# -----------------------------
# Rate limiting storage
# -----------------------------

client_requests = defaultdict(deque)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):

    client_id = request.headers.get(
        "X-Client-Id",
        "anonymous"
    )

    now = time.monotonic()

    bucket = client_requests[client_id]

    # Remove expired requests
    while bucket and now - bucket[0] >= WINDOW_SECONDS:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT:
        response = JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded"
            }
        )

        response.headers["Retry-After"] = "10"

        return response

    bucket.append(now)

    return await call_next(request)



# -----------------------------
# POST /orders
# -----------------------------

@app.post("/orders", status_code=201)
async def create_order(
    Idempotency_Key: str | None = Header(default=None)
):

    # Same key returns same order
    if Idempotency_Key:

        if Idempotency_Key in idempotency_store:
            return idempotency_store[Idempotency_Key]


    order = {
        "id": str(uuid4()),
        "status": "created"
    }


    if Idempotency_Key:
        idempotency_store[Idempotency_Key] = order


    return order



# -----------------------------
# GET /orders pagination
# -----------------------------

@app.get("/orders")
async def get_orders(
    limit: int = 10,
    cursor: str | None = None
):

    # Decode cursor
    if cursor:
        start = int(
            base64.urlsafe_b64decode(
                cursor.encode()
            ).decode()
        )
    else:
        start = 1


    # Never exceed limit
    end = min(
        start + limit - 1,
        TOTAL_ORDERS
    )


    items = catalog[start - 1:end]


    # Generate next cursor
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
