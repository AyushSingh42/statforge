import pytest

from statforge.ingest.sources import SOURCES, UnknownSourceError, get_source
from statforge.ingest.sources.template import TemplateSource


def test_fixture_source_is_registered_and_filters_by_season():
    source = get_source("fixture")
    rows = list(source.fetch([2019]))
    assert rows
    assert {row["season"] for row in rows} == {"2019"}


def test_unknown_source_lists_known_names():
    with pytest.raises(UnknownSourceError, match="fixture"):
        get_source("does-not-exist")


def test_template_is_not_registered_and_fails_loudly():
    assert "template" not in SOURCES
    with pytest.raises(NotImplementedError):
        list(TemplateSource().fetch([2020]))
