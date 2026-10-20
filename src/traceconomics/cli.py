"""Command line: `python -m traceconomics <command>` (or `traceconomics <command>` once installed)."""

from __future__ import annotations

import argparse
import json
import os
import traceback
from datetime import date
from pathlib import Path

from traceconomics import __version__, backfill, config as config_mod, job, schedule
from traceconomics.archive.store import Archive
from traceconomics.notify import notify


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="traceconomics", description="Traceconomics: archive public statistics.")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--config", type=Path, help="config file (default: the user config folder)")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("archive", help="run the archive job if a release is due")
    a.add_argument("--force", action="store_true", help="run even if no release is due")
    a.add_argument("--dry-run", action="store_true", help="list what would be fetched; store nothing")

    i = sub.add_parser("import", help="add a file downloaded by hand (e.g. microdata)")
    i.add_argument("file", type=Path)
    i.add_argument("--source", default="elstat")
    i.add_argument("--dataset", help="default: puf-<file name>, e.g. puf-hbs-2025")
    i.add_argument("--url", help="the page it was downloaded from, if any")
    i.add_argument("--downloaded", type=date.fromisoformat, help="download date (YYYY-MM-DD) if not today")
    i.add_argument("--note")

    s = sub.add_parser("seed", help="copy earlier downloads with recorded URL, date and checksum")
    s.add_argument("folder", type=Path)
    s.add_argument("--dry-run", action="store_true")

    h = sub.add_parser("fetch-history", help="one-off: archive past years of a source table")
    h.add_argument("table", choices=["cpi07"], help="cpi07: ELSTAT CPI table 07 (item indices and weights)")
    h.add_argument("--years", type=_years, required=True, help="e.g. 2011-2013,2015")
    h.add_argument("--pause", type=float, default=60.0, help="seconds between requests (default 60)")
    h.add_argument("--dry-run", action="store_true")

    ck = sub.add_parser("check", help="rebuild official figures from their parts, to test the engine")
    ck.add_argument("which", choices=["v1", "v1-cpi", "v2", "mapping", "v3", "v4", "v5", "v6", "hospital", "prices", "seam",
                                      "combos"],
                    help="v1: all-items HICP from Eurostat sub-indices and weights; "
                         "v1-cpi: Greek CPI from ELSTAT's table 07; "
                         "v2: ELSTAT's household spending table from the survey microdata (needs the local extra); "
                         "mapping: the surveys' old codes mapped to COICOP 2018, against the next year (needs the local extra)")
    ck.add_argument("--geo", default="GR", help="country (ISO code, default GR)")
    ck.add_argument("--outputs", type=Path, default=Path.home() / "traceconomics-outputs",
                    help="combos: the module 1 outputs folder (default ~/traceconomics-outputs)")
    ck.add_argument("--baseline", type=Path, help="combos: an earlier build's outputs folder to compare the default with")

    st = sub.add_parser("store", help="the observation store, built from the archive")
    st.add_argument("action", choices=["update", "rebuild"],
                    help="update: read new snapshots only; rebuild: delete and read everything again")
    st.add_argument("--dataset", action="append", help="limit to a dataset, e.g. eurostat:prc_hicp_iw (repeatable)")

    ex = sub.add_parser("export", help="write published files from the store")
    ex.add_argument("what", choices=["skeleton", "site"],
                    help="skeleton: Greece's all-households HICP, rebuilt; site: the website's data from module 1's outputs")
    ex.add_argument("--out", type=Path, required=True, help="folder to write into (e.g. site/public/data)")
    ex.add_argument("--outputs", type=Path, default=Path.home() / "traceconomics-outputs",
                    help="site: module 1's outputs folder (default ~/traceconomics-outputs)")
    ex.add_argument("--no-downloads", action="store_true", help="site: skip the per-setting download files")

    m1 = sub.add_parser("module1", help="inflation by household group, from the store")
    m1.add_argument("action", choices=["run"], help="run: compute every group's index and rates and write them")
    m1.add_argument("--out", type=Path, required=True, help="folder to write into (rebuildable, e.g. ~/traceconomics-outputs)")
    m1.add_argument("--combinations", choices=["all", "default"], default="all",
                    help="all: every combination of the options (default); default: the default one only")
    m1.add_argument("--spending", action="append", choices=["purchases", "all"],
                    help="spending concept(s) to compute (default: both)")

    wt = sub.add_parser("weights", help="spending shares by group from the survey microdata (needs the local extra)")
    wt.add_argument("action", choices=["run"], help="run: build each survey year's tables and archive them as oet-local")
    wt.add_argument("--years", type=_years, help="e.g. 2008-2024 (default: every archived survey)")
    wt.add_argument("--replicates", type=int, default=1000, help="bootstrap replicates (default 1000)")

    bd = sub.add_parser("bands", help="error bands for the group series (needs the local extra and the microdata)")
    bd.add_argument("action", choices=["run"], help="run: compute the bands and archive them as oet-local")
    bd.add_argument("--replicates", type=int, default=1000, help="bootstrap replicates (default 1000)")
    bd.add_argument("--combinations", choices=["all", "default"], default="all",
                    help="all: every combination of the options (default); default: the default one only")

    mp = sub.add_parser("mapping", help="the survey's old codes mapped to COICOP 2018 (needs the local extra)")
    mp.add_argument("action", choices=["build"], help="build: write the mapping tables from the archive and the store")
    mp.add_argument("--out", type=Path, required=True, help="folder to write into (the package's data folder)")

    sub.add_parser("status", help="last runs, release dates and files waiting for backup")
    sub.add_parser("backup-done", help="record that the archive was just backed up")
    sub.add_parser("notify-test", help="send a test message through the configured channel")

    bk = sub.add_parser("backup", help="copy new archive files to private cloud storage (never the microdata)")
    bk.add_argument("action", choices=["sync", "plan"], help="sync: send them; plan: list what would be sent")

    rl = sub.add_parser("release", help="build a release as a private preview, or promote one to the site")
    rl.add_argument("action", choices=["build", "promote", "status"])
    rl.add_argument("id", nargs="?", help="promote: the build to publish (from `release status`)")

    sc = sub.add_parser("schedule", help="the daily trigger: Windows Task Scheduler, or systemd units on Linux")
    sc.add_argument("action", choices=["install", "remove", "show", "units"],
                    help="install/remove/show: Windows; units: write the Linux service and timer files")
    sc.add_argument("--out", type=Path, help="units: folder to write into (e.g. ~/.config/systemd/user)")

    mg = sub.add_parser("migrate-local", help="one-off: move a local setup from the project's earlier name")
    mg.add_argument("--dry-run", action="store_true", help="show what would move; change nothing")

    args = p.parse_args(argv)
    if args.command == "migrate-local":
        # Runs before the config is read: the config under the new name may not exist yet.
        from traceconomics import migrate

        plan = migrate.run(dry_run=args.dry_run)
        for step in plan.steps:
            print(("would " if args.dry_run else "") + step)
        for problem in plan.problems:
            print(f"PROBLEM {problem}")
        return 1 if plan.problems else 0
    try:
        cfg = config_mod.load(args.config)
    except config_mod.ConfigError as exc:
        p.error(str(exc))
    if args.config is not None:
        # Steps a release runs as separate processes must read the same file.
        os.environ[config_mod.CONFIG_ENV] = str(args.config.resolve())

    try:
        return _dispatch(args, cfg)
    except job.Locked as exc:
        print(f"Skipped: {exc}")
        return 0
    except Exception:  # noqa: BLE001 - a scheduled run has no console; make the crash visible
        text = traceback.format_exc()
        where = notify(cfg, f"ALERT: traceconomics {args.command} crashed", text)
        print(text)
        print(f"Crash report sent to: {where}")
        return 1


