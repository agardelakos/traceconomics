# The Selenium suite (testing showcase)

A second browser suite for the site, in Python and Selenium on a pinned Chrome for Testing, over the
same areas as the Playwright suite in `site/tests/ui/`. It is part of the maintainer's testing
showcase: it exists to compare the two tools on the same product, and asks nothing of contributors.
A change to the site updates the Playwright suite only; if it breaks a test here, the maintainer
follows up.

Run it after `npm run build` in `site/`, with `requirements-selenium.txt` installed:

```sh
.venv/bin/python -I -m pytest tests/selenium --selenium -n auto
```

The plain pytest run never collects these tests. More on the wiki, "Testing showcase".
