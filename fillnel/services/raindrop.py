from abc import ABC, abstractmethod
import json
import os
import requests
import logging


UNSORTED_COLLECTION_ID = -1

logger = logging.getLogger(__name__)


class BookmarkClient(ABC):
    @abstractmethod
    def get_tags(self) -> list[str]: ...

    @abstractmethod
    def get_or_create_collection(self, name: str) -> int: ...

    @abstractmethod
    def get_bookmarks(self, collection_id: int | None = None, tag: str | None = None, not_tag: str | None = None) -> list[dict]: ...

    @abstractmethod
    def create_bookmark(self, bookmark: dict) -> None: ...

    @abstractmethod
    def update_bookmark(self, id: str, patch: dict) -> None: ...

    @abstractmethod
    def delete_bookmark(self, id: str) -> None: ...

    @abstractmethod
    def delete_bookmarks(self, ids: list[int]) -> None: ...


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

    def get_or_create_collection(self, name: str) -> int:
        resp = self._session.get(f"{self.BASE_URL}/collections")
        resp.raise_for_status()
        for col in resp.json().get("items", []):
            if col["title"] == name:
                return col["_id"]
        resp = self._session.post(f"{self.BASE_URL}/collection", json={"title": name})
        resp.raise_for_status()
        return resp.json()["item"]["_id"]

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
# --- Mock implementation for local testing ---------------------------------

class MockRaindropClient(BookmarkClient):
    def __init__(self):
        # prepopulate a favorite collection with dummy bookmarks
        self._bookmarks: list[dict] = [
            {
                "_id": 1,
                "title": "Mock Article 1",
                "link": "https://example.com/article1",
                "excerpt": "Mock excerpt 1",
                "tags": [],
                "collectionId": 1,
            },
            {
                "_id": 2,
                "title": "Mock Article 2",
                "link": "https://example.com/article2",
                "excerpt": "Mock excerpt 2",
                "tags": [],
                "collectionId": 1,
            },
        ]
        self._collections: dict[str, int] = {"Favorite": 1, "お気に入り": 1}
        self._next_id = 3

    def get_tags(self) -> list[str]:
        return []

    def get_or_create_collection(self, name: str) -> int:
        # Return a deterministic ID for known names
        return self._collections.setdefault(name, self._next_id)

    def get_bookmarks(self, collection_id: int | None = None, tag: str | None = None, not_tag: str | None = None) -> list[dict]:
        return [b for b in self._bookmarks if (collection_id is None or b.get("collectionId") == collection_id)]

    def create_bookmark(self, bookmark: dict) -> None:
        bookmark = bookmark.copy()
        bookmark["_id"] = self._next_id
        self._next_id += 1
        self._bookmarks.append(bookmark)

    def update_bookmark(self, id: str, patch: dict) -> None:
        for b in self._bookmarks:
            if b.get("_id") == id:
                b.update(patch)
                break

    def delete_bookmark(self, id: str) -> None:
        self._bookmarks = [b for b in self._bookmarks if b.get("_id") != id]

    def delete_bookmarks(self, ids: list[int]) -> None:
        self._bookmarks = [b for b in self._bookmarks if b.get("_id") not in ids]

# --------------------------------------------------------------------------


def create_raindrop_client() -> RaindropClient:
    token = os.getenv("RAINDROP_TOKEN", "")
    if "mock" in token.lower() or os.getenv("MOCK_MODE", "false").lower() in {"1", "true", "yes"}:
        logger.info("Raindrop mock mode enabled")
        return MockRaindropClient()
    return RaindropClient(token)
