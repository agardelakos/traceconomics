"""Moving a local setup from the earlier project name, on a made-up home folder."""

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
