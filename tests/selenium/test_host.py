"""The host's own headers, on a server that applies site/public/_headers (the deployed site, or
`npx wrangler dev` on the build): the security headers on every page, open CORS on the data
files, security.txt served as plain text, and no Content Security Policy violation on any page, nor on
Explore after changing options.
Skipped without `--base-url`: the test process's own server sends none of these headers."""

import re
import urllib.request

import pytest
from helpers import SITE, default_slug, sitemap_paths


def _rules() -> dict[str, dict[str, str]]:
    """site/public/_headers: each path pattern with its headers."""
    rules, current = {}, None
    for line in (SITE / "public" / "_headers").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            current = rules.setdefault(line.strip(), {})
        else:
            name, value = line.strip().split(":", 1)
            current[name.strip().lower()] = value.strip()
    return rules


def _headers(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return {k.lower(): v for k, v in r.headers.items()}


def _csp_violations(site):
    return [e["message"] for e in site.console() if "Content Security Policy" in e["message"]]


@pytest.mark.host
@pytest.mark.smoke
@pytest.mark.parametrize("path", ["/en/", "/en/gr/inflation-by-group/explore/", "/en/data/gr/"])
def test_pages_carry_the_security_headers(host_url, path):
    """SEL-HOST-001: pages carry the security headers

    Given a page served by a host that applies the site's headers file
    When it is fetched
    Then every header the file sets for all pages comes back with the file's value
    """
    got = _headers(host_url + path)
    for name, value in _rules()["/*"].items():
        assert got.get(name) == value, f"{path}: {name} is {got.get(name)!r}"


@pytest.mark.host
@pytest.mark.smoke
def test_data_files_are_open_to_other_sites(host_url):
    """SEL-HOST-002: data files are open to other sites

    Given the default setting's series file, served by the host
    When it is fetched
    Then any site may read it (open CORS)
    And the browser is told not to guess its type
    """
    got = _headers(f"{host_url}/data/v1/gr/m1/latest/series/{default_slug()}.json")
    assert got.get("access-control-allow-origin") == "*"
    assert got.get("x-content-type-options") == "nosniff"


@pytest.mark.host
@pytest.mark.smoke
def test_security_txt_is_served_as_plain_text(host_url):
    """SEL-HOST-005: security.txt is served as plain text

    Given a host that serves the site
    When /.well-known/security.txt is fetched
    Then it is served as plain text
    And it is the repository's file, byte for byte
    """
    with urllib.request.urlopen(f"{host_url}/.well-known/security.txt", timeout=30) as r:
        assert r.headers.get("content-type", "").startswith("text/plain")
        body = r.read()
    assert body == (SITE / "public" / ".well-known" / "security.txt").read_bytes()


@pytest.mark.host
@pytest.mark.smoke
@pytest.mark.parametrize("path", sitemap_paths())
def test_no_policy_violation(host_url, site, path):
    """SEL-HOST-003: no page breaks the Content Security Policy

    Given a page the sitemap lists, served by the host
    When it opens in the browser
    Then the console reports no Content Security Policy violation
    """
    site.open(path)
    assert not _csp_violations(site), "\n".join(_csp_violations(site))


@pytest.mark.host
@pytest.mark.smoke
def test_no_policy_violation_on_explore_after_changes(host_url, site):
    """SEL-HOST-004: Explore breaks no policy after changes

    Given Explore, served by the host
    When renters are added, the breakdown view is shown and then the view over time
    And the data table is unfolded
    Then the address carries the groups
    And the console reports no Content Security Policy violation
    """
    site.open("/en/gr/inflation-by-group/explore/")
    site.visible("#explore [data-role=summary]")
    site.find('#explore button.chip[data-group="tenure/renter"]').click()
    site.find('#explore [data-view="parts"]').click()
    site.visible("#explore [data-role=view-parts]")
    site.find('#explore [data-view="time"]').click()
    site.find("#explore [data-role=table-fold] summary").click()
    site.visible("#explore [data-role=table] table")
    assert re.search(r"groups=", site.driver.current_url)
    assert not _csp_violations(site), "\n".join(_csp_violations(site))
