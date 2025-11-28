import sys
import os
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from datetime import datetime
import json
import re

HTML_FILE = "opinion.html"
XML_FILE = "articles.xml"
MAX_ITEMS = 500

# Load HTML
if not os.path.exists(HTML_FILE):
    print("HTML not found")
    sys.exit(1)

with open(HTML_FILE, "r", encoding="utf-8") as f:
    content = f.read()
    soup = BeautifulSoup(content, "html.parser")

articles = []

# --- Extract from JSON data embedded in the page ---
# Find the script tag containing article data
script_tag = soup.find("script", {"id": "__NUXT_DATA__", "type": "application/json"})
if script_tag:
    try:
        json_data = json.loads(script_tag.string)
        
        # Navigate through the JSON structure to find articles
        # The articles are in the category_all_news section
        if isinstance(json_data, list) and len(json_data) > 1:
            data_dict = json_data[1]
            
            # Find article entries in the JSON
            for i, item in enumerate(json_data):
                if isinstance(item, dict):
                    # Look for article data structure
                    if "headline" in item and "slug" in item:
                        slug = item.get("slug", "")
                        title = item.get("headline", "")
                        desc = item.get("excerpt", "") or item.get("content", "")[:200]
                        pub = item.get("published_at", "")
                        img = item.get("thumb", "")
                        
                        if title and slug:
                            url = f"https://www.dainikamadershomoy.com/news/{slug}"
                            
                            # Truncate description if too long
                            if len(desc) > 300:
                                desc = desc[:297] + "..."
                            
                            articles.append({
                                "url": url,
                                "title": title,
                                "desc": desc,
                                "pub": pub,
                                "img": img
                            })
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"Error parsing JSON data: {e}")

# --- Fallback: Extract from HTML structure ---
if not articles:
    # Look for article links in the HTML
    for link in soup.find_all("a", href=re.compile(r"/news/\w+")):
        url = link.get("href", "")
        if not url.startswith("http"):
            url = "https://www.dainikamadershomoy.com" + url
        
        # Try to find title (headline)
        title = None
        h1 = link.find("h1")
        h2 = link.find("h2")
        h3 = link.find("h3")
        
        if h1:
            title = h1.get_text(strip=True)
        elif h2:
            title = h2.get_text(strip=True)
        elif h3:
            title = h3.get_text(strip=True)
        
        if not title:
            continue
        
        # Try to find description
        desc = ""
        p_tag = link.find("p")
        if p_tag:
            desc = p_tag.get_text(strip=True)
        
        # Try to find publication date
        pub = ""
        pub_tag = link.find(class_=re.compile(r"(date|time|publish)"))
        if pub_tag:
            pub = pub_tag.get_text(strip=True)
        
        # Try to find image
        img = ""
        img_tag = link.find("img")
        if img_tag:
            img = img_tag.get("src", "")
        
        articles.append({
            "url": url,
            "title": title,
            "desc": desc,
            "pub": pub,
            "img": img
        })

# Remove duplicates based on URL
seen_urls = set()
unique_articles = []
for art in articles:
    if art["url"] not in seen_urls:
        seen_urls.add(art["url"])
        unique_articles.append(art)

articles = unique_articles

print(f"Found {len(articles)} articles")

# --- Load or create XML ---
if os.path.exists(XML_FILE):
    try:
        tree = ET.parse(XML_FILE)
        root = tree.getroot()
    except ET.ParseError:
        root = ET.Element("rss", version="2.0")
else:
    root = ET.Element("rss", version="2.0")

# Ensure channel exists
channel = root.find("channel")
if channel is None:
    channel = ET.SubElement(root, "channel")
    ET.SubElement(channel, "title").text = "Dainik Amader Shomoy Opinion"
    ET.SubElement(channel, "link").text = "https://www.dainikamadershomoy.com/category/all/opinion"
    ET.SubElement(channel, "description").text = "Latest opinion articles from Dainik Amader Shomoy"

# Deduplicate existing URLs
existing = set()
for item in channel.findall("item"):
    link_tag = item.find("link")
    if link_tag is not None:
        existing.add(link_tag.text.strip())

# Append new unique articles
new_count = 0
for art in articles:
    if art["url"] in existing:
        continue
    
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = art["title"]
    ET.SubElement(item, "link").text = art["url"]
    ET.SubElement(item, "description").text = art["desc"]
    ET.SubElement(item, "pubDate").text = art["pub"] if art["pub"] else datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
    if art["img"]:
        ET.SubElement(item, "enclosure", url=art["img"], type="image/jpeg")
    
    new_count += 1

print(f"Added {new_count} new articles")

# Trim to last MAX_ITEMS
all_items = channel.findall("item")
if len(all_items) > MAX_ITEMS:
    for old_item in all_items[:-MAX_ITEMS]:
        channel.remove(old_item)

# Save XML
tree = ET.ElementTree(root)
tree.write(XML_FILE, encoding="utf-8", xml_declaration=True)

print(f"XML saved with {len(channel.findall('item'))} total articles")
