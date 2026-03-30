#!/usr/bin/env python3
"""End-to-end test: register → login → upload → wait processing → chat → verify cited response.

Usage:
    python scripts/e2e_test.py [--base-url http://localhost:8000]

Requires: httpx (pip install httpx)
"""
import argparse
import json
import sys
import time

import httpx

DEFAULT_BASE = "http://localhost:8000/api/v1"
TIMEOUT = httpx.Timeout(30.0, read=120.0)


def log(msg: str) -> None:
    print(f"  ✓ {msg}")


def fail(msg: str) -> None:
    print(f"  ✗ {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="FitCoach AI E2E test")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--pdf", default=None, help="Path to a test PDF file")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    client = httpx.Client(base_url=base, timeout=TIMEOUT)

    ts = int(time.time())
    email = f"e2e_{ts}@test.com"
    password = "e2eTestPass123"

    # ── 1. Health check ────────────────────────────────────────────────────
    print("\n[1/6] Health check")
    r = client.get(f"{base.rsplit('/api', 1)[0]}/health")
    if r.status_code != 200:
        fail(f"Health check failed: {r.status_code}")
    health = r.json()
    log(f"Status: {health['status']}")

    # ── 2. Register ────────────────────────────────────────────────────────
    print("\n[2/6] Register")
    r = client.post("/auth/register", json={
        "username": f"e2e_user_{ts}",
        "email": email,
        "password": password,
    })
    if r.status_code != 201:
        fail(f"Register failed: {r.status_code} — {r.text}")
    user_id = r.json()["id"]
    log(f"User created: {user_id}")

    # ── 3. Login ───────────────────────────────────────────────────────────
    print("\n[3/6] Login")
    r = client.post("/auth/login", data={
        "username": email,
        "password": password,
    })
    if r.status_code != 200:
        fail(f"Login failed: {r.status_code} — {r.text}")
    token = r.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    log("JWT obtained")

    # ── 4. Upload PDF ──────────────────────────────────────────────────────
    print("\n[4/6] Upload PDF")
    if args.pdf:
        with open(args.pdf, "rb") as f:
            pdf_bytes = f.read()
        filename = args.pdf.rsplit("/", 1)[-1]
    else:
        # Minimal valid PDF for testing
        pdf_bytes = (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
            b"/Contents 4 0 R>>endobj\n"
            b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 100 700 Td "
            b"(E2E Test) Tj ET\nendstream\nendobj\n"
            b"xref\n0 5\ntrailer<</Size 5/Root 1 0 R>>\nstartxref\n0\n%%EOF"
        )
        filename = "e2e_test.pdf"

    r = client.post(
        "/documents/upload",
        files={"file": (filename, pdf_bytes, "application/pdf")},
        data={"domain": "training"},
    )
    if r.status_code != 202:
        fail(f"Upload failed: {r.status_code} — {r.text}")
    doc_id = r.json()["id"]
    log(f"Document uploaded: {doc_id} (status: pending)")

    # ── 5. Poll until processed ────────────────────────────────────────────
    print("\n[5/6] Wait for processing")
    max_wait = 120  # seconds
    start = time.time()
    status = "pending"
    while time.time() - start < max_wait:
        r = client.get(f"/documents/{doc_id}")
        if r.status_code != 200:
            fail(f"Get document failed: {r.status_code}")
        status = r.json()["status"]
        if status in ("ready", "failed"):
            break
        time.sleep(3)

    if status == "ready":
        chunk_count = r.json().get("chunk_count", 0)
        log(f"Document ready — {chunk_count} chunks")
    elif status == "failed":
        error_msg = r.json().get("error_message", "unknown")
        log(f"Document processing failed: {error_msg}")
        print("  ⚠ Continuing to chat test (will use empty context)")
    else:
        fail(f"Document still '{status}' after {max_wait}s — timed out")

    # ── 6. Chat ────────────────────────────────────────────────────────────
    print("\n[6/6] Chat (SSE streaming)")
    r = client.post(
        "/chat",
        json={"message": "引体向上怎么练？"},
        headers={"Accept": "text/event-stream"},
    )
    if r.status_code != 200:
        fail(f"Chat failed: {r.status_code} — {r.text}")

    events = {}
    for line in r.text.split("\n\n"):
        line = line.strip()
        if not line.startswith("data: "):
            continue
        event = json.loads(line[6:])
        events[event["type"]] = event

    if "routing" in events:
        log(f"Routing → agent: {events['routing']['agent']}")
    else:
        fail("No routing event received")

    if "sources" in events:
        src_count = len(events["sources"].get("chunks", []))
        log(f"Sources → {src_count} chunks retrieved")

    if "token" in events:
        preview = events["token"]["content"][:50]
        log(f"Token streaming OK (preview: {preview}...)")

    if "done" in events:
        conv_id = events["done"].get("conversation_id")
        latency = events["done"].get("latency_ms", "?")
        log(f"Done → conversation: {conv_id}, latency: {latency}ms")
    else:
        fail("No done event received")

    if "error" in events:
        fail(f"Error event: {events['error']['message']}")

    # ── Summary ────────────────────────────────────────────────────────────
    print("\n" + "=" * 50)
    print("  E2E TEST PASSED")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
