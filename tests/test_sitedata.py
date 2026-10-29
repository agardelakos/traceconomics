"""The made-up site data (`tests/sitedata.py`), which the site's browser tests run on: it goes
through the real export, and takes the same special paths as real baskets do."""

import json

import duckdb
import pytest

import sitedata
from traceconomics.module1 import combinations
from traceconomics.export import site


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    out = tmp_path_factory.mktemp("data")
    sitedata.generate(out, tmp_path_factory.mktemp("work"), log=lambda *a: None)
    return out / "v1" / "gr" / "m1" / "latest"


def test_every_setting_gets_its_files_and_the_shared_ones_are_there(data):
    for s in combinations.settings():
        slug = site.slug(s)
        assert (data / "series" / f"{slug}.json").is_file() and (data / "contributions" / f"{slug}.json").is_file()
    for name in ("calculator.json", "availability.json", "official.json", "settings.json", "metadata.json", "SHA256SUMS"):
        assert (data / name).is_file()
    assert (data.parents[2] / "labels" / "coicop18.json").is_file() and (data.parents[2] / "references.json").is_file()


def test_the_country_card_rates_come_from_one_index_so_they_agree(data):
    official = json.loads((data / "official.json").read_text(encoding="utf-8"))
    assert official["comparison"]["agree"] is True


def test_made_up_baskets_take_the_special_paths(data):
    con = duckdb.connect()

    def used(setting, where):
        path = (data / "downloads" / setting / "m1_weights_used.parquet").as_posix()
        return set(con.execute(f"SELECT DISTINCT coicop18, priced_with FROM '{path}' WHERE {where}").fetchall())

    # a small cell published inside "rest of" its parent; imputed rent priced with actual rents;
    # tutoring (no index of its own) priced with secondary education
    assert any(c.endswith("_REST") for c, _ in used("all_excluded_cpi_N_priced", "true"))
    assert used("purchases_included_cpi_N_priced", "coicop18 = '0421'") == {("0421", "0411")}
    assert used("purchases_excluded_cpi_N_priced", "coicop18 = '1050'") == {("1050", "1020")}