def _years(text: str) -> list[int]:
    """'2011-2013,2015' -> [2011, 2012, 2013, 2015]"""
    years: set[int] = set()
    for part in text.split(","):
        lo, _, hi = part.strip().partition("-")
        years.update(range(int(lo), int(hi or lo) + 1))
    return sorted(years)


def _check_v1(cfg, geo: str) -> int:
    from traceconomics.store.db import connect
    from traceconomics.validate import v1

    archive = Archive(cfg.archive_dir)
    paths = {}
    for name in ("prc_hicp_minr", "prc_hicp_iw"):
        rec = archive.latest("eurostat", name)
        if rec is None:
            print(f"No archived eurostat/{name}; run `traceconomics archive` first.")
            return 1
        paths[name] = cfg.archive_dir / rec["path"]
        print(f"Using {rec['path']}")
    weights, prices, official, rates = v1.load(connect(), paths["prc_hicp_minr"], paths["prc_hicp_iw"], geo)
    if not official:
        print(f"No all-items index for {geo}.")
        return 1
    results = v1.run(weights, prices, official, rates, last_year=int(max(official)[:4]))
    print(f"\nV1: {geo} all-items HICP rebuilt from Eurostat sub-indices and item weights\n")
    for r in results:
        print(r.summary() + "\n")
    ok = bool(results) and all(r.passed for r in results)
    print("V1 passed." if ok else "V1 FAILED.")
    return 0 if ok else 1


