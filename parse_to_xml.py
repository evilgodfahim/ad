import sys
import os
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import json
import re

HTML_FILES = ["opinion.html", "shompadokiyo.html"]
XML_FILE = "articles.xml"
MAX_ITEMS = 500

def extract_articles_from_file(filepath):
    if not os.path.exists(filepath):
        print(f"Warning: {filepath} not found")
        return []

    print(f"\n--- Processing {filepath} ---")

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
        soup = BeautifulSoup(content, "html.parser")

    articles = []

    script_tag = soup.find("script", {"id": "__NUXT_DATA__", "type": "application/json"})
    if script_tag:
        try:
            json_data = json.loads(script_tag.string)

            def resolve_value(val, depth=0):
                if depth > 5:
                    return val
                if isinstance(val, int) and 0 <= val < len(json_data):
                    resolved = json_data[val]
                    if isinstance(resolved, int) and resolved != val:
                        return resolve_value(resolved, depth + 1)
                    return resolved
                return val

            for i, item in enumerate(json_data):
                if isinstance(item, dict) and "headline" in item and "slug" in item:
                    slug_val = item.get("slug")
                    title_val = item.get("headline")
                    desc_val = item.get("excerpt") or item.get("content")
                    pub_val = item.get("published_at")
                    img_val = item.get("thumb")

                    slug = resolve_value(slug_val)
                    title = resolve_value(title_val)
                    desc = resolve_value(desc_val) if desc_val else ""
                    pub = resolve_value(pub_val)
                    img = resolve_value(img_val)

                    slug = str(slug) if slug else ""
                    title = str(title) if title else ""
                    desc = str(desc) if desc else ""
                    pub = str(pub) if pub else ""
                    img = str(img) if img else ""

                    is_valid_slug = (
                        slug and 
                        not slug.isdigit() and 
                        len(slug) > 10 and 
                        slug.startswith("019a")
                    )

                    is_valid_title = (
                        title and 
                        not title.isdigit() and 
                        len(title) > 5 and
                        not title.startswith("http")
                    )

                    if is_valid_slug and is_valid_title:
                        url = f"https://www.dainikamadershomoy.com/news/{slug}"

                        if len(desc) > 300:
                            desc = desc[:297] + "..."

                        articles.append({
                            "url": url,
                            "title": title,
                            "desc": desc,
                            "pub": pub,
                            "img": img
                        })
                        print(f"Found article: {title[:50]}...")

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"Error parsing JSON data: {e}")

    if not articles:
        print("Trying fallback method - parsing from text patterns...")

        patterns = [
            (r'"headline":"([^"]+)"[^}]*"slug":"(019a[^"]+)"[^}]*"thumb":"([^"]+)"[^}]*"published_at":"([^"]+)"', 1, 2, 3, 4),
        ]

        for pattern, title_idx, slug_idx, img_idx, pub_idx in patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                title = match.group(title_idx)
                slug = match.group(slug_idx)
                img = match.group(img_idx)
                pub = match.group(pub_idx)

                if title and slug and len(slug) > 10:
                    url = f"https://www.dainikamadershomoy.com/news/{slug}"
                    articles.append({
                        "url": url,
                        "title": title,
                        "desc": "",
                        "pub": pub,
                        "img": img
                    })
                    print(f"Found article (regex): {title[:50]}...")

    return articles


articles_by_file = {}

for html_file in HTML_FILES:
    file_articles = extract_articles_from_file(html_file)
    articles_by_file[html_file] = file_articles


url_sets = {}
for filename, arts in articles_by_file.items():
    url_sets[filename] = set(art["url"] for art in arts)


all_urls = set()
for urls in url_sets.values():
    all_urls.update(urls)

url_counts = {}
for url in all_urls:
    count = sum(1 for urls in url_sets.values() if url in urls)
    url_counts[url] = count

common_urls = {url for url, count in url_counts.items() if count > 1}

print(f"\nCommon URLs found in multiple files: {len(common_urls)}")
for url in common_urls:
    print(f"  - {url}")

unique_articles = []
eliminated_count = 0

for filename, arts in articles_by_file.items():
    for art in arts:
        if art["url"] in common_urls:
            eliminated_count += 1
            print(f"Eliminated common article: {art['title'][:50]}...")
        elif art["url"] not in [a["url"] for a in unique_articles]:
            unique_articles.append(art)

articles = unique_articles

print(f"\n=== Summary ===")
total_found = sum(len(arts) for arts in articles_by_file.values())
print(f"Total articles found: {total_found}")
print(f"Common articles eliminated: {eliminated_count}")
print(f"Unique articles kept: {len(articles)}")

if not articles:
    print("WARNING: No articles found! Check HTML structure.")


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


existing = set()
for item in channel.findall("item"):
    link_tag = item.find("link")
    if link_tag is not None:
        existing.add(link_tag.text.strip())


new_count = 0
for art in articles:
    if art["url"] in existing:
        continue

    fixed_url = art["url"].replace("/news/", "/details/")

    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = str(art["title"])
    ET.SubElement(item, "link").text = fixed_url
    ET.SubElement(item, "description").text = str(art["desc"])
    ET.SubElement(item, "pubDate").text = (
        str(art["pub"]) if art["pub"] else
        datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    )
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