import sys
import os
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import json
import re

HTML_FILES = ["opinion.html", "shompadokiyo.html"]
XML_FILE = "articles.xml"
MAX_ITEMS = 500

# Bangladesh Standard Time (UTC+6)
BD_TZ = timezone(timedelta(hours=6))
NOW = datetime.now(timezone.utc)

def parse_and_format_date(date_input):
    """
    Translates Bengali dates, handles standard ISO/Epochs, and formats for RSS.
    Returns: (datetime_object, formatted_rss_string) or (None, None)
    """
    if not date_input:
        return None, None

    # 1. Handle raw timestamps if JSON provides them
    if isinstance(date_input, (int, float)):
        try:
            ts = float(date_input)
            if ts > 1e11: ts /= 1000.0
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt, dt.strftime("%a, %d %b %Y %H:%M:%S %z")
        except Exception:
            pass

    date_str = str(date_input).strip()
    
    # 2. Translate Bengali numerals to English numerals
    bengali_to_english_digits = str.maketrans('০১২৩৪৫৬৭৮৯', '0123456789')
    date_str = date_str.translate(bengali_to_english_digits)
    
    # 3. Map Bengali text to English equivalents & strip garbage chars
    replacements = {
        "জানুয়ারি": "Jan", "ফেব্রুয়ারি": "Feb", "মার্চ": "Mar", "এপ্রিল": "Apr",
        "মে": "May", "জুন": "Jun", "জুলাই": "Jul", "আগস্ট": "Aug",
        "সেপ্টেম্বর": "Sep", "অক্টোবর": "Oct", "নভেম্বর": "Nov", "ডিসেম্বর": "Dec",
        "এএম": "AM", "পিএম": "PM",
        "আপডেটঃ": "", "আপডেট:": "", "|": "", ",": ""
    }
    
    for bengali_word, english_word in replacements.items():
        date_str = date_str.replace(bengali_word, english_word)
        
    date_str = " ".join(date_str.split()) # Clean extra spaces

    # If it's a pure numeric string after translation
    if date_str.replace('.', '', 1).isdigit():
        try:
            ts = float(date_str)
            if ts > 1e11: ts /= 1000.0
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt, dt.strftime("%a, %d %b %Y %H:%M:%S %z")
        except Exception:
            pass

    dt = None
    
    # Try common formats
    formats = [
        "%d %b %Y %I:%M %p", # 14 Apr 2026 12:00 AM
        "%d %b %Y %H:%M",    # 05 Jun 2026 07:48
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%d %b %Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d"
    ]

    # Clean Z for ISO attempts
    clean_str = date_str.replace("Z", "+00:00")
    
    try:
        dt = datetime.fromisoformat(clean_str)
    except ValueError:
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                break
            except ValueError:
                continue

    if not dt:
        print(f"  [!] Could not parse cleaned date: {date_str} (Original: {date_input})")
        return None, None

    # Attach BD Timezone (+6) if none exists
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BD_TZ)

    # Format strictly for RSS
    rss_date_str = dt.strftime("%a, %d %b %Y %H:%M:%S %z")
    return dt, rss_date_str


