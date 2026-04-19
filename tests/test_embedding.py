from unittest.mock import MagicMock

import numpy as np
import pytest

from fillnel.services.embedding import cosine_similarity, score_articles


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


class TestScoreArticles:
    def _make_client(self, vec=None):
        client = MagicMock()
        client.embed_text.return_value = vec or [1.0, 0.0, 0.0]
        return client

    def test_returns_articles_unchanged_when_no_profile_vector(self):
        articles = [{"title": "A", "url": "https://a.com", "excerpt": ""}]
        client = self._make_client()
        result = score_articles(articles, None, client)
        assert result == articles
        client.embed_text.assert_not_called()

    def test_returns_articles_unchanged_when_profile_vector_empty(self):
        articles = [{"title": "A", "url": "https://a.com", "excerpt": ""}]
        client = self._make_client()
        result = score_articles(articles, [], client)
        assert result == articles
        client.embed_text.assert_not_called()

    def test_attaches_score_to_articles(self):
        articles = [{"title": "A", "url": "https://a.com", "excerpt": ""}]
        profile_vector = [1.0, 0.0, 0.0]
        client = self._make_client([1.0, 0.0, 0.0])
        result = score_articles(articles, profile_vector, client)
        assert "_score" in result[0]
        assert isinstance(result[0]["_score"], float)

    def test_sorts_by_score_descending(self):
        articles = [
            {"title": "low", "url": "https://low.com", "excerpt": ""},
            {"title": "high", "url": "https://high.com", "excerpt": ""},
        ]
        profile_vector = [1.0, 0.0]
        client = MagicMock()
        client.embed_text.side_effect = lambda text: [1.0, 0.0] if "high" in text else [0.0, 1.0]

        result = score_articles(articles, profile_vector, client)
        assert result[0]["title"] == "high"
        assert result[1]["title"] == "low"
