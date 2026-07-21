from __future__ import annotations

import os

from snowwatch import load_env

_VAR = "SNOWWATCH_DOTENV_TEST"


def test_dotenv_loads_when_var_absent(tmp_path, monkeypatch):
    monkeypatch.delenv(_VAR, raising=False)
    env = tmp_path / ".env"
    env.write_text(f"{_VAR}=from_dotenv\n")
    load_env(env)
    try:
        assert os.environ[_VAR] == "from_dotenv"
    finally:
        os.environ.pop(_VAR, None)


def test_real_env_takes_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv(_VAR, "from_real")
    env = tmp_path / ".env"
    env.write_text(f"{_VAR}=from_dotenv\n")
    load_env(env)
    assert os.environ[_VAR] == "from_real"


def test_missing_env_file_is_noop(tmp_path, monkeypatch):
    monkeypatch.delenv(_VAR, raising=False)
    load_env(tmp_path / "does-not-exist.env")
    assert _VAR not in os.environ
