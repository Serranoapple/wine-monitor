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

    msg = MIMEText(body)

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


def extract_pdf_text(pdf_bytes):

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

    return text


def parse_wines(text):

    wines = {}

    lines = text.splitlines()

    for line in lines:

        line = line.strip()

        if len(line) < 10:
            continue

        # Find alle tal
        numbers = re.findall(
            r'\d[\d\.\s]{1,10}',
            line
        )

        if not numbers:
            continue

        # Brug sidste tal som pris
        raw_price = numbers[-1]

        # Rens pris
        clean_price = re.sub(
            r'[^\d]',
            '',
            raw_price
        )

        if not clean_price:
            continue

        try:

            price = int(clean_price)

        except:
            continue

        # Ignorér usandsynlige priser
        if price < 100 or price > 50000:
            continue

        # Fjern pris fra navn
        wine_name = line.replace(
            raw_price,
            ""
        ).strip()

        # Fjern dobbelte spaces
        wine_name = re.sub(
            r'\s+',
            ' ',
            wine_name
        )

        # Fjern ensomme årstal i starten
        wine_name = re.sub(
            r'^(19|20)\d{2}\s+',
            '',
            wine_name
        )

        # Ignorér korte navne
        if len(wine_name) < 5:
            continue

        wines[wine_name] = price

    return wines


def load_state():

    if not os.path.exists(STATE_FILE):
        return {}

    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state):

    with open(STATE_FILE, "w") as f:
        json.dump(
            state,
            f,
            indent=2
        )


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

# Load tidligere state
old_state = load_state()

new_state = {}

report = []

for pdf_url in pdf_links:

    try:

        pdf_data = requests.get(
            pdf_url,
            timeout=30
        ).content

        text = extract_pdf_text(pdf_data)

        wines = parse_wines(text)

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
                    f"• {wine} — {price:,} kr."
                )

        # Fjernede vine
        for wine, price in old_wines.items():

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
                        f"  {old_price:,} → {price:,} kr."
                    )

        if added or removed or changed:

            pdf_name = (
                pdf_url
                .split("/")[-1]
                .replace(".pdf", "")
                .replace("_", " ")
            )

            report.append(
                f"\n🍷 ÆNDRINGER\n"
                f"📄 {pdf_name}\n"
            )

            if added:

                report.append(
                    "\n🆕 NYE VINE"
                )

                report.extend(
                    added[:20]
                )

            if changed:

                report.append(
                    "\n💰 PRISÆNDRINGER"
                )

                report.extend(
                    changed[:20]
                )

            if removed:

                report.append(
                    "\n❌ FJERNEDE"
                )

                report.extend(
                    removed[:20]
                )

            report.append(
                f"\n🔗 LINK:\n{pdf_url}\n"
            )

    except Exception as e:

        report.append(
            f"\nFEJL:\n"
            f"{pdf_url}\n"
            f"{str(e)}\n"
        )

# Gem ny state
save_state(new_state)

# Send mail
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
