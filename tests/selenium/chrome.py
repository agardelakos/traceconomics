"""The pinned Chrome for Testing and its driver, fetched by Selenium Manager into ~/.cache/selenium
(or $SE_CACHE_PATH) when missing.

Selenium Manager is asked once per process, one process at a time (a file lock): parallel test
workers asking at once download Chrome over each other and leave its metadata file half-written.

Run on its own, it fetches Chrome and starts it once, headless, outside Selenium, so a Chrome that
can't start says why in its own words (CI runs this before the tests):

    python -I tests/selenium/chrome.py
"""

import fcntl
import os
import subprocess
import sys
from functools import cache
from pathlib import Path

from selenium.webdriver.common.selenium_manager import SeleniumManager

# Chrome for Testing 156.0.8078.47, published 2026-10-19 (at least two weeks before it was pinned).
CHROME_VERSION = "156.0.8078.47"


@cache
def paths() -> dict[str, str]:
    """Paths to the pinned Chrome ("browser_path") and its driver ("driver_path")."""
    cache_dir = Path(os.environ.get("SE_CACHE_PATH", Path.home() / ".cache" / "selenium"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_dir / "traceconomics-tests.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)    # released when the file closes
        found = SeleniumManager().binary_paths(["--browser", "chrome", "--browser-version", CHROME_VERSION])
    for key in ("driver_path", "browser_path"):
        if not Path(found.get(key) or "").is_file():
            raise FileNotFoundError(f"Selenium Manager gave no {key} for Chrome {CHROME_VERSION}: {found}")
    return found


def main() -> int:
    p = paths()
    print(f"Chrome {CHROME_VERSION}: {p['browser_path']}\nchromedriver: {p['driver_path']}", flush=True)
    run = subprocess.run([p["browser_path"], "--headless=new", "--dump-dom", "about:blank"],
                         capture_output=True, text=True, timeout=60)
    if run.returncode != 0 or "<html" not in run.stdout:
        print(f"Chrome did not start (exit {run.returncode}):\n{run.stderr.strip()}", file=sys.stderr)
        return 1
    print("Chrome starts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
