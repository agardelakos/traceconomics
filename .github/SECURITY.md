# Security

## Reporting a problem

Please don't open a public issue for a security problem. Report it privately through GitHub instead:
the repository's **Security** tab, then **Report a vulnerability**. Only the maintainer sees the report.

Useful to include: what you found, where (a page of the site, a file or a command), how to reproduce
it, and what an attacker could do with it.

This is a one-person project with no paid support, so there is no fixed response time; reports are
read and answered as soon as possible. There is no bug bounty.

## What is in scope

- The website (static pages, served with a Content Security Policy and other security headers).
- The code in this repository: the pipeline that fetches, stores and computes the published data.
- The published data files, if they could be made to show something other than what the pipeline
  computed.

Only the latest version on the default branch, and the live site, are supported.
