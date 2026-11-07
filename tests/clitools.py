"""Fixtures shared by the command-line tests (test_cli.py, test_cli_local.py)."""

from types import SimpleNamespace

import pytest

from traceconomics import cli, config as config_mod


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """A config file with an archive, a store and a releases folder in a temporary folder;
    `setup.run(*args)` runs the command line with it and returns the exit code."""
    # main() points TRACECONOMICS_CONFIG at the file it read; setting the variable through
    # monkeypatch first means it is removed again after the test.
    monkeypatch.setenv(config_mod.CONFIG_ENV, "unset")
    monkeypatch.delenv(config_mod.CONFIG_ENV)
    path = tmp_path / "config.toml"
    path.write_text('[archive]\ndir = "archive"\n[fetch]\nuser_agent = "test"\n[store]\ndir = "store"\n'
                    '[release]\ndir = "releases"\n', encoding="utf-8")
    cfg = config_mod.load(path)

    def run(*args):
        return cli.main(["--config", str(path), *args])

    return SimpleNamespace(path=path, cfg=cfg, run=run)


@pytest.fixture
def run(setup, capsys):
    """`run(*args)`: the command line with the temporary config; (exit code, what it printed)."""
    def go(*args):
        code = setup.run(*args)
        return code, capsys.readouterr().out
    return go


@pytest.fixture
def no_store(monkeypatch):
    """Store-backed commands open DuckDB views over the store; a stand-in connection is enough
    when the work behind the command is replaced too."""
    monkeypatch.setattr("traceconomics.store.db.connect", lambda *a, **k: "con")
    monkeypatch.setattr("traceconomics.store.query.open_views", lambda con, folder: None)
