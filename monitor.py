import requests
from bs4 import BeautifulSoup
import hashlib
import os

URL = "https://www.syttende.dk/vinen"

STATE_FILE = "state.txt"

def hash_content(content):
    return hashlib.md5(content).hexdigest()

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r") as f:
        lines = f.read().splitlines()
    return dict(line.split("||") for line in lines if "||" in line)

def save_state(state):
    with open(STATE_FILE, "w") as f:
        for k, v in state.items():
            f.write(f"{k}||{v}\n")

# 1. Hent siden
html = requests.get(URL, timeout=30).text
soup = BeautifulSoup(html, "html.parser")

# 2. Find PDF-links
pdf_links = []
for a in soup.find_all("a"):
    href = a.get("href")
    if href and ".pdf" in href.lower():
        if href.startswith("/"):
            href = "https://www.syttende.dk" + href
        pdf_links.append(href)

print(f"Fundet PDF'er: {len(pdf_links)}")

# 3. Load tidligere state
old_state = load_state()
new_state = {}

changes = []

# 4. Download og sammenlign
for pdf in pdf_links:
    try:
        data = requests.get(pdf, timeout=30).content
        h = hash_content(data)

        new_state[pdf] = h

        if pdf not in old_state:
            changes.append(f"NY PDF: {pdf}")
        elif old_state[pdf] != h:
            changes.append(f"ÆNDRET PDF: {pdf}")

    except Exception as e:
        changes.append(f"FEJL ved {pdf}: {str(e)}")

# 5. Gem state
save_state(new_state)

# 6. Output (ses i GitHub Actions)
print("\n--- RESULTAT ---")
if changes:
    for c in changes:
        print("🔴", c)
else:
    print("🟢 Ingen ændringer")
