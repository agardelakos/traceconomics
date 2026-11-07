"""Moving a local setup from the earlier project name, on a made-up home folder."""

import subprocess
import sys

import pytest

from traceconomics import migrate

pytestmark = pytest.mark.unit


class FakeKeyring:
    def __init__(self, entries):
        self.entries = dict(entries)

    def get_password(self, service, user):
        return self.entries.get((service, user))

    def set_password(self, service, user, secret):
        self.entries[(service, user)] = secret


OLD_CONFIG = """# Copy this file to %APPDATA%\\oet\\config.toml
[archive]
dir = "~/oet-archive"
[fetch]
user_agent = "open-econ-tracker/0.1 (archive of public statistics)"
# python -m keyring set oet-smtp <username>, or OET_SMTP_PASSWORD
[email]
username = "someone@example.org"
"""


def setup(tmp_path):
    home, base = tmp_path / "home", tmp_path / "appdata"
    (home / "oet-archive" / "raw").mkdir(parents=True)
    (home / "oet-archive" / "raw" / "index.jsonl").write_text("{}\n", encoding="utf-8")
    (home / "oet-store").mkdir()
    (base / "oet").mkdir(parents=True)
    (base / "oet" / "config.toml").write_text(OLD_CONFIG, encoding="utf-8")
    return home, base


def test_dry_run_changes_nothing(tmp_path):
    """PY-MIGRATE-001: a dry run changes nothing

    Given a made-up home with the earlier name's archive, store, config and keyring password
    When the migration is run as a dry run
    Then its plan includes a rename and reports no problems
    And the old archive is still there and no new one exists
    And no new config folder or keyring entry is made
    """
    home, base = setup(tmp_path)
    kr = FakeKeyring({("oet-smtp", "someone@example.org"): "secret"})
    plan = migrate.run(dry_run=True, home=home, config_base=base, keyring_module=kr, schtasks=False)
    assert any("rename" in s for s in plan.steps) and not plan.problems
    assert (home / "oet-archive").exists() and not (home / "traceconomics-archive").exists()
    assert not (base / "traceconomics").exists() and ("traceconomics-smtp", "someone@example.org") not in kr.entries


def test_run_moves_folders_writes_config_and_copies_the_password(tmp_path):
    """PY-MIGRATE-002: the migration moves the folders, writes the config and copies the password

    Given a made-up home with the earlier name's archive, store, config and keyring password
    When the migration is run
    Then it reports no problems
    And the archive (with its index) and the store are under the new names, and the old archive is gone
    And the new config points to the new archive and uses the new user agent, keyring service and password variable, with no "oet" left
    And the old config file is kept unchanged
    And the password is copied to the new keyring service
    And no step of the plan shows the password
    """
    home, base = setup(tmp_path)
    kr = FakeKeyring({("oet-smtp", "someone@example.org"): "secret"})
    plan = migrate.run(dry_run=False, home=home, config_base=base, keyring_module=kr, schtasks=False)
    assert not plan.problems
    assert (home / "traceconomics-archive" / "raw" / "index.jsonl").exists() and not (home / "oet-archive").exists()
    assert (home / "traceconomics-store").exists()
    new = (base / "traceconomics" / "config.toml").read_text(encoding="utf-8")
    assert 'dir = "~/traceconomics-archive"' in new and "Traceconomics/0.1" in new
    assert "traceconomics-smtp" in new and "TRACECONOMICS_SMTP_PASSWORD" in new and "oet" not in new
    assert (base / "oet" / "config.toml").read_text(encoding="utf-8") == OLD_CONFIG     # the old file is kept
    assert kr.entries[("traceconomics-smtp", "someone@example.org")] == "secret"
    assert all("secret" not in s for s in plan.steps)                                  # never shown


def test_a_taken_target_is_a_problem_not_a_merge(tmp_path):
    """PY-MIGRATE-003: a target folder that already exists is a problem, not a merge

    Given a made-up home where the new archive folder already exists
    When the migration is run
    Then it reports a problem
    And the old archive is left in place
    """
    home, base = setup(tmp_path)
    (home / "traceconomics-archive").mkdir()
    plan = migrate.run(dry_run=False, home=home, config_base=base, keyring_module=FakeKeyring({}), schtasks=False)
    assert plan.problems and (home / "oet-archive").exists()