def _store(cfg, action: str, only: list[str] | None) -> int:
    import time

    from traceconomics.catalog import datasets
    from traceconomics.store.build import Store, update
    from traceconomics.store.db import connect

    unknown = [d for d in only or [] if d not in datasets()]
    if unknown:
        print(f"Unknown dataset(s): {unknown}. Known: {sorted(datasets())}")
        return 2
    started = time.perf_counter()
    with job.RunLock(cfg.store_dir):
        reports = update(Archive(cfg.archive_dir), Store(cfg.store_dir),
                         connect(cfg.store_memory_limit, cfg.store_threads),
                         only=only, full=action == "rebuild")
    for r in reports:
        print(r.line())
    print(f"Store: {cfg.store_dir} ({time.perf_counter() - started:.0f} s)")
    return 0


def _check_v2(cfg) -> int:
    from traceconomics.local import puf, v2

    archive = Archive(cfg.archive_dir)
    years = [y for y in range(2008, 2100) if archive.latest("elstat", f"puf-hbs-{y}")]
    print("V2: ELSTAT's published household spending (table 1.03, purchases) rebuilt from the survey")
    print("microdata: all households every year, and each band in the years whose bands can be rebuilt")
    print()
    ok = True
    for r in v2.run(archive, years):
        strict = r.year not in v2.REPORT_ONLY
        verdict = ("PASS" if r.passed else "FAIL") if strict else "report only"
        ok = ok and (r.passed or not strict)
        where = f"{r.year}" if r.group == v2.ALL else f"  {r.group.replace(chr(0x20ac), 'EUR')}"
        print(f"{where}: {verdict:11s} households {'same' if r.same_households else 'differ'}; "
              f"{r.matched}/{r.compared} figures to the cent; {len(r.excused)} excused (items missing from the PUF); "
              f"{len(r.mismatches)} other differences"
              + ("" if r.uncovered is None else f"; PUF lacks {r.uncovered:.1%} of purchases"))
        if strict:
            for code, label, pub, ours in r.mismatches[:10]:
                print(f"    {code} {label[:40]}: published {pub}, ours {ours}")
    print()
    print("Standard errors: our bootstrap against the coefficients of variation ELSTAT publishes")
    for year, entry in sorted(v2.published_cvs().items()):
        if year not in years:
            continue
        r = v2.cv_check(puf.read(archive, year), entry["cv"])
        ok = ok and r.passed
        print(f"{year}: {'PASS' if r.passed else 'FAIL'} ({entry['source']}; design {r.design})")
        print("    " + "  ".join(f"{code} {pub}/{ours:.1f}" for code, pub, ours in r.rows) + "   (published/ours, %)")
    print()
    print("V2 passed." if ok else "V2 FAILED.")
    return 0 if ok else 1


