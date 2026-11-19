# Storage auction tracker

Checks storage unit auction sites once a day and builds one digest of every open
auction within 50 miles of Fall City, WA (98024). It shows what's new since
yesterday, what ends in the next 48 hours, and flags units whose contents
mention keywords you care about (tools, furniture, and so on).

## Sources

| Site | What we read | Notes |
|---|---|---|
| [StorageTreasures](https://www.storagetreasures.com/auctions/wa) | Public Washington listing pages, 100 per page | Biggest source (~1,400 WA auctions). robots.txt allows it. Location is city-level. |
| [Bid13](https://bid13.com/current-auction-notices/united-states/washington) | Public WA auction notices page | Full street address and ZIP. robots.txt asks for 5s between requests. |

Not included: Lockerfox (very few WA listings, and its robots.txt disallows the
auction pages). Ideas for later: iBid4Storage, StorageAuctions.com, newspaper
legal notices for in-person sales.

The scraper loads about 15 pages from StorageTreasures and 1 from Bid13 per run,
with pauses between pages, once a day. Please keep it that gentle.

## Settings

Edit [`config.toml`](config.toml): home ZIP, radius, keywords, and which sources are on.

## Running it

**On GitHub (recommended):** the workflow in `.github/workflows/daily.yml` runs
every morning at about 6 AM Pacific. It saves the digest to `docs/index.html`
(download it from the run's *Artifacts*, or view the file in the repo) and can email it.
To run it right now: **Actions → Daily auction digest → Run workflow**.

**Website for you and Chad:** if the repo is public, turn on GitHub Pages under
**Settings → Pages → Build and deployment → Deploy from a branch → `main` / `docs`**.
The digest is then at `https://<your-username>.github.io/storage-auction-tracker/` and
refreshes after each morning run. (Free GitHub accounts can't use Pages on private repos.)

**Email (optional):** add these under **Settings → Secrets and variables → Actions**:

- `SMTP_USER`: the Gmail address that sends the digest
- `SMTP_PASSWORD`: a Gmail [app password](https://myaccount.google.com/apppasswords) (not your normal password)
- `DIGEST_TO`: who gets it, comma-separated (for example, you and Chad)

**On your own computer:**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python -m tracker --no-email
open docs/index.html
```

## How it works

- `tracker/sources/` has one module per site. Each has a `parse(html)` function (tested
  against saved pages in `tests/fixtures/`) and a `fetch(page)` function that drives
  a headless browser.
- `tracker/geo.py` measures straight-line distance using the offline ZIP database in
  the `zipcodes` package.
- `tracker/pipeline.py` filters by radius, removes duplicates, and remembers what it has
  already seen in `data/seen.json`, so the digest can mark new auctions.
- `tracker/digest.py` builds the HTML page/email.

If a site changes its layout, its parser test will still pass, but the run will report
0 auctions for that site and the digest shows a warning. Update the selectors in that
source's module.