def test_what_is_already_in_place_is_left_as_it_is(tmp_path):
    """PY-MIGRATE-004: what is already in place under the new name is left as it is

    Given a made-up home whose new config exists already and whose new keyring entry holds a password
    When the migration is run for real
    Then the new config keeps its own text
    And the new keyring password is not overwritten
    And the plan says both were left as they are
    """
    home, base = setup(tmp_path)
    (base / "traceconomics").mkdir()
    (base / "traceconomics" / "config.toml").write_text("# mine\n", encoding="utf-8")
    kr = FakeKeyring({("oet-smtp", "someone@example.org"): "old", ("traceconomics-smtp", "someone@example.org"): "new"})
    plan = migrate.run(dry_run=False, home=home, config_base=base, keyring_module=kr, schtasks=False)
    assert (base / "traceconomics" / "config.toml").read_text(encoding="utf-8") == "# mine\n"
    assert kr.entries[("traceconomics-smtp", "someone@example.org")] == "new"
    assert any("exists already; left as it is" in s for s in plan.steps)
    assert any("already has a password; left as it is" in s for s in plan.steps)


def test_without_an_old_password_it_says_how_to_set_one(tmp_path, monkeypatch):
    """PY-MIGRATE-005: without an old keyring password the plan says how to set the new one

    Given a made-up home whose old config names a mailbox user but no keyring holds its password
    And the system's keyring module, as installed
    When the migration is run
    Then the plan says there is no password under the old name and how to set one under the new name
    """
    home, base = setup(tmp_path)
    monkeypatch.setitem(sys.modules, "keyring", FakeKeyring({}))
    plan = migrate.run(dry_run=True, home=home, config_base=base, schtasks=False)
    assert any("no password under oet-smtp" in s and "keyring set traceconomics-smtp" in s for s in plan.steps)


def test_without_an_old_config_there_is_nothing_to_move(tmp_path):
    """PY-MIGRATE-006: without an old config or folders there is nothing to move

    Given an empty home and config folder
    When the migration is run
    Then the plan says there is no old config and no old folders, with no problems
    And no keyring is consulted
    """
    plan = migrate.run(dry_run=False, home=tmp_path / "home", config_base=tmp_path / "base",
                       keyring_module=None, schtasks=False)
    assert plan.steps[0].startswith("config: no old config") and not plan.problems
    assert all("not found; nothing to move" in s for s in plan.steps[1:])


@pytest.mark.parametrize("platform, variable, expected", [
    ("linux", "XDG_CONFIG_HOME", "xdg"), ("win32", "APPDATA", "appdata")])
def test_the_config_folder_follows_the_platform(tmp_path, monkeypatch, platform, variable, expected):
    """PY-MIGRATE-007: the config folder is the platform's own

    Given Linux with XDG_CONFIG_HOME set, or Windows with APPDATA set
    When the migration looks for the old config without being told where
    Then it looks in that folder
    """
    monkeypatch.setattr(migrate.sys, "platform", platform)
    monkeypatch.setenv(variable, str(tmp_path / expected))
    plan = migrate.run(dry_run=True, home=tmp_path, keyring_module=FakeKeyring({}), schtasks=False)
    assert str(tmp_path / expected / "oet" / "config.toml") in plan.steps[0]


@pytest.mark.parametrize("exists", [True, False])
def test_the_old_windows_task_is_removed(tmp_path, monkeypatch, exists):
    """PY-MIGRATE-008: the old Windows scheduled task is removed if there is one

    Given Windows, with or without the old scheduled task "oet-archive"
    When the migration is run as a dry run, then for real
    Then with the task, both plans say it will be removed and only the real run deletes it
    And without it, both plans say there is no such task and nothing is deleted
    """
    calls = []

    def run(args, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0 if exists else 1)
    monkeypatch.setattr(migrate.sys, "platform", "win32")
    monkeypatch.setattr(migrate.subprocess, "run", run)
    for dry in (True, False):
        plan = migrate.run(dry_run=dry, home=tmp_path, config_base=tmp_path, keyring_module=FakeKeyring({}))
        assert any(("remove the old scheduled task oet-archive" if exists else "no scheduled task oet-archive") in s
                   for s in plan.steps)
    deletes = [c for c in calls if "/Delete" in c]
    assert deletes == ([["schtasks", "/Delete", "/TN", "oet-archive", "/F"]] if exists else [])
