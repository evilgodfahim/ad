import sys
import os
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
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
script_tag = soup.find("script", {"id": "__NUXT_DATA__", "type": "application/json"})
if script_tag:
    try:
        json_data = json.loads(script_tag.string)
        
        # Helper function to resolve references in the JSON array
        def resolve_value(val, depth=0):
            if depth > 5:  # Prevent infinite recursion
                return val
            if isinstance(val, int) and 0 <= val < len(json_data):
                resolved = json_data[val]
                # If it's still an int, try to resolve again
                if isinstance(resolved, int) and resolved != val:
                    return resolve_value(resolved, depth + 1)
                return resolved
            return val
        
        # Debug: Print structure
        print(f"JSON data length: {len(json_data)}")
        if len(json_data) > 1 and isinstance(json_data[1], dict):
            print(f"Keys in data object: {json_data[1].keys()}")
        
        # Navigate to the correct nested structure
        # Based on the JSON: json_data[1] contains the data object
        if len(json_data) > 1 and isinstance(json_data[1], dict):
            data_obj = json_data[1].get("data")
            if data_obj:
                data_obj = resolve_value(data_obj)
                
                if isinstance(data_obj, dict):
                    # Look for category_all_news key
                    category_news = data_obj.get("category_all_news")
                    if category_news:
                        category_news = resolve_value(category_news)
                        print(f"Found category_all_news: {type(category_news)}")
                        
                        # category_news should be a list or array of article references
                        if isinstance(category_news, list):
                            print(f"Processing {len(category_news)} items from category_all_news")
                            
                            for art_ref in category_news:
                                article = resolve_value(art_ref)
                                
                                if isinstance(article, dict) and "headline" in article and "slug" in article:
                                    # Resolve all fields
                                    slug = resolve_value(article.get("slug"))
                                    title = resolve_value(article.get("headline"))
                                    desc = resolve_value(article.get("excerpt")) or resolve_value(article.get("content", ""))
                                    pub = resolve_value(article.get("published_at"))
                                    img = resolve_value(article.get("thumb"))
                                    
                                    # Convert to strings
                                    slug = str(slug) if slug and not isinstance(slug, (int, type(None))) else ""
                                    title = str(title) if title and not isinstance(title, (int, type(None))) else ""
                                    desc = str(desc) if desc and not isinstance(desc, (int, type(None))) else ""
                                    pub = str(pub) if pub and not isinstance(pub, (int, type(None))) else ""
                                    img = str(img) if img and not isinstance(img, (int, type(None))) else ""
                                    
                                    # Basic validation
                                    if title and slug and len(title) > 5 and len(slug) > 10:
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
                                        print(f"Found article: {title[:50]}...")
                    
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"Error parsing JSON data: {e}")

# --- Fallback: Parse from text in the original snippet you provided ---
if not articles:
    print("Trying fallback method - parsing from text patterns...")
    
    # Look for the patterns from your original data
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

# Remove duplicates based on URL
seen_urls = set()
unique_articles = []
for art in articles:
    if art["url"] not in seen_urls:
        seen_urls.add(art["url"])
        unique_articles.append(art)

articles = unique_articles

print(f"\nFound {len(articles)} total unique articles")

if not articles:
    print("WARNING: No articles found! Check HTML structure.")
    # Print sample of HTML for debugging
    print("\nSample HTML content:")
    print(content[:1000])

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