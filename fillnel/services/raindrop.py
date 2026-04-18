from abc import ABC, abstractmethod
import json
import os
import requests


UNSORTED_COLLECTION_ID = -1


class BookmarkClient(ABC):
    @abstractmethod
    def get_tags(self) -> list[str]: ...

    @abstractmethod
    def get_bookmarks(self, collection_id: int | None = None, tag: str | None = None, not_tag: str | None = None) -> list[dict]: ...

    @abstractmethod
    def create_bookmark(self, bookmark: dict) -> None: ...

    @abstractmethod
    def update_bookmark(self, id: str, patch: dict) -> None: ...

    @abstractmethod
    def delete_bookmark(self, id: str) -> None: ...


class RaindropClient(BookmarkClient):
    BASE_URL = "https://api.raindrop.io/rest/v1"

    def __init__(self, token: str):
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {token}"})

    def get_tags(self) -> list[str]:
        resp = self._session.get(f"{self.BASE_URL}/tags")
        resp.raise_for_status()
        data = resp.json()
        return [item["_id"] for item in data.get("items", [])]

    def get_bookmarks(self, collection_id: int | None = None, tag: str | None = None, not_tag: str | None = None) -> list[dict]:
        results = []
        page = 0
        per_page = 50
        col = collection_id if collection_id is not None else 0

        search_filters = []
        if tag:
            search_filters.append({"key": "tag", "val": tag})
        if not_tag:
            search_filters.append({"key": "notTag", "val": not_tag})

        params: dict = {"perpage": per_page}
        if search_filters:
            params["search"] = json.dumps(search_filters)

        while True:
            params["page"] = page
            resp = self._session.get(f"{self.BASE_URL}/raindrops/{col}", params=params)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            results.extend(items)
            if len(items) < per_page:
                break
            page += 1

        return results

    def create_bookmark(self, bookmark: dict) -> None:
        resp = self._session.post(f"{self.BASE_URL}/raindrop", json=bookmark)
        if resp.status_code == 400:
            body = resp.json()
            if body.get("errorMessage") == "url_already_exists":
                return
        resp.raise_for_status()

    def update_bookmark(self, id: str, patch: dict) -> None:
        resp = self._session.put(f"{self.BASE_URL}/raindrop/{id}", json=patch)
        resp.raise_for_status()

    def delete_bookmark(self, id: str) -> None:
        resp = self._session.delete(f"{self.BASE_URL}/raindrop/{id}")
        resp.raise_for_status()

    def delete_bookmarks(self, ids: list[int]) -> None:
        if not ids:
            return
        for id in ids:
            self._session.delete(f"{self.BASE_URL}/raindrop/{id}").raise_for_status()


def create_raindrop_client() -> RaindropClient:
    token = os.environ["RAINDROP_TOKEN"]
    return RaindropClient(token)