def _check_v6(cfg) -> int:
    from traceconomics.module1 import checks
    from traceconomics.store.db import connect
    from traceconomics.store.query import open_views

    con = connect(cfg.store_memory_limit, cfg.store_threads)
    open_views(con, cfg.store_dir)
    r = checks.v6(con, Archive(cfg.archive_dir))
    period, h, ours, official = r.worst
    ok = r.compared > 0 and abs(round(ours, 2) - official) <= 0.0100001
    print("V6: our contributions code against Eurostat's contributions to euro-area inflation "
          "(12 divisions, 2016-2025, two decimals)")
    print(f"{r.exact}/{r.compared} equal; largest difference {abs(round(ours, 2) - official):.2f} pp "
          f"({period}, division {h}: ours {ours:.4f}, Eurostat {official:.2f})")
    print("V6 passed." if ok else "V6 FAILED (more than rounding).")
    return 0 if ok else 1


def _check_v3(cfg) -> int:
    from traceconomics.module1 import checks
    from traceconomics.store.db import connect
    from traceconomics.store.query import open_views

    con = connect(cfg.store_memory_limit, cfg.store_threads)
    open_views(con, cfg.store_dir)
    print("V3: our all-households index against the official CPI, one change at a time (annual averages, %)")
    print("  L1 = our survey weights with ELSTAT's timing (survey y-2); L2 = our timing (survey y-1)")
    print(f"  years where L1 differs from the CPI by more than {checks.REPORT_PP} pp need an explanation (report only)")
    for spending in ("purchases", "all"):
        print()
        print(f"{spending}:  year  official     L1     L2   weights data  timing rule")
        for r in checks.v3(con, Archive(cfg.archive_dir), spending):
            note = ""
            if abs(r.weights_effect) > checks.REPORT_PP:
                note = "  <- " + checks.KNOWN.get(r.year, checks.EXPLAINED.get(r.year, "TO EXPLAIN"))
            print(f"            {r.year}  {r.official:7.2f} {r.l1:6.2f} {r.l2:6.2f}   {r.weights_effect:+6.2f}"
                  f"        {r.timing_effect:+6.2f}{note}")
    return 0


def _check_mapping(cfg) -> int:
    from traceconomics.local import mapping_check as mc
    from traceconomics.store.db import connect
    from traceconomics.store.query import open_views

    archive = Archive(cfg.archive_dir)
    print("Mapping to COICOP 2018: the last year in the old codes, mapped, against the next year")
    print(f"(all households, no imputed rent; flagged: over {mc.MIN_PP} pp, over {mc.TIMES_USUAL}x the usual yearly change,")
    print(f"and over {mc.NOISE_SE} combined standard errors; from the mapping if splits decided {mc.EXPOSURE:.0%} or more)")
    usual = mc.usual_change(archive)
    reasons = mc.explained()
    ok = True
    for older, newer in ((2023, 2024), (2014, 2015)):
        r = mc.compare(archive, older, newer, usual, reasons.get(f"{older}-{newer}", {}))
        ok = ok and r.passed
        div = r.table[r.table.index.str.len() == 2]
        print()
        print(f"{older} mapped -> {newer}: {'PASS' if r.passed else 'FAIL'}; divisions within "
              f"{div['diff'].abs().max():.2f} pp; {len(r.flags)} flagged")
        for f in r.flags:
            verdict = ("explained: " + f.explanation) if f.explanation else (
                "NOT EXPLAINED" if f.from_mapping else "not from the mapping")
            print(f"    {f.code}: {f.older:.2f}% -> {f.newer:.2f}%  (usual change {f.usual:.2f}, noise {f.noise:.2f}, "
                  f"decided by splits {f.exposure:.1%}): {verdict}")
    print()
    print("Report: ELSTAT's CPI weights (table 07, COICOP 2018) against our mapped shares of the survey a year or")
    print("two before; mean absolute difference per division, per mille (no pass rule)")
    con = connect(cfg.store_memory_limit, cfg.store_threads)
    open_views(con, cfg.store_dir)
    print(mc.cpi_report(archive, con).to_string(index=False))
    print()
    print("Mapping check passed." if ok else "Mapping check FAILED.")
    return 0 if ok else 1


