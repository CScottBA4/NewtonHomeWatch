import hashlib
import json
import os
import re
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

import fitz  # PyMuPDF
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

ALLOWED_NEWTON_HOSTS = {
    "newtonma.gov",
    "www.newtonma.gov",
    "apps2.newtonma.gov",
    "gisweb.newtonma.gov",
}

PROPERTY_TERMS = [
    "162 Clark Street",
    "162 Clark St",
    "162 Clark St.",
    "62023 0003",
    "62023-0003",
]

STREET_TERMS = [
    "Clark Street",
    "Clark St",
    "Clark St.",
]

RELEVANT_LINK_KEYWORDS = [
    "agenda",
    "minutes",
    "meeting",
    "notice",
    "docket",
    "packet",
    "calendar",
    "hearing",
    "planning",
    "zoning",
    "land use",
    "permit",
    "inspection",
    "public works",
    "traffic",
    "committee",
    "board",
    "commission",
    "archive",
    "archives",
    "public safety",
    "transportation",
    "public facilities",
    "engineering",
    "construction",
    "sidewalk",
    "special permit",
    "variance",
    "development",
    "historic",
    "assessor",
    "assessing",
    "gis",
]

OFFICIAL_PORTALS = {
    "Newton permit / NewGov search": "https://newtonma.portal.opengov.com/search",
    "Newton GIS Browser": "https://gisweb.newtonma.gov/browser.html",
    "Newton Assessor information": "https://www.newtonma.gov/Home/Components/ServiceDirectory/ServiceDirectory/28/",
}

PROPERTY_START_URLS = [
    "https://www.newtonma.gov/government/city-clerk/city-council/electronic-posting-board",
    "https://www.newtonma.gov/government/city-clerk/city-council",
    "https://www.newtonma.gov/how-do-i/view/city-council-dockets",
    "https://www.newtonma.gov/government/city-clerk/city-council/friday-packet",
    "https://www.newtonma.gov/government/planning",
    "https://www.newtonma.gov/government/planning/development-projects",
    "https://www.newtonma.gov/government/planning/development-review/special-permits-land-use",
    "https://www.newtonma.gov/government/planning/zoning-board-of-appeals",
    "https://www.newtonma.gov/government/inspectional-services",
    "https://www.newtonma.gov/government/public-works/engineering",
    "https://www.newtonma.gov/government/information-technology/gis",
    "https://www.newtonma.gov/government/planning/historic-preservation",
]

STREET_START_URLS = [
    "https://www.newtonma.gov/government/city-clerk/city-council/electronic-posting-board",
    "https://www.newtonma.gov/how-do-i/view/city-council-dockets",
    "https://www.newtonma.gov/government/city-clerk/city-council/friday-packet",
    "https://www.newtonma.gov/government/city-clerk/city-council/calendar-news/calendar",
    "https://www.newtonma.gov/government/planning",
    "https://www.newtonma.gov/government/planning/development-projects",
    "https://www.newtonma.gov/government/planning/development-review/special-permits-land-use",
    "https://www.newtonma.gov/government/planning/zoning-board-of-appeals",
    "https://www.newtonma.gov/government/public-works",
    "https://www.newtonma.gov/government/public-works/engineering",
]

HISTORY_START_URLS = [
    "https://www.newtonma.gov/government/planning/historic-preservation",
    "https://www.newtonma.gov/government/information-technology/gis",
    "https://www.newtonma.gov/Home/Components/ServiceDirectory/ServiceDirectory/28/",
    "https://www.newtonma.gov/government/city-clerk/city-council/friday-packet",
    "https://www.newtonma.gov/how-do-i/view/city-council-dockets",
    "https://www.newtonma.gov/government/planning/development-review/special-permits-land-use",
]

DEFAULT_MAX_PAGES = 300
DEFAULT_MAX_PDFS = 450
CONTEXT_WINDOW = 350
MAX_EMAIL_ITEMS = 20
MAX_FAILURES_IN_EMAIL = 20

