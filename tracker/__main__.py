"""Run the tracker: python -m tracker [--no-email] [--config config.toml]"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
import traceback
from pathlib import Path

from . import digest
from .pipeline import Store, dedupe, filter_nearby, tag_keywords
from .sources import bid13, storagetreasures

ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 storage-auction-tracker (personal use, once daily)"
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.toml"))
    ap.add_argument("--no-email", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "docs" / "index.html"))
    args = ap.parse_args(argv)

    cfg = tomllib.loads(Path(args.config).read_text())
    sources = cfg.get("sources", {})

    from playwright.sync_api import sync_playwright

    collected, errors = [], []
    with sync_playwright() as p:
        exe = os.getenv("CHROMIUM_PATH")  # optional: use an already-installed Chromium
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        page = browser.new_context(user_agent=USER_AGENT).new_page()
        jobs = [
            ("bid13", bid13.fetch),
            ("storagetreasures", storagetreasures.fetch),
        ]
        for name, fn in jobs:
            sc = sources.get(name, {})
            if not sc.get("enabled", True):
                continue
            try:
                got = fn(page, state=sc.get("state"))
                print(f"{name}: {len(got)} auctions statewide")
                collected += got
            except Exception as e:  # keep going if one site breaks
                traceback.print_exc()
                errors.append(f"{name}: {type(e).__name__}: {e}")
        browser.close()

    auctions = dedupe(collected)
    nearby, unknown = filter_nearby(auctions, cfg["home_zip"], cfg["radius_miles"])
    if unknown:
        print(f"Could not locate {len(unknown)} auctions: " + ", ".join(sorted({f'{a.city}, {a.state}' for a in unknown})))
    for a in nearby:
        a.tags = tag_keywords(a, cfg.get("keywords", []))

    store = Store(ROOT / "data" / "seen.json")
    new = store.update(nearby)
    store.save()
    (ROOT / "data" / "latest.json").write_text(json.dumps([a.to_dict() for a in nearby], indent=1))

    page_html = digest.render(nearby, new, cfg, errors)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page_html)
    print(f"{len(nearby)} within {cfg['radius_miles']} mi, {len(new)} new. Digest: {out}")

    if not args.no_email:
        subject = f"Storage auctions: {len(new)} new near {cfg['home_zip']}"
        email_html = digest.render(nearby, new, cfg, errors, for_email=True)
        if digest.send_email(email_html, subject):
            print("Email sent.")
        else:
            print("Email not configured (set SMTP_USER, SMTP_PASSWORD, DIGEST_TO).")

    # Fail the run only if every source failed.
    return 1 if errors and not collected else 0


if __name__ == "__main__":
    sys.exit(main())
