"""Catalog and classifier invariants. No database required."""

from ainews.catalog import KEYWORDS, SOURCES, TOPICS, classify


def test_every_topic_has_keyword_rules():
    assert {t.slug for t in TOPICS} == set(KEYWORDS)


def test_source_slugs_and_feeds_are_unique():
    assert len({s.slug for s in SOURCES}) == len(SOURCES)
    assert len({s.feed_url for s in SOURCES}) == len(SOURCES)


def test_source_topics_reference_real_topics():
    known = {t.slug for t in TOPICS}
    for s in SOURCES:
        assert set(s.topics) <= known, s.slug


def test_topical_sources_declare_topics_and_broad_do_not():
    for s in SOURCES:
        if s.kind == "topical":
            assert s.topics, f"{s.slug} is topical but declares no topic"
        else:
            assert not s.topics, f"{s.slug} is broad; topics come from the classifier"


def test_kinds_and_tiers_are_valid():
    for s in SOURCES:
        assert s.kind in {"broad", "topical"}
        assert s.quality_tier in {1, 2, 3}


def test_classifier_returns_at_most_three_topics():
    noisy = ("GPU robot agent regulation funding healthcare electricity "
            "alignment copilot benchmark nvidia lawsuit")
    assert len(classify(noisy, None)) <= 3


def test_classifier_picks_the_obvious_topic():
    assert "robotics" in dict(classify("Humanoid robot learns manipulation", None))
    assert "power" in dict(classify("Datacenter electricity demand strains the power grid", None))
    assert "policy" in dict(classify("State attorney general sues over AI regulation", None))


def test_classifier_is_quiet_on_unrelated_text():
    assert classify("A recipe for sourdough bread", None) == []
