# Security

## Reporting a vulnerability

Please don't open a public issue for a security problem. Report it privately through GitHub: the
repository's **Security** tab, then **Report a vulnerability**. Only the maintainer sees the report.

Useful to include: what you found, where (a page of the site, a file or a command), how to
reproduce it, and what an attacker could do with it.

This is a one-person project with no paid support, so there is no fixed response time: reports are
read and answered as soon as possible, and you'll be told what is planned. You'll be credited in
the release notes unless you'd rather not be. There is no bug bounty.

## What is in scope

- The website (traceconomics.com): its static pages, scripts and response headers (Content
  Security Policy and the other security headers).
- The code in this repository: fetching, parsing, the archive, the computations and the release
  steps.
- The published data files, if they could be made to show something other than what the pipeline
  computed.

A number that looks wrong is not a security issue: open an ordinary issue for it (see
[CONTRIBUTING.md](CONTRIBUTING.md)).

## Please don't

- Test against the website with heavy or automated traffic.
- Send requests to ELSTAT, Eurostat or any other publisher in the name of this project.

## Supported versions

Only the latest version on the default branch, and the live site, are supported.
