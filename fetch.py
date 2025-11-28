import requests
import sys

FLARESOLVERR_URL = "http://localhost:8191/v1"

# Define multiple target URLs
TARGETS = {
    "opinion": "https://www.dainikamadershomoy.com/category/all/opinion",
    "shompadokiyo": "https://www.dainikamadershomoy.com/category/all/shompadokiyo"
}

def fetch_url(url, filename):
    """Fetch a URL using FlareSolverr and save to file"""
    payload = {
        "cmd": "request.get",
        "url": url,
        "maxTimeout": 60000
    }
    
    print(f"Fetching {url}...")
    r = requests.post(FLARESOLVERR_URL, json=payload)
    data = r.json()
    
    # If FlareSolverr returns an error field, expose it
    if "error" in data:
        print(f"FlareSolverr error for {filename}: {data['error']}")
        return False
    
    # If FlareSolverr fails silently
    if "solution" not in data or "response" not in data["solution"]:
        print(f"Invalid FlareSolverr response for {filename}: {data}")
        return False
    
    html = data["solution"]["response"]
    
    with open(f"{filename}.html", "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"Successfully saved to {filename}.html")
    return True

# Fetch all targets
success_count = 0
for name, url in TARGETS.items():
    if fetch_url(url, name):
        success_count += 1

print(f"\nCompleted: {success_count}/{len(TARGETS)} files fetched successfully")

if success_count < len(TARGETS):
    sys.exit(1)