DATE_PATTERNS = [
    re.compile(
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
        r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
        r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+\d{4}\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
]


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_url(url):
    url, _ = urldefrag(url)
    return url.strip()


def is_allowed_url(url):
    try:
        host = (urlparse(url).hostname or "").lower()
        return host in ALLOWED_NEWTON_HOSTS
    except Exception:
        return False


def is_pdf_url(url):
    clean = url.lower().split("?")[0]
    return (
        clean.endswith(".pdf")
        or "/home/showpublisheddocument/" in clean
        or "friday%20packet%20archives" in clean
    )


def looks_relevant(text, url):
    combined = f"{text} {url}".lower()
    return any(keyword in combined for keyword in RELEVANT_LINK_KEYWORDS)


def fetch(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/18.6 Safari/605.1.15"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "application/pdf,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Referer": "https://www.newtonma.gov/",
    }
    response = requests.get(url, headers=headers, timeout=45)
    response.raise_for_status()
    return response


def extract_page(url):
    response = fetch(url)
    soup = BeautifulSoup(response.text, "html.parser")

    title = soup.title.get_text(" ", strip=True) if soup.title else url
    text = soup.get_text(" ", strip=True)

    pages = []
    pdfs = []

    for anchor in soup.find_all("a", href=True):
        href = normalize_url(urljoin(url, anchor["href"]))
        anchor_text = anchor.get_text(" ", strip=True)

        if not is_allowed_url(href):
            continue

        if is_pdf_url(href):
            pdfs.append((anchor_text or "Newton document", href))
        elif looks_relevant(anchor_text, href):
            pages.append(href)

    return title, text, pages, pdfs


def extract_pdf_text(url):
    response = fetch(url)
    parts = []

    with fitz.open(stream=response.content, filetype="pdf") as document:
        for page in document:
            parts.append(page.get_text() or "")

    return "\n".join(parts)


def crawl(start_urls, max_pages=DEFAULT_MAX_PAGES, max_pdfs=DEFAULT_MAX_PDFS):
    """Crawl relevant Newton pages and PDFs."""
    pages_to_visit = [normalize_url(url) for url in start_urls]
    visited_pages = set()
    queued_pdfs = set()
    pdf_queue = []
    records = []
    failures = []

    while pages_to_visit and len(visited_pages) < max_pages:
        url = pages_to_visit.pop(0)

        if url in visited_pages:
            continue

        visited_pages.add(url)
        print(f"Checking webpage: {url}", flush=True)

        try:
            title, text, pages, pdfs = extract_page(url)
        except Exception as exc:
            failures.append({"kind": "webpage", "url": url, "error": repr(exc)})
            continue

        records.append(
            {"title": title, "url": url, "text": text, "source_type": "webpage"}
        )

        for page in pages:
            if page not in visited_pages and page not in pages_to_visit:
                pages_to_visit.append(page)

        for pdf_title, pdf_url in pdfs:
            if pdf_url not in queued_pdfs:
                queued_pdfs.add(pdf_url)
                pdf_queue.append((pdf_title, pdf_url))

    visited_pdfs = set()

    for title, pdf_url in pdf_queue:
        if len(visited_pdfs) >= max_pdfs:
            break
        if pdf_url in visited_pdfs:
            continue

        visited_pdfs.add(pdf_url)
        print(f"Checking PDF/document: {pdf_url}", flush=True)

        try:
            text = extract_pdf_text(pdf_url)
        except Exception as exc:
            failures.append(
                {"kind": "pdf/document", "url": pdf_url, "error": repr(exc)}
            )
            continue

        if not text.strip():
            failures.append(
                {
                    "kind": "pdf/document unreadable",
                    "url": pdf_url,
                    "error": (
                        "No extractable text found. This may be an image-only "
                        "or scanned PDF that would require OCR."
                    ),
                }
            )
            continue

        records.append(
            {"title": title, "url": pdf_url, "text": text, "source_type": "pdf"}
        )

    stats = {
        "visited_pages": len(visited_pages),
        "queued_pdfs": len(queued_pdfs),
        "visited_pdfs": len(visited_pdfs),
        "records_readable": len(records),
        "failures": len(failures),
    }

    return records, failures, stats


def _spans_overlap(start, end, selected_spans):
    return any(
        start < other_end and end > other_start
        for other_start, other_end in selected_spans
    )


def find_contexts(text, terms, window=CONTEXT_WINDOW):
    """Extract de-duplicated snippets around matches."""
    selected_spans = []
    raw_matches = []

    for term in sorted(set(terms), key=len, reverse=True):
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        for match in pattern.finditer(text):
            if _spans_overlap(match.start(), match.end(), selected_spans):
                continue
            selected_spans.append((match.start(), match.end()))
            raw_matches.append((match.start(), match.end(), term))

    contexts = []
    seen = set()

    for start_idx, end_idx, _term in sorted(raw_matches):
        start = max(0, start_idx - window)
        end = min(len(text), end_idx + window)
        context = re.sub(r"\s+", " ", text[start:end]).strip()

        if context and context not in seen:
            seen.add(context)
            contexts.append(context)

    return contexts


def contains_any(text, terms):
    lower = text.lower()
    return any(term.lower() in lower for term in terms)


def clean_excerpt(text, max_chars=650):
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= max_chars:
        return clean
    clipped = clean[:max_chars].rsplit(" ", 1)[0]
    return clipped + "…"


def extract_date(title, text):
    sample = f"{title}\n{text[:5000]}"
    for pattern in DATE_PATTERNS:
        match = pattern.search(sample)
        if match:
            return match.group(0)
    return ""


def classify_record(title, url, text):
    sample = f"{title} {url} {text[:2500]}".lower()

    categories = [
        ("Permit / Inspection", ["permit", "inspection", "newgov", "opengov"]),
        (
            "Zoning / Land Use",
            ["zoning", "variance", "special permit", "land use", "zba"],
        ),
        ("Planning / Development", ["planning", "development", "site plan"]),
        (
            "Public Works / Infrastructure",
            [
                "public works",
                "engineering",
                "sidewalk",
                "traffic",
                "road",
                "street",
                "construction",
                "utility",
                "eversource",
                "verizon",
                "sewer",
                "water",
            ],
        ),
        (
            "Historic / Preservation",
            ["historic", "landmark", "preservation", "demolition"],
        ),
        ("Assessing / GIS", ["assessor", "assessing", "gis", "parcel"]),
        (
            "City Council / Meeting",
            ["council", "agenda", "minutes", "docket", "committee"],
        ),
    ]

    for category, keywords in categories:
        if any(keyword in sample for keyword in keywords):
            return category

    return "Other city record"


def context_fingerprint(contexts):
    normalized = "\n---\n".join(
        sorted(re.sub(r"\s+", " ", c).strip() for c in contexts)
    )
    return hashlib.sha256(normalized.encode()).hexdigest()


def stable_key(*parts):
    joined = "|".join(str(part) for part in parts)
    return hashlib.sha256(joined.encode()).hexdigest()


def load_json(path, default):
    path = Path(path)
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)


