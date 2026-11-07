"""Reading the settings file, and the capped DuckDB connections the store opens."""

import pytest

from traceconomics import config
from traceconomics.config import ConfigError, load, parse
from traceconomics.store.db import connect

pytestmark = pytest.mark.unit

MINIMAL = '[archive]\ndir = "archive"\n[fetch]\nuser_agent = "test"\n'


def test_every_setting_is_read_from_the_file(tmp_path):
    """PY-CONF-001: every setting in the file is read, with paths relative to the file

    Given a settings file with the archive, fetch, schedule, store, email and release sections all filled in
    When it is loaded
    Then relative paths are taken from the file's folder and "~" from the home folder
    And the run time, pause, extra release dates, image, store limits and thread count are read
    And the email settings default the sender to the user name
    And the release settings strip a trailing slash from the public address
    """
    (tmp_path / "config.toml").write_text(MINIMAL.replace("[fetch]", '[schedule]\nrun_after = "14:30"\n'
                                                          'extra_release_dates = ["2026-12-01"]\nimage = "img:1"\n[fetch]')
                                          + 'pause_seconds = 5\n[store]\ndir = "~/store"\nmemory_limit = "4GB"\nthreads = 2\n'
                                          '[email]\nsmtp_host = "smtp.example"\nsmtp_port = "465"\nusername = "bot"\n'
                                          'recipients = ["a@example"]\nsecurity = "ssl"\n'
                                          '[release]\nenabled = true\nsite_dir = "site"\nproduction_url = "https://x.example/"\n'
                                          'keep = 3\nreplicates = 10\n', encoding="utf-8")
    c = load(tmp_path / "config.toml")
    assert c.archive_dir == tmp_path / "archive" and c.store_dir.name == "store" and c.store_dir.is_absolute()
    assert c.run_after.strftime("%H:%M") == "14:30" and c.request_pause_seconds == 5.0
    assert [d.isoformat() for d in c.extra_release_dates] == ["2026-12-01"] and c.image == "img:1"
    assert (c.store_memory_limit, c.store_threads) == ("4GB", 2)
    assert (c.email.smtp_port, c.email.sender, c.email.recipients, c.email.security) == (465, "bot", ("a@example",), "ssl")
    r = c.release
    assert r.enabled and r.site_dir == tmp_path / "site" and r.production_url == "https://x.example"
    assert (r.keep, r.replicates) == (3, 10)


@pytest.mark.parametrize("extra, message", [
    ('[email]\nsmtp_host = "h"\nsmtp_port = 25\nusername = "u"\nrecipients = []\nsecurity = "plain"\n',
     "email.security must be 'starttls' or 'ssl'"),
    ('[release]\nenabled = true\n', "release.site_dir is required"),
    ('[email]\nsmtp_host = "h"\n', "Missing config field: 'smtp_port'"),
])
def test_a_setting_that_cant_work_is_refused(extra, message):
    """PY-CONF-002: a settings file that can't work is refused with the reason

    Given a settings file with unencrypted email, or releases on without a site folder, or email without a port
    When it is parsed
    Then a ConfigError names the setting at fault
    """
    import tomllib
    from pathlib import Path

    with pytest.raises(ConfigError, match=message):
        parse(tomllib.loads(MINIMAL + extra), base_dir=Path("/base"))


def test_the_file_is_found_through_the_environment(tmp_path, monkeypatch):
    """PY-CONF-003: without a path, the settings file is the one TRACECONOMICS_CONFIG names

    Given a settings file whose path is in TRACECONOMICS_CONFIG
    When the settings are loaded without a path
    And TRACECONOMICS_CONFIG names a file that doesn't exist
    Then the first load reads that file
    And the second raises a ConfigError naming the missing file and the variable
    """
    (tmp_path / "c.toml").write_text(MINIMAL, encoding="utf-8")
    monkeypatch.setenv(config.CONFIG_ENV, str(tmp_path / "c.toml"))
    assert load().user_agent == "test"
    monkeypatch.setenv(config.CONFIG_ENV, str(tmp_path / "none.toml"))
    with pytest.raises(ConfigError, match=r"No config file at .*none\.toml.*TRACECONOMICS_CONFIG"):
        load()


@pytest.mark.parametrize("platform, variable, folder", [("linux", "XDG_CONFIG_HOME", "xdg"),
                                                       ("win32", "APPDATA", "appdata")])
def test_the_default_settings_file_is_in_the_platforms_config_folder(tmp_path, monkeypatch, platform, variable, folder):
    """PY-CONF-004: the default settings file is in the platform's own config folder

    Given Linux with XDG_CONFIG_HOME set, or Windows with APPDATA set
    When the default settings path is asked for
    Then it is traceconomics/config.toml in that folder
    """
    monkeypatch.setattr(config.sys, "platform", platform)
    monkeypatch.setenv(variable, str(tmp_path / folder))
    assert config.default_config_path() == tmp_path / folder / "traceconomics" / "config.toml"


@pytest.mark.parametrize("threads", [None, 2])
def test_store_connections_are_capped(threads):
    """PY-CONF-005: every store connection is capped in memory, and in threads when asked

    Given a memory limit of 1 GB, with and without a thread count of 2
    When a store connection is opened
    Then its memory limit is 1 GB, which DuckDB shows as 953.6 MiB
    And with a thread count it uses that many threads
    And the progress bar is off (a scheduled run has no console)
    """
    con = connect("1GB", threads)
    limit = con.execute("SELECT current_setting('memory_limit')").fetchone()[0]
    assert limit == "953.6 MiB"          # DuckDB reports 1 GB (10^9 bytes) in binary units
    if threads:
        assert con.execute("SELECT current_setting('threads')").fetchone()[0] == 2
    assert con.execute("SELECT current_setting('enable_progress_bar')").fetchone()[0] is False
