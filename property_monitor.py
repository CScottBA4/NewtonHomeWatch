from common import (
    MAX_EMAIL_ITEMS,
    PROPERTY_START_URLS,
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

STATE_FILE = "data/property_state.json"


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

    records, failures, stats = crawl(PROPERTY_START_URLS)

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

    # Update persistent state with everything seen on this run. Older records
    # are retained if a source is temporarily unavailable.
    for key, item in matched.items():
        first_seen = state["items"].get(key, {}).get("first_seen_utc")
        item["first_seen_utc"] = first_seen or utc_now_iso()
        state["items"][key] = item

    if not state["initialized"]:
        state["initialized"] = True

        body = "\n".join(
            [
                "NewtonHomeWatch property monitoring is now initialized.",
                "",
                "Property: 162 Clark Street, Newton, MA",
                f"Existing matching official records used as baseline: {len(matched)}",
                "",
                "Old material has been recorded without generating individual alerts.",
                "Future runs will email only newly discovered or materially changed",
                "property-related records.",
                "",
                f"Readable records inspected: {stats['records_readable']}",
                f"Source failures: {stats['failures']}",
                "",
                portal_links_text(),
            ]
        )

        send_email(
            "[NewtonHomeWatch - Property] 162 Clark Street baseline created",
            body,
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
        body = "\n".join(
            [
                "NewtonHomeWatch completed the scheduled property check.",
                "",
                "No new or materially changed records tied to 162 Clark Street",
                "were found in the official sources inspected.",
                "",
                f"Readable records inspected: {stats['records_readable']}",
                f"Property-matching records currently tracked: {len(matched)}",
                f"Source failures: {stats['failures']}",
                "",
                portal_links_text(),
            ]
        )
        send_email(
            "[NewtonHomeWatch - Property] No new 162 Clark Street updates",
            body,
        )

    state["last_run_utc"] = utc_now_iso()
    maybe_email_failures("Property monitor", failures, state)
    save_json(STATE_FILE, state)

    print("----- PROPERTY MONITOR -----")
    print(f"Readable records inspected: {stats['records_readable']}")
    print(f"Property-matching records: {len(matched)}")
    print(f"New/changed records: {len(changes)}")
    print(f"Failures: {len(failures)}")


if __name__ == "__main__":
    main()