def send_email(subject, body):
    required = ["ALERT_EMAIL_TO", "SMTP_USER", "SMTP_PASSWORD"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Missing required email environment variable(s): " + ", ".join(missing)
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ["SMTP_USER"]
    msg["To"] = os.environ["ALERT_EMAIL_TO"]
    msg.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(msg)


def portal_links_text():
    lines = ["Official property portals:"]
    for name, url in OFFICIAL_PORTALS.items():
        lines.append(f"- {name}: {url}")
    return "\n".join(lines)


def failure_fingerprint(failures):
    if not failures:
        return ""
    material = "\n".join(
        sorted(
            f"{item['kind']}|{item['url']}|{item['error']}" for item in failures
        )
    )
    return hashlib.sha256(material.encode()).hexdigest()


def maybe_email_failures(label, failures, state):
    """Email a warning only when the set of failures changes."""
    current = failure_fingerprint(failures)
    previous = state.get("failure_fingerprint", "")

    if current == previous:
        return False

    state["failure_fingerprint"] = current

    if not failures:
        return True

    lines = [
        f"NewtonHomeWatch encountered {len(failures)} read/crawl failure(s) during {label}.",
        "",
        "The rest of the monitor continued. These warnings matter because a failed",
        "source could contain an item the monitor was unable to inspect.",
        "",
    ]

    for failure in failures[:MAX_FAILURES_IN_EMAIL]:
        lines.extend(
            [
                f"{failure['kind']}: {failure['url']}",
                f"Error: {failure['error']}",
                "",
            ]
        )

    if len(failures) > MAX_FAILURES_IN_EMAIL:
        lines.append(
            f"{len(failures) - MAX_FAILURES_IN_EMAIL} additional failure(s) omitted."
        )

    send_email(
        f"[NewtonHomeWatch - Warning] {label}: {len(failures)} source failure(s)",
        "\n".join(lines),
    )
    return True
