from common import (
    HISTORY_START_URLS,
    MAX_EMAIL_ITEMS,
    PROPERTY_TERMS,
    classify_record,
    clean_excerpt,
    context_fingerprint,
    crawl,
    extract_date,
    find_contexts,
    load_json,
    maybe_email_failures,
    portal_links_text,
    save_json,
    send_email,
    stable_key,
    utc_now_iso,
)

HISTORY_FILE = "data/house_history.json"


def default_history():
    return {
        "version": 1,
        "property": "162 Clark Street, Newton, MA",
        "records": [],
        "failure_fingerprint": "",
        "last_run_utc": "",
    }


def build_history_record(record, contexts):
    fingerprint = context_fingerprint(contexts)
    return {
        "id": stable_key(record["url"], fingerprint),
        "source_title": record["title"],
        "source_url": record["url"],
        "source_type": record["source_type"],
        "category": classify_record(
            record["title"],
            record["url"],
            record["text"],
        ),
        "document_date": extract_date(record["title"], record["text"]),
        "excerpt": clean_excerpt(contexts[0], max_chars=900),
        "match_count": len(contexts),
        "fingerprint": fingerprint,
        "discovered_utc": utc_now_iso(),
    }


def format_record(item):
    date_text = item["document_date"] or "Date not detected"
    return "\n".join(
        [
            item["source_title"],
            f"Type: {item['category']}",
            f"Document date: {date_text}",
            f"Relevant text: {item['excerpt']}",
            f"Source: {item['source_url']}",
        ]
    )


def main():
    history = load_json(HISTORY_FILE, default_history())
    existing_ids = {item["id"] for item in history.get("records", [])}

    records, failures, stats = crawl(
        HISTORY_START_URLS,
        max_pages=400,
        max_pdfs=600,
    )

    added = []

    for record in records:
        contexts = find_contexts(record["text"], PROPERTY_TERMS)
        if not contexts:
            continue

        item = build_history_record(record, contexts)
        if item["id"] in existing_ids:
            continue

        history["records"].append(item)
        existing_ids.add(item["id"])
        added.append(item)

    history["last_run_utc"] = utc_now_iso()

    if added:
        subject = (
            "[NewtonHomeWatch - House History] "
            f"{len(added)} historical record(s) added"
        )
        lines = [
            f"NewtonHomeWatch added {len(added)} newly discovered record(s) to",
            "the 162 Clark Street house-history archive.",
            "",
        ]

        for item in added[:MAX_EMAIL_ITEMS]:
            lines.append(format_record(item))
            lines.append("")

        if len(added) > MAX_EMAIL_ITEMS:
            lines.append(
                f"{len(added) - MAX_EMAIL_ITEMS} additional record(s) are stored "
                "in data/house_history.json."
            )

        lines.extend(["", portal_links_text()])
        send_email(subject, "\n".join(lines))
    else:
        body = "\n".join(
            [
                "NewtonHomeWatch completed the monthly house-history search.",
                "",
                "No newly discovered historical records for 162 Clark Street",
                "were found in the official sources inspected this month.",
                "",
                f"Total archived records: {len(history['records'])}",
                f"Readable records inspected: {stats['records_readable']}",
                f"Source failures: {stats['failures']}",
                "",
                portal_links_text(),
            ]
        )
        send_email(
            "[NewtonHomeWatch - House History] No new historical records this month",
            body,
        )

    maybe_email_failures("House history builder", failures, history)
    save_json(HISTORY_FILE, history)

    print("----- HOUSE HISTORY BUILDER -----")
    print(f"Readable records inspected: {stats['records_readable']}")
    print(f"Historical records added: {len(added)}")
    print(f"Total history records: {len(history['records'])}")
    print(f"Failures: {len(failures)}")


if __name__ == "__main__":
    main()
