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
        
        # Helper function to resolve references in the JSON array
        def resolve_value(val):
            if isinstance(val, int) and 0 <= val < len(json_data):
                return json_data[val]
            return val
        
        # Navigate through the JSON structure to find the category_all_news section
        if isinstance(json_data, list) and len(json_data) > 1:
            # Look for the data structure - typically at index 1
            data_obj = json_data[1] if isinstance(json_data[1], dict) else {}
            
            # Find category_all_news key
            category_news_idx = data_obj.get("category_all_news")
            if category_news_idx and isinstance(category_news_idx, int):
                category_news = resolve_value(category_news_idx)
                
                # category_news should be a list of article indices
                if isinstance(category_news, list):
                    for art_idx in category_news:
                        article = resolve_value(art_idx)
                        
                        if isinstance(article, dict) and "headline" in article and "slug" in article:
                            # Resolve references to get actual values
                            slug = resolve_value(article.get("slug", ""))
                            title = resolve_value(article.get("headline", ""))
                            desc = resolve_value(article.get("excerpt", "")) or resolve_value(article.get("content", ""))
                            pub = resolve_value(article.get("published_at", ""))
                            img = resolve_value(article.get("thumb", ""))
                            
                            # Ensure all fields are strings
                            slug = str(slug) if slug and slug != 10 and not isinstance(slug, int) else ""
                            title = str(title) if title and not isinstance(title, int) else ""
                            desc = str(desc) if desc and desc != 10 and not isinstance(desc, int) else ""
                            pub = str(pub) if pub and not isinstance(pub, int) else ""
                            img = str(img) if img and not isinstance(img, int) else ""
                            
                            # Skip if title is still empty or numeric or too short
                            if not title or title.isdigit() or len(title) < 5:
                                continue
                            
                            # Opinion article slugs typically start with "019a" or similar
                            if title and slug and not slug.isdigit() and len(slug) > 5:
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
    ET.SubElement(item, "title").text = str(art["title"])
    ET.SubElement(item, "link").text = str(art["url"])
    ET.SubElement(item, "description").text = str(art["desc"])
    ET.SubElement(item, "pubDate").text = str(art["pub"]) if art["pub"] else datetime.now(datetime.UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")
    if art["img"]:
        ET.SubElement(item, "enclosure", url=str(art["img"]), type="image/jpeg")
    
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