def _check_v1_cpi(cfg) -> int:
    from traceconomics.validate import v1_cpi

    checked, earlier, disagreements, files = v1_cpi.run_archive(Archive(cfg.archive_dir))
    print(f"Table 07 files for {min(files)}-{max(files)} ({len(files)} years)")
    missing = sorted(set(range(min(files), max(files) + 1)) - set(files))
    if missing:
        print(f"Missing years: {missing} (see `traceconomics fetch-history cpi07`)")
    print(f"December values that differ between a year's file and the next year's link month: {disagreements}")
    print("\nV1-CPI: Greek CPI rebuilt from ELSTAT table 07 item indices and weights\n")
    print(checked.summary() + "\n")
    if earlier is not None:
        print(earlier.summary().replace(", FAIL", ", outside the check").replace("  FAIL ", "  off: ") + "\n")
    print("V1-CPI passed." if checked.passed else "V1-CPI FAILED.")
    return 0 if checked.passed else 1


def _dispatch(args, cfg) -> int:
    if args.command == "archive":
        result = job.run(cfg, force=args.force, dry_run=args.dry_run)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("result") in ("ok", "not-due", "dry-run") else 1

    if args.command == "import":
        r = backfill.import_file(Archive(cfg.archive_dir), args.file, source=args.source, dataset=args.dataset,
                                 url=args.url, downloaded=args.downloaded, note=args.note)
        print(f"{r.status}: {r.source}/{r.dataset}" + (f" -> {r.path}" if r.path else ""))
        return 0

    if args.command == "seed":
        rep = backfill.seed(Archive(cfg.archive_dir), args.folder, dry_run=args.dry_run)
        verb = "would store" if args.dry_run else "stored"
        print(f"{verb}: {len(rep.stored)}; already archived: {rep.unchanged}; "
              f"skipped (no date/checksum/file): {len(rep.skipped)}; checksum mismatch: {len(rep.bad_checksum)}; "
              f"not seeded, no recorded source (papers, scripts, extracted copies, older pages): {rep.unrecorded}")
        for line in rep.stored:
            print(f"  + {line}")
        for line in rep.skipped + [f"BAD CHECKSUM {x}" for x in rep.bad_checksum]:
            print(f"  ! {line}")
        return 1 if rep.bad_checksum else 0

    if args.command == "fetch-history":
        result = job.fetch_history(cfg, args.years, pause_seconds=args.pause, dry_run=args.dry_run)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("result") in ("ok", "dry-run") else 1

    if args.command == "export":
        from traceconomics.export import skeleton
        from traceconomics.store.db import connect
        from traceconomics.store.query import open_views

        con = connect(cfg.store_memory_limit, cfg.store_threads)
        open_views(con, cfg.store_dir)
        if args.what == "site":
            from traceconomics.export import site

            written = site.export(con, Archive(cfg.archive_dir), args.outputs, args.out,
                                  with_downloads=not args.no_downloads, log=lambda line: print(line, flush=True))
            print(f"Wrote {len(written)} files under {Path(args.out) / site.FORMAT}")
            return 0
        for path in skeleton.export(con, args.out):
            print(f"Wrote {path}")
        return 0

    if args.command == "store":
        return _store(cfg, args.action, args.dataset)

    if args.command == "module1":
        from traceconomics.module1 import availability, combinations, index, output
        from traceconomics.store.db import connect
        from traceconomics.store.query import open_views

        con = connect(cfg.store_memory_limit, cfg.store_threads)
        open_views(con, cfg.store_dir)
        archive = Archive(cfg.archive_dir)
        only = combinations.settings() if args.combinations == "all" else [combinations.DEFAULT]
        if args.spending:
            only = [s for s in only if s["spending"] in args.spending]
        folder = Path(args.out) / "gr" / "m1"
        writer, summaries = output.Writer(folder), []
        for k, (setting, series, blocks) in enumerate(combinations.iterate(con, archive, only=only), 1):
            writer.add(series, blocks)
            summaries += [availability.Summary.of(s) for s in series]
            fell_back = sum(len(u.price_with) for s in series for u in s.used.values())
            print(f"[{k}/{len(only)}] {combinations.label(setting)}: {len(series)} series, "
                  f"{min(min(s.published) for s in series)} to {max(max(s.published) for s in series)}; "
                  f"{fell_back} item-years priced by another code", flush=True)
        written = writer.close()
        validation = []
        for spending in sorted({s["spending"] for s in only}):
            validation += index.build_all(con, archive, spending=spending, groups=index.VALIDATION_GROUPS)
        written += output.write_validation(folder, validation, index.price_blocks(con, archive))
        written += availability.write(folder, availability.build(summaries))
        written.append(output.write_metadata(folder, first_period=writer.first_period,
                                             last_period=writer.last_period, manifest=output.manifest(con)))
        for path in written:
            print(f"Wrote {path}")
        print(json.dumps(writer.counts))
        return 0

    if args.command == "weights":
        from traceconomics.local import weights

        archive = Archive(cfg.archive_dir)
        years = args.years or [y for y in range(2008, 2100) if archive.latest("elstat", f"puf-hbs-{y}")]
        for line in weights.run(archive, years, args.replicates):
            print(json.dumps(line, ensure_ascii=False))
        return 0

    if args.command == "bands":
        from traceconomics.local import bands
        from traceconomics.store.db import connect
        from traceconomics.store.query import open_views

        con = connect(cfg.store_memory_limit, cfg.store_threads)
        open_views(con, cfg.store_dir)
        from traceconomics.module1 import combinations

        only = combinations.settings() if args.combinations == "all" else [combinations.DEFAULT]
        r = bands.run(Archive(cfg.archive_dir), con, args.replicates, only=only,
                      log=lambda line: print(line, flush=True))
        t = r.pop("table")
        print(json.dumps(r, ensure_ascii=False))
        default = (t.spending == "purchases") & (t.imputed_rent == "excluded") & (t.price_source == "cpi")             & (t.weights_timing == "N") & (t.tutoring == "priced") & (t.grouping == "B")
        gap = t[default & (t.unit == "RCH_A_AVG_GAP")]
        print("Q1-Q5 gap, annual averages: standard error (pp) by year:",
              dict(zip(gap.ref_period, gap.se)))
        return 0

    if args.command == "mapping":
        from traceconomics.local import mapping

        report = mapping.build(Archive(cfg.archive_dir), cfg.store_dir, args.out)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    if args.command == "check":
        if args.which == "v2":
            return _check_v2(cfg)
        if args.which == "mapping":
            return _check_mapping(cfg)
        if args.which == "v3":
            return _check_v3(cfg)
        if args.which == "v6":
            return _check_v6(cfg)
        if args.which == "v4":
            from traceconomics.module1 import benchmarks
            from traceconomics.store.db import connect
            from traceconomics.store.query import open_views

            con = connect(cfg.store_memory_limit, cfg.store_threads)
            open_views(con, cfg.store_dir)
            ok = True
            print("V4: other studies rebuilt with their own settings (tier B: months within "
                  f"{benchmarks.MONTHLY_PP} pp, annual averages within {benchmarks.ANNUAL_LIMIT_PP} pp)")
            for r in benchmarks.v4_bruegel(con, Archive(cfg.archive_dir)):
                ok = ok and r.passed
                p, a, b = r.worst_month
                print(f"{r.name}: {'PASS' if r.passed else 'FAIL'}; {r.months} months, largest gap {abs(a - b):.2f} pp ({p}); "
                      "annual averages " + ", ".join(f"{y} {x:.2f}/{z:.2f}" for y, (x, z) in r.annual.items()) + " (ours/theirs)")
            if r.provisional:
                print(f"  not compared, built by Bruegel on provisional data: {', '.join(r.provisional)}")
            print()
            print("KEPE (report: KEPE priced the 12 COICOP 1999 divisions as published then; only ELSTAT's re-issued")
            print("COICOP 2018 series exist now, so an exact rebuild isn't possible). Annual averages, ours vs KEPE's chart 1:")
            pub = benchmarks.kepe_published()["chart1"]
            for (spending, ranking), v in benchmarks.v4_kepe(con).items():
                cells = "; ".join(f"{k} " + " ".join(f"{y}:{v['rates'][k][y]:.2f}/{pub[k][str(y)]}" for y in sorted(v["rates"][k]))
                                  for k in ("P20", "R20", "R10"))
                print(f"  {spending}, ranking {ranking}: largest gap {v['max_gap']:.2f}, mean {v['mean_gap']:.2f}")
                print(f"     {cells}")
            print("V4 passed (Bruegel, tier B; KEPE is a report)." if ok else "V4 FAILED (Bruegel, tier B).")
            return 0 if ok else 1
        if args.which == "v5":
            from traceconomics.module1 import attribution
            from traceconomics.store.db import connect
            from traceconomics.store.query import open_views

            con = connect(cfg.store_memory_limit, cfg.store_threads)
            open_views(con, cfg.store_dir)
            print("V5: our default against Bruegel and KEPE, one setting at a time (gap, annual averages, pp; report)")
            for title, rows in (("Bruegel (Q1-Q5)", attribution.v5_bruegel(con, Archive(cfg.archive_dir))),
                                ("KEPE (P20-R20)", attribution.v5_kepe(con, Archive(cfg.archive_dir)))):
                years = sorted(next(iter(rows.values())))
                print()
                print(title.ljust(52) + "  ".join(f"{y:>5}" for y in years))
                for name, g in rows.items():
                    print(name.ljust(52) + "  ".join(f"{g[y]:+5.2f}" for y in years))
            return 0
        if args.which == "combos":
            from traceconomics.module1 import combos_check as cc

            folder = args.outputs / "gr" / "m1"
            base = args.baseline / "gr" / "m1" if args.baseline else None
            print("Every combination: identities (strict)")
            results = cc.identities(folder, base)
            for name, ok, detail in results:
                print(f"  {'ok  ' if ok else 'FAIL'} {name}: {detail}")
            print()
            print("Price source, annual averages (%): all households CPI / HICP; Q1-Q5 gap (B) CPI / HICP")
            for y, r in cc.source(folder).items():
                gc, gh = r["gap_cpi"], r["gap_hicp"]
                print(f"  {y}  {r['all_cpi']:6.2f} {r['all_hicp']:6.2f}  ({r['all_hicp'] - r['all_cpi']:+.2f})   "
                      + (f"gap {gc:+.1f} {gh:+.1f}" if gc is not None and gh is not None else ""))
            print()
            print("Timing, Q1-Q5 gap (B), annual averages (pp): rules N / F / U")
            for y, r in cc.timing(folder).items():
                print(f"  {y}  " + "  ".join(f"{k} {v:+.1f}" if v is not None else f"{k}   - " for k, v in r.items()))
            print()
            print("Imputed rent kept (option 2): its weight in 2025, and the change in annual-average rates (pp)")
            for g, r in cc.rent(folder).items():
                ch = r["change"]
                print(f"  {g:10s} weight {r['weight_2025']:.3f}   " + ", ".join(f"{y} {ch[y]:+.2f}" for y in sorted(ch)
                                                                           if y in (2010, 2015, 2020, 2022, 2023, 2025)))
            print()
            t = cc.tutoring(folder)
            print(f"Tutoring from 2026: annual rate {t['period']} priced / excluded; education weight 2026 priced / excluded")
            for g, r in t["groups"].items():
                print(f"  {g:14s} {r['priced']:6.2f} {r['excluded']:6.2f}  ({r['excluded'] - r['priced']:+.2f})   "
                      f"{r['education_weight_priced']:.4f} {r['education_weight_excluded']:.4f}")
            ok = all(ok for _, ok, _ in results)
            print()
            print("Identities passed." if ok else "Identities FAILED.")
            return 0 if ok else 1
        if args.which == "seam":
            from traceconomics.module1 import checks
            from traceconomics.store.db import connect
            from traceconomics.store.query import open_views

            con = connect(cfg.store_memory_limit, cfg.store_threads)
            open_views(con, cfg.store_dir)
            print("Seam: each group's January-December 2010 movement, same weights, priced with ELSTAT's original")
            print("tables and with its re-issued series (report)")
            for g, (a, b) in checks.seam(con, Archive(cfg.archive_dir)).items():
                print(f"  {g:24s} original {a:6.2f}%   re-issued {b:6.2f}%   difference {a - b:+.2f} pp")
            return 0
        if args.which == "prices":
            from traceconomics.module1 import checks
            from traceconomics.store.db import connect
            from traceconomics.store.query import open_views

            con = connect(cfg.store_memory_limit, cfg.store_threads)
            open_views(con, cfg.store_dir)
            print("V-prices: the CPI's and the HICP's annual rates for the same item (4 and 5 digits), report only")
            print("year   pairs  median gap  within 0.1 pp   largest")
            for y, d in checks.v_prices(con).items():
                print(f"{y}  {d['pairs']:6d}   {d['median']:8.3f}   {d['within_0.1']:10.0%}   {d['max']:8.2f}")
            return 0
        if args.which == "hospital":
            from traceconomics.local import hospital_check
            from traceconomics.store.db import connect
            from traceconomics.store.query import open_views

            con = connect(cfg.store_memory_limit, cfg.store_threads)
            open_views(con, cfg.store_dir)
            r = hospital_check.run(Archive(cfg.archive_dir), con)
            print("Hospital services put back into surveys 2008-2014 (their band averages from table 1.03):")
            for year, note in r["surveys"].items():
                print(f"  survey {year}: {note['hospital_share_of_purchases']:.1%} of purchases; {note['bands']}")
            print("Change in annual-average rates (pp), by group:")
            for name, changes in r["series"].items():
                print(f"  {name}: " + ", ".join(f"{y} {v:+.3f}" for y, v in changes.items()))
            print("Change in the Q1-Q5 gap (pp): " + ", ".join(f"{y} {v:+.3f}" for y, v in r["gap_change"].items()))
            return 0
        return _check_v1(cfg, args.geo) if args.which == "v1" else _check_v1_cpi(cfg)

    if args.command == "status":
        archive = Archive(cfg.archive_dir)
        state = job.load_state(cfg.archive_dir)
        print(f"Archive: {cfg.archive_dir}")
        print(f"Last good run (releases covered through): {state.get('last_good_run', 'never')}")
        upcoming = sorted(d for d in job.all_release_dates(state, cfg) if d >= date.today())[:5]
        print("Next release days: " + (", ".join(d.isoformat() for d in upcoming) or "none known"))
        for r in archive.runs()[-5:]:
            print(f"  run {r.get('started')}: {r.get('result')} ({r.get('reason', '')}) "
                  f"stored={r.get('stored', 0)} failures={len(r.get('failures', []))}")
        waiting = archive.stored_since(state.get("backup_mark"))
        print(f"Files waiting for backup since {state.get('backup_mark', 'the start')}: {len(waiting)}")
        return 0

    if args.command == "backup-done":
        print(f"Backup recorded at {job.mark_backup_done(cfg)} (UTC).")
        return 0

    if args.command == "notify-test":
        print("Sent to: " + notify(cfg, "test message", "If you can read this, alerts reach you."))
        return 0

    if args.command == "backup":
        from traceconomics import backup

        if args.action == "plan":
            todo = backup.plan(cfg.archive_dir)
            print(f"{len(todo)} files to send")
            for name, _ in todo[:50]:
                print(f"  {name}")
            return 0
        result = backup.sync(cfg.archive_dir)
        print(json.dumps(result))
        return 0 if result["result"] in ("ok", "off") else 1

    if args.command == "release":
        from traceconomics import release

        if args.action == "build":
            result = release.build(cfg, args.config)
            print(release.render(result))
            return 0 if result["result"] == "ok" else 1
        if args.action == "promote":
            if not args.id:
                print("Which build? See `traceconomics release status`.")
                return 2
            done = release.promote(cfg, args.id)
            print(f"Promoted {done['id']} to {done['to']}: {done.get('url') or '(no address in the log)'}")
            return 0
        for b in release.status(cfg.release.releases_dir):
            print(f"  {b['id']}  {b['result']:7s}  {b.get('failed_step') or ''}  {b.get('preview_url') or ''}")
        return 0

    if args.command == "schedule":
        if args.action == "units":
            if not args.out:
                print("Where? Pass --out, e.g. ~/.config/systemd/user")
                return 2
            for path in schedule.write_units(cfg, args.out):
                print(f"Wrote {path}")
            return 0
        if args.action == "install":
            print(f"Installed task {schedule.install(cfg)}: daily at {cfg.run_after:%H:%M}, runs missed triggers later.")
        elif args.action == "remove":
            schedule.remove()
            print("Removed.")
        else:
            print(schedule.show())
        return 0
    return 2
