import requests
from bs4 import BeautifulSoup
import hashlib
import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

URL = "https://www.syttende.dk/vinen"

STATE_FILE = "state.txt"

EMAIL_FROM = os.environ["EMAIL_FROM"]
EMAIL_TO = os.environ["EMAIL_TO"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]

def hash_content(content):
    return hashlib.md5(content).hexdigest()

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}

    with open(STATE_FILE, "r") as f:
        lines = f.read().splitlines()

    return dict(
        line.split("||")
        for line in lines
        if "||" in line
    )

def save_state(state):
    with open(STATE_FILE, "w") as f:
        for k, v in state.items():
            f.write(f"{k}||{v}\n")

def send_email(subject, body):

    msg = MIMEText(body)

    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.send_message(msg)

# Hent hjemmeside
html = requests.get(URL, timeout=30).text
soup = BeautifulSoup(html, "html.parser")

# Find PDF-links
pdf_links = []

for a in soup.find_all("a"):
    href = a.get("href")

    if href and ".pdf" in href.lower():

        if href.startswith("/"):
            href = "https://www.syttende.dk" + href

        pdf_links.append(href)

print(f"Fundet PDF'er: {len(pdf_links)}")

# Load gammel state
old_state = load_state()
new_state = {}

changes = []

# Tjek PDF'er
for pdf in pdf_links:

    try:

        data = requests.get(pdf, timeout=30).content

        h = hash_content(data)

        new_state[pdf] = h

        if pdf not in old_state:
            changes.append(f"NY PDF:\n{pdf}\n")

        elif old_state[pdf] != h:
            changes.append(f"ÆNDRET PDF:\n{pdf}\n")

    except Exception as e:

        changes.append(f"FEJL:\n{pdf}\n{str(e)}\n")

# Gem ny state
save_state(new_state)

# Send mail hvis ændringer
if changes:

    body = "\n".join(changes)

    body += f"\n\nKontrolleret: {datetime.now()}"

    send_email(
        "🍷 Restaurant 17 vinkort ændret",
        body
    )

    print("Mail sendt")

else:

    print("Ingen ændringer")
