# NewtonHomeWatch

Private home/property monitoring for 162 Clark Street and Clark Street, Newton, MA.

This repository contains three small monitors:

1. **Property Monitor** — runs daily and looks for new or changed official material tied specifically to 162 Clark Street (including address variants and parcel/account identifier `62023 0003`). It is intentionally focused on permit/inspection, assessor/GIS, planning/zoning, historic-preservation and property-infrastructure sources rather than recursively crawling the entire City website.
2. **Clark Street Digest** — runs Monday and Thursday and sends one digest containing newly discovered Clark Street activity from the official sources it crawls.
3. **House History Builder** — runs monthly and appends newly discovered historical records about 162 Clark Street to `data/house_history.json`.

The first version is deliberately rule-based: it extracts relevant nearby text and links back to the original City webpage/PDF. It does **not** use an AI API.

## How this differs from NewtonSearch

`NewtonSearch` remains the broad recursive City-document monitor. It searches City Council material, dockets, Friday packets, planning/zoning pages, Public Works pages and linked PDFs for both **162 Clark Street** and **Clark Street**.

`NewtonHomeWatch - Property` is complementary rather than a duplicate. It checks a curated set of property-oriented sources plus a small current-document safety net. It does not follow those pages recursively into hundreds of unrelated City pages. Directly linked PDFs from the focused source pages are still inspected.

This means the broad City-document coverage is retained by NewtonSearch while NewtonHomeWatch can concentrate on the property-specific systems that NewtonSearch is not designed around.

## Email subjects

- `[NewtonHomeWatch - Property] ...`
- `[NewtonHomeWatch - Clark Street] Weekly street activity`
- `[NewtonHomeWatch - House History] ...`
- `[NewtonHomeWatch - Warning] ...` for crawl/read failures

## Property-monitor sources

The daily property monitor checks a curated set of official pages covering:

- NewGov / Inspectional Services permitting entry points and permit-history information
- Building permit summary information
- Newton assessor/property database entry points
- Newton GIS
- Planning development projects
- Special Permits / Land Use
- Zoning Board of Appeals
- Planning online applications
- Historic Preservation
- DPW permits and Engineering
- A small safety net consisting of the Electronic Posting Board, City Council dockets and Friday Packet pages

The City exposes permit/address search through NewGov/OpenGov and parcel information through Newton GIS/assessor tools. The current release records and monitors the official NewGov entry points but does not yet automate the JavaScript-driven address search inside NewGov. That remains the highest-value dedicated adapter to add next; it should be implemented separately rather than by duplicating the general City crawl.

## Required GitHub Secrets

In **Settings -> Secrets and variables -> Actions**, create these repository secrets:

- `ALERT_EMAIL_TO` — email address that should receive alerts
- `SMTP_USER` — Gmail/Google account used to send alerts
- `SMTP_PASSWORD` — Google app password for this repository

Secrets from another repository are not automatically shared with this repository.

## Scheduling

GitHub Actions uses UTC. Current schedules:

- Property monitor: daily at 13:05 UTC
- Clark Street digest: Monday + Thursday at 14:10 UTC
- House history: first day of each month at 14:20 UTC

All workflows can also be run manually from the **Actions** tab.

## First-run behavior

The property and street monitors establish a baseline on their first successful run so you are not flooded with old material. Subsequent runs email only new or materially changed relevant items. The house-history builder is archival, so it records historical matches it discovers.

## Notes

- Digital PDFs are text-extracted with PyMuPDF.
- Image-only/scanned PDFs are logged as unreadable; OCR is intentionally not enabled in this first version.
- State files are committed back to the private repository after each run so the monitors remember what they have already seen.
