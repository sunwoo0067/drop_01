from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


@dataclass(frozen=True)
class OwnerClanToken:
    access_token: str
    expires_at: datetime | None


class OwnerClanClient:
    def __init__(self, auth_url: str, api_base_url: str, graphql_url: str, access_token: str | None = None) -> None:
        self._auth_url = auth_url
        self._api_base_url = api_base_url.rstrip("/")
        self._graphql_url = graphql_url
        self._access_token = access_token

    def with_token(self, access_token: str) -> "OwnerClanClient":
        return OwnerClanClient(
            auth_url=self._auth_url,
            api_base_url=self._api_base_url,
            graphql_url=self._graphql_url,
            access_token=access_token,
        )

    def issue_token(self, username: str, password: str, user_type: str) -> OwnerClanToken:
        payload = {
            "service": "ownerclan",
            "userType": user_type,
            "username": username,
            "password": password,
        }

        timeout = httpx.Timeout(30.0, connect=10.0)
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(self._auth_url, json=payload)

        resp.raise_for_status()

        token: str | None = None
        try:
            data = resp.json()
            if isinstance(data, dict):
                token = data.get("token")
        except Exception:
            token = None

        if not token:
            token = resp.text.strip() if resp.text else None

        expires_at = datetime.now(timezone.utc) + timedelta(days=30)

        if not token:
            raise RuntimeError("오너클랜 토큰 발급 응답에 token이 없습니다")

        return OwnerClanToken(access_token=str(token), expires_at=expires_at)

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        payload: dict[str, Any] = {"query": query}
        if variables is not None:
            payload["variables"] = variables

        timeout = httpx.Timeout(60.0, connect=10.0)
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(self._graphql_url, json=payload, headers=headers)

        return resp.status_code, resp.json() if resp.content else {}

    def get(self, path: str, params: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        headers: dict[str, str] = {}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        url = f"{self._api_base_url}{path}"
        timeout = httpx.Timeout(60.0, connect=10.0)
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, params=params, headers=headers)

        return resp.status_code, resp.json() if resp.content else {}

    def post(self, path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        url = f"{self._api_base_url}{path}"
        timeout = httpx.Timeout(60.0, connect=10.0)
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload or {}, headers=headers)

        return resp.status_code, resp.json() if resp.content else {}
