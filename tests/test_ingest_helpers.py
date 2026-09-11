"""URL normalisation — the basis of article de-duplication."""

from ainews.ingest import normalize_url, url_hash


def test_tracking_params_are_stripped():
    assert normalize_url("https://e.com/a?utm_source=x&id=5") == "https://e.com/a?id=5"


def test_fragments_are_dropped_and_host_lowercased():
    assert normalize_url("https://E.com/a#section") == "https://e.com/a"


def test_same_article_hashes_identically():
    a = "https://e.com/post?id=5&utm_campaign=news"
    b = "https://e.com/post?id=5"
    assert url_hash(a) == url_hash(b)


def test_different_articles_differ():
    assert url_hash("https://e.com/a") != url_hash("https://e.com/b")


def test_path_case_is_preserved():
    # Many CMSes serve case-sensitive slugs; collapsing them would merge articles.
    assert normalize_url("https://e.com/Post") != normalize_url("https://e.com/post")
