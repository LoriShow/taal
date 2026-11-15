"""Supabase over plain HTTP, with the service key. Worker only."""

from __future__ import annotations

import os

import httpx


class Db:
    def __init__(self) -> None:
        self.url = os.environ["SUPABASE_URL"].rstrip("/")
        key = os.environ["SUPABASE_SERVICE_KEY"]
        self.http = httpx.Client(
            headers={"apikey": key, "Authorization": f"Bearer {key}"}, timeout=60.0
        )

    def _check(self, r: httpx.Response) -> httpx.Response:
        if r.status_code >= 400:
            raise RuntimeError(f"Supabase {r.status_code}: {r.text[:500]}")
        return r

    def claim_job(self) -> dict | None:
        r = self._check(self.http.post(f"{self.url}/rest/v1/rpc/taal_claim_job", json={}))
        rows = r.json()
        return rows[0] if rows else None

    def get(self, table: str, row_id: str) -> dict | None:
        r = self._check(
            self.http.get(f"{self.url}/rest/v1/{table}", params={"id": f"eq.{row_id}"})
        )
        rows = r.json()
        return rows[0] if rows else None

    def update(self, table: str, row_id: str, values: dict) -> None:
        self._check(
            self.http.patch(
                f"{self.url}/rest/v1/{table}", params={"id": f"eq.{row_id}"}, json=values
            )
        )

    def insert(self, table: str, values: dict) -> None:
        self._check(self.http.post(f"{self.url}/rest/v1/{table}", json=values))

    def upload(self, path: str, data: bytes, content_type: str) -> str:
        """Put a file in the private 'taal' bucket. Returns the stored path."""
        self._check(
            self.http.post(
                f"{self.url}/storage/v1/object/taal/{path}",
                content=data,
                headers={"Content-Type": content_type, "x-upsert": "true"},
            )
        )
        return path
