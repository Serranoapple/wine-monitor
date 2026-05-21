import requests
from bs4 import BeautifulSoup
import pdfplumber
import tempfile
import os
import json
import re
import smtplib

from email.mime.text import MIMEText
from datetime import datetime

URL = "https://www.syttende.dk/vinen"

STATE_FILE = "wine_structured_state.json"

EMAIL_FROM = os.environ["EMAIL_FROM"]
EMAIL_TO = os.environ["EMAIL_TO"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]


def send_email(subject, body):

    msg = MIMEText(body, "plain", "utf-8")

    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    with smtplib.SMTP("smtp.gmail.com", 587) as server:

        server.starttls()

        server.login(
            EMAIL_FROM,
            EMAIL_PASSWORD
        )

        server.send_message(msg)


def format_price(price):

    # 1495 -> 1.495
    return f"{price:,}".replace(",", ".")


def extract_pdf_text(pdf_bytes, pdf_url):

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".pdf"
    ) as tmp:

        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    text = ""

    try:

        with pdfplumber.open(tmp_path) as pdf:

            for page in pdf.pages:

                page_text = page.extract_text()

                if page_text:
                    text += page_text + "\n"

    finally:

        os.remove(tmp_path)

    upper_url = pdf_url.upper()

    # Filtrér relevante sektioner
    if "HVIDVIN" in upper_url:

        start_keywords = [
            "HVIDVIN"
        ]

        stop_keywords = [
            "RØDVIN",
            "ROSÉ",
            "AVEC"
        ]

    elif "RØD" in upper_url:

        start_keywords = [
            "RØDVIN",
            "ROSÉ"
        ]

        stop_keywords = [
            "AVEC"
        ]

    elif "BOBLER" in upper_url:

        start_keywords = [
            "CHAMPAGNE",
            "BOBLER"
        ]

        stop_keywords = [
            "HVIDVIN",
            "RØDVIN"
        ]

    else:

        return text

    lines = text.splitlines()

    filtered = []

    active = False

    for line in lines:

        upper = line.upper()

        if any(k in upper for k in start_keywords):
            active = True

        if any(k in upper for k in stop_keywords):
            active = False

        if active:
            filtered.append(line)

    return "\n".join(filtered)


def clean_wine_name(name):

    # Fjern ekstra spacing
    name = re.sub(
        r'\s+',
        ' ',
        name
    )

    # Fix spacing omkring årstal
    name = re.sub(
        r'((19|20)\d{2})([A-Z])',
        r'\1 \3',
        name
    )

    # Fjern mærkelige tegn
    name = name.strip(
        " -–—|:"
    )

    return name.strip()


def parse_wines(text):

    wines = {}

    lines = text.splitlines()

    for line in lines:

        line = line.strip()

        if len(line) < 15:
            continue

        upper = line.upper()

        # Ignorér overskrifter
        if upper in [
            "HVIDVIN",
            "RØDVIN",
            "ROSÉ",
            "BOBLER",
            "CHAMPAGNE",
            "SØDT",
            "AVEC"
        ]:
            continue

        # Find alle talblokke
        matches = re.findall(
            r'[\d\.,]+',
            line
        )

        if not matches:
            continue

        possible_prices = []

        for m in matches:

            clean = re.sub(
                r'[^\d]',
                '',
                m
            )

            if not clean:
                continue

            try:

                num = int(clean)

            except:
                continue

            # Ignorér årgange
            if 1900 <= num <= 2030:
                continue

            # Sandsynlige priser
            if 100 <= num <= 50000:

                possible_prices.append(
                    (num, m)
                )

        if not possible_prices:
            continue

        # Brug største tal som pris
        price, raw_price = max(
            possible_prices,
            key=lambda x: x[0]
        )

        wine_name = line.replace(
            raw_price,
            ""
        )

        wine_name = clean_wine_name(
            wine_name
        )

        if len(wine_name) < 5:
            continue

        wines[wine_name] = price

    return wines


def load_state():

    if not os.path.exists(STATE_FILE):
        return {}

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except:

        return {}


def save_state(state):

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            state,
            f,
            indent=2,
            ensure_ascii=False
        )


def get_pretty_pdf_name(pdf_url):

    pdf_name = (
        pdf_url
        .split("/")[-1]
        .replace(".pdf", "")
    )

    pdf_name = requests.utils.unquote(
        pdf_name
    )

    upper = pdf_name.upper()

    if "HVIDVIN" in upper:
        return "HVIDVIN"

    elif "RØD" in upper:
        return "ROSÉ & RØDVIN"

    elif "BOBLER" in upper:
        return "BOBLER & SØDT"

    elif "AVEC" in upper:
        return "AVEC"

    return pdf_name


# Hent hjemmeside
html = requests.get(
    URL,
    timeout=30
).text

soup = BeautifulSoup(
    html,
    "html.parser"
)

# Find PDF-links
pdf_links = []

for a in soup.find_all("a"):

    href = a.get("href")

    if href and ".pdf" in href.lower():

        if href.startswith("/"):
            href = (
                "https://www.syttende.dk"
                + href
            )

        pdf_links.append(href)

# Fjern dubletter
pdf_links = list(
    dict.fromkeys(pdf_links)
)

print(f"Fundet PDF'er: {len(pdf_links)}")

# Load state
old_state = load_state()

new_state = {}

report = []

for pdf_url in pdf_links:

    try:

        print(f"Scanner: {pdf_url}")

        pdf_data = requests.get(
            pdf_url,
            timeout=30
        ).content

        text = extract_pdf_text(
            pdf_data,
            pdf_url
        )

        wines = parse_wines(
            text
        )

        new_state[pdf_url] = wines

        old_wines = old_state.get(
            pdf_url,
            {}
        )

        added = []
        removed = []
        changed = []

        # Nye vine
        for wine, price in wines.items():

            if wine not in old_wines:

                added.append(
                    f"• {wine} — {format_price(price)} kr."
                )

        # Fjernede vine
        for wine in old_wines:

            if wine not in wines:

                removed.append(
                    f"• {wine}"
                )

        # Prisændringer
        for wine, price in wines.items():

            if wine in old_wines:

                old_price = old_wines[wine]

                if old_price != price:

                    changed.append(
                        f"• {wine}\n"
                        f"  {format_price(old_price)} → "
                        f"{format_price(price)} kr."
                    )

        if added or removed or changed:

            pdf_name = get_pretty_pdf_name(
                pdf_url
            )

            report.append(
                "\n"
                + "=" * 50
            )

            report.append(
                f"\n🍷 {pdf_name}\n"
            )

            if added:

                report.append(
                    "\n🆕 NYE VINE"
                )

                report.extend(
                    added[:25]
                )

            if changed:

                report.append(
                    "\n💰 PRISÆNDRINGER"
                )

                report.extend(
                    changed[:25]
                )

            if removed:

                report.append(
                    "\n❌ FJERNEDE"
                )

                report.extend(
                    removed[:25]
                )

            report.append(
                f"\n🔗 LINK:\n{pdf_url}\n"
            )

    except Exception as e:

        report.append(
            "\n"
            + "=" * 50
        )

        report.append(
            f"\nFEJL I:\n{pdf_url}\n"
        )

        report.append(
            str(e)
        )

# Gem ny state
save_state(new_state)

# Send mail hvis ændringer
if report:

    body = "\n".join(report)

    body += (
        f"\n\nKontrolleret: "
        f"{datetime.now()}"
    )

    send_email(
        "🍷 Restaurant 17 vinkort ændringer",
        body
    )

    print("Mail sendt")

else:

    print("Ingen ændringer")
