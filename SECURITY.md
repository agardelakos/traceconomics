# Security

## Reporting a vulnerability

Please report it privately: on GitHub, open the repository's **Security** tab and choose
**Report a vulnerability**. Don't open a public issue for it.

Say what is affected, how to reproduce it and what an attacker could do. This is a one-person
project: you'll get an answer as soon as possible, be told what is planned, and be credited in
the release notes unless you'd rather not be.

## What counts

- The website (traceconomics.com): its pages, scripts and response headers.
- The pipeline code in this repository: fetching, parsing, the archive and the release steps.
- The published data files, if they can be made to carry something other than our figures.

A number that looks wrong is not a security issue: open an ordinary issue for it (see the
README).

## Please don't

- Test against the website with heavy or automated traffic.
- Send requests to ELSTAT, Eurostat or any other publisher in the name of this project.

Only the latest release and the `main` branch are supported.