def extract_articles_from_file(filepath):
    if not os.path.exists(filepath):
        print(f"Warning: {filepath} not found")
        return []

    print(f"\n--- Processing {filepath} ---")

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
        soup = BeautifulSoup(content, "html.parser")

    articles = []

    # 1. Try to extract from Nuxt JSON
    script_tag = soup.find("script", {"id": "__NUXT_DATA__", "type": "application/json"})
    if script_tag:
        try:
            json_data = json.loads(script_tag.string)

            def resolve_value(val, depth=0):
                if depth > 5: return val
                if isinstance(val, int) and 0 <= val < len(json_data):
                    resolved = json_data[val]
                    if isinstance(resolved, int) and resolved != val:
                        return resolve_value(resolved, depth + 1)
                    return resolved
                return val

            state_dict = None
            for item in json_data:
                if isinstance(item, dict) and "category_all_news" in item:
                    state_dict = item
                    break

            if state_dict:
                cat_ref = state_dict["category_all_news"]
                article_index_list = json_data[cat_ref] if isinstance(cat_ref, int) and 0 <= cat_ref < len(json_data) else []

                if isinstance(article_index_list, list):
                    for article_idx in article_index_list:
                        if not (isinstance(article_idx, int) and 0 <= article_idx < len(json_data)): continue

                        item = json_data[article_idx]
                        if not isinstance(item, dict) or "headline" not in item or "slug" not in item:
                            continue

                        slug = resolve_value(item.get("slug"))
                        title = resolve_value(item.get("headline"))
                        desc_raw = item.get("excerpt") or item.get("content")
                        desc = resolve_value(desc_raw) if desc_raw is not None else ""
                        pub_raw = resolve_value(item.get("published_at"))
                        img = resolve_value(item.get("thumb"))

                        slug = str(slug) if slug else ""
                        title = str(title) if title else ""
                        desc = str(desc) if desc else ""
                        img = str(img) if img else ""

                        # --- Robust Time Check Filter ---
                        dt, rss_pub_str = parse_and_format_date(pub_raw)
                        
                        if not dt or (NOW - dt) > timedelta(hours=25):
                            continue

                        is_valid_slug = (slug and not slug.isdigit() and len(slug) > 10 and slug.startswith("019"))
                        is_valid_title = (title and not title.isdigit() and len(title) > 5 and not title.startswith("http"))

                        if is_valid_slug and is_valid_title:
                            url = f"https://www.dainikamadershomoy.com/news/{slug}"
                            if len(desc) > 300: desc = desc[:297] + "..."
                            
                            articles.append({
                                "url": url, "title": title, "desc": desc, 
                                "pub": rss_pub_str, "img": img
                            })
                            print(f"Found valid recent article: {title[:50]}...")
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"Error parsing JSON data: {e}")

    # 2. Regex fallback if Nuxt fails
    if not articles:
        print("Trying fallback method - parsing from text patterns...")
        pattern = r'"headline":"([^"]+)"[^}]*"slug":"(019[^"]+)"[^}]*"thumb":"([^"]*)"[^}]*"published_at":"([^"]*)"'
        for match in re.finditer(pattern, content):
            title, slug, img, pub_raw = match.group(1), match.group(2), match.group(3), match.group(4)
            
            dt, rss_pub_str = parse_and_format_date(pub_raw)
            if not dt or (NOW - dt) > timedelta(hours=25):
                continue
                
            if title and slug and len(slug) > 10:
                url = f"https://www.dainikamadershomoy.com/news/{slug}"
                articles.append({
                    "url": url, "title": title, "desc": "", 
                    "pub": rss_pub_str, "img": img
                })
                print(f"Found valid recent article (regex): {title[:50]}...")

    return articles


# ── Collect ──────────────────────────────────────────────────────────────────
articles = []
seen_urls = set()

for html_file in HTML_FILES:
    file_articles = extract_articles_from_file(html_file)
    for art in file_articles:
        if art["url"] not in seen_urls:
            articles.append(art)
            seen_urls.add(art["url"])

print(f"\n=== Summary ===")
print(f"Total recent unique articles collected: {len(articles)}")

# ── XML merge ─────────────────────────────────────────────────────────────────
if os.path.exists(XML_FILE):
    try:
        tree = ET.parse(XML_FILE)
        root = tree.getroot()
    except ET.ParseError:
        root = ET.Element("rss", version="2.0")
else:
    root = ET.Element("rss", version="2.0")

channel = root.find("channel")
if channel is None:
    channel = ET.SubElement(root, "channel")
    ET.SubElement(channel, "title").text = "Dainik Amader Shomoy Opinion"
    ET.SubElement(channel, "link").text = "https://www.dainikamadershomoy.com/category/all/opinion"
    ET.SubElement(channel, "description").text = "Latest opinion articles from Dainik Amader Shomoy"

existing = {
    item.find("link").text.strip()
    for item in channel.findall("item")
    if item.find("link") is not None
}

new_count = 0
for art in articles:
    fixed_url = art["url"].replace("/news/", "/details/")
    if fixed_url in existing:
        continue

    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = str(art["title"])
    ET.SubElement(item, "link").text = fixed_url
    ET.SubElement(item, "description").text = str(art["desc"])
    ET.SubElement(item, "pubDate").text = str(art["pub"]) # Now injecting standard RSS string
    
    if art["img"]:
        ET.SubElement(item, "enclosure", url=str(art["img"]), type="image/jpeg")
    new_count += 1

print(f"\nAdded {new_count} new articles to XML")

all_items = channel.findall("item")
if len(all_items) > MAX_ITEMS:
    for old_item in all_items[:-MAX_ITEMS]:
        channel.remove(old_item)

tree = ET.ElementTree(root)
tree.write(XML_FILE, encoding="utf-8", xml_declaration=True)
print(f"XML saved with {len(channel.findall('item'))} total articles")