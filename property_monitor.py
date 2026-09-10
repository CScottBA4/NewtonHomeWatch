from common import (
    MAX_EMAIL_ITEMS,
    PROPERTY_TERMS,
    classify_record,
    clean_excerpt,
    context_fingerprint,
    crawl,
    extract_date,
    find_contexts,
    load_json,
    portal_links_text,
    save_json,
    send_email,
    stable_key,
    utc_now_iso,
)

STATE_FILE = "data/property_state.json"

# Deliberately focused list. NewtonSearch remains the broad recursive city-
# document crawler, so this monitor does not need to walk hundreds of unrelated
# City pages every day. It checks the property/permit/assessor/GIS systems and
# a small set of current-document pages as a safety net. Linked PDFs from these
# exact pages are still inspected.
FOCUSED_PROPERTY_URLS = [
    # Permitting / Inspectional Services
    "https://www.newtonma.gov/government/newgov-permitting",
    "https://www.newtonma.gov/government/inspectional-services/online-permitting",
    "https://www.newtonma.gov/government/inspectional-services/online-permit-history-lookup",
    "https://www.newtonma.gov/government/inspectional-services/building-permit-summary-report",

    # Parcel / assessor / GIS
    "https://www.newtonma.gov/government/assessing/assessor-s-database",
    "https://www.newtonma.gov/government/information-technology/gis",

    # Planning / zoning / property review
    "https://www.newtonma.gov/government/planning/development-projects",
    "https://www.newtonma.gov/government/planning/development-review/special-permits-land-use",
    "https://www.newtonma.gov/government/planning/zoning-board-of-appeals",
    "https://www.newtonma.gov/government/planning/online-applications",
    "https://www.newtonma.gov/government/planning/historic-preservation",

    # Property-frontage / infrastructure permits
    "https://www.newtonma.gov/government/dpw-permits",
    "https://www.newtonma.gov/government/public-works/engineering",

    # Small safety net for current city material. NewtonSearch does the full
    # recursive crawl of these systems; here we inspect only these exact pages
    # and their directly linked PDFs.
    "https://www.newtonma.gov/government/city-clerk/city-council/electronic-posting-board",
    "https://www.newtonma.gov/how-do-i/view/city-council-dockets",
    "https://apps.newtonma.gov/apps/dockets/search.php",
    "https://www.newtonma.gov/government/city-clerk/city-council/friday-packet",
]


def default_state():
    return {
        "version": 1,
        "initialized": False,
        "items": {},
        "failure_fingerprint": "",
        "last_run_utc": "",
    }


def build_item(record, contexts):
    return {
        "title": record["title"],
        "url": record["url"],
        "source_type": record["source_type"],
        "category": classify_record(
            record["title"],
            record["url"],
            record["text"],
        ),
        "document_date": extract_date(record["title"], record["text"]),
        "fingerprint": context_fingerprint(contexts),
        "excerpt": clean_excerpt(contexts[0]),
        "match_count": len(contexts),
        "last_seen_utc": utc_now_iso(),
    }


def format_item(item, status):
    date_text = item["document_date"] or "Date not detected"
    return "\n".join(
        [
            f"{status}: {item['title']}",
            f"Type: {item['category']}",
            f"Document date: {date_text}",
            f"Relevant text: {item['excerpt']}",
            f"Source: {item['url']}",
        ]
    )


def main():
    state = load_json(STATE_FILE, default_state())

    print("Property monitor mode: focused property sources + current-document safety net", flush=True)
    print(
        f"Checking {len(FOCUSED_PROPERTY_URLS)} exact source pages; "
        "recursive general-site crawling is left to NewtonSearch.",
        flush=True,
    )

    records, failures, stats = crawl(
        FOCUSED_PROPERTY_URLS,
        max_pages=len(FOCUSED_PROPERTY_URLS),
        max_pdfs=175,
    )

    matched = {}
    changes = []

    for record in records:
        contexts = find_contexts(record["text"], PROPERTY_TERMS)
        if not contexts:
            continue

        key = stable_key(record["url"])
        item = build_item(record, contexts)
        matched[key] = item

        previous = state["items"].get(key)
        if state["initialized"]:
            if previous is None:
                changes.append(("NEW", item))
            elif previous.get("fingerprint") != item["fingerprint"]:
                changes.append(("CHANGED", item))

    for key, item in matched.items():
        first_seen = state["items"].get(key, {}).get("first_seen_utc")
        item["first_seen_utc"] = first_seen or utc_now_iso()
        state["items"][key] = item

    if not state["initialized"]:
        # First run establishes a silent baseline. No email is sent unless a
        # later run finds a genuinely new or materially changed record.
        state["initialized"] = True
        print(
            f"Silent baseline created with {len(matched)} matching record(s).",
            flush=True,
        )

    elif changes:
        if len(changes) == 1:
            subject = "[NewtonHomeWatch - Property] 162 Clark Street update"
        else:
            subject = (
                "[NewtonHomeWatch - Property] "
                f"{len(changes)} updates for 162 Clark Street"
            )

        lines = [
            f"NewtonHomeWatch found {len(changes)} new or changed record(s) tied",
            "specifically to 162 Clark Street / its parcel identifier.",
            "",
        ]

        for status, item in changes[:MAX_EMAIL_ITEMS]:
            lines.append(format_item(item, status))
            lines.append("")

        if len(changes) > MAX_EMAIL_ITEMS:
            lines.append(
                f"{len(changes) - MAX_EMAIL_ITEMS} additional update(s) are stored "
                "in data/property_state.json."
            )

        lines.extend(["", portal_links_text()])
        send_email(subject, "\n".join(lines))

    else:
        print("No new property results; no email sent.", flush=True)

    state["last_run_utc"] = utc_now_iso()
    save_json(STATE_FILE, state)

    print("----- PROPERTY MONITOR -----")
    print(f"Exact source pages inspected: {stats['visited_pages']}")
    print(f"Readable pages/documents inspected: {stats['records_readable']}")
    print(f"Property-matching records: {len(matched)}")
    print(f"New/changed records: {len(changes)}")
    print(f"Source/PDF failures logged only: {len(failures)}")


if __name__ == "__main__":
    main()
