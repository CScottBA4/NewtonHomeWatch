from common import (
    MAX_EMAIL_ITEMS,
    PROPERTY_TERMS,
    STREET_START_URLS,
    STREET_TERMS,
    classify_record,
    clean_excerpt,
    contains_any,
    context_fingerprint,
    crawl,
    extract_date,
    find_contexts,
    load_json,
    maybe_email_failures,
    save_json,
    send_email,
    stable_key,
    utc_now_iso,
)

STATE_FILE = "data/street_state.json"


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
        "mentions_162_clark": contains_any(record["text"], PROPERTY_TERMS),
        "last_seen_utc": utc_now_iso(),
    }


def format_item(item, status):
    date_text = item["document_date"] or "Date not detected"
    property_note = (
        "Yes - this source also mentions 162 Clark Street"
        if item["mentions_162_clark"]
        else "No"
    )
    return "\n".join(
        [
            f"{status}: {item['title']}",
            f"Type: {item['category']}",
            f"Document date: {date_text}",
            f"Also mentions 162 Clark Street: {property_note}",
            f"Relevant text: {item['excerpt']}",
            f"Source: {item['url']}",
        ]
    )


def main():
    state = load_json(STATE_FILE, default_state())

    records, failures, stats = crawl(STREET_START_URLS)

    # PDF read/extraction problems stay in the Actions log only. Warning emails
    # are reserved for failures of non-PDF sources.
    email_failures = [
        failure
        for failure in failures
        if not failure.get("kind", "").startswith("pdf/document")
    ]

    matched = {}
    changes = []

    for record in records:
        contexts = find_contexts(record["text"], STREET_TERMS)
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
        state["initialized"] = True
        body = "\n".join(
            [
                "NewtonHomeWatch Clark Street monitoring is now initialized.",
                "",
                f"Existing Clark Street source records used as baseline: {len(matched)}",
                "",
                "Old material has been recorded without being sent as a large",
                "historical digest. Future Monday/Thursday digests will contain",
                "only newly discovered or materially changed Clark Street items.",
                "",
                f"Readable records inspected: {stats['records_readable']}",
                f"Non-PDF source failures: {len(email_failures)}",
            ]
        )
        send_email(
            "[NewtonHomeWatch - Clark Street] Street activity - baseline created",
            body,
        )

    else:
        if changes:
            subject = (
                "[NewtonHomeWatch - Clark Street] Street activity - "
                f"{len(changes)} new/changed item(s)"
            )
            lines = [
                f"NewtonHomeWatch found {len(changes)} new or changed Clark Street",
                "item(s) since the previous digest.",
                "",
            ]

            for status, item in changes[:MAX_EMAIL_ITEMS]:
                lines.append(format_item(item, status))
                lines.append("")

            if len(changes) > MAX_EMAIL_ITEMS:
                lines.append(
                    f"{len(changes) - MAX_EMAIL_ITEMS} additional item(s) are stored "
                    "in data/street_state.json."
                )
        else:
            subject = (
                "[NewtonHomeWatch - Clark Street] Street activity - "
                "no new items"
            )
            lines = [
                "NewtonHomeWatch completed the Clark Street check.",
                "",
                "No new or materially changed Clark Street items were found.",
                "",
            ]

        lines.extend(
            [
                f"Readable records inspected: {stats['records_readable']}",
                f"Clark Street source records currently tracked: {len(matched)}",
                f"Non-PDF source failures: {len(email_failures)}",
            ]
        )
        send_email(subject, "\n".join(lines))

    state["last_run_utc"] = utc_now_iso()
    maybe_email_failures("Clark Street digest", email_failures, state)
    save_json(STATE_FILE, state)

    pdf_failures = len(failures) - len(email_failures)
    print("----- CLARK STREET DIGEST -----")
    print(f"Readable records inspected: {stats['records_readable']}")
    print(f"Clark Street matching records: {len(matched)}")
    print(f"New/changed records: {len(changes)}")
    print(f"Non-PDF failures eligible for warning email: {len(email_failures)}")
    print(f"PDF read/extraction failures logged only: {pdf_failures}")


if __name__ == "__main__":
    main()
