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
  
            # Navigate the Nuxt flat-array structure:  
            # Find the state dict that holds category_all_news  
            state_dict = None  
            for item in json_data:  
                if isinstance(item, dict) and "category_all_news" in item:  
                    state_dict = item  
                    break  
  
            if state_dict is None:  
                print("Could not find state dict with category_all_news key")  
            else:  
                cat_ref = state_dict["category_all_news"]  
  
                # Resolve cat_ref to the list of article indices  
                if isinstance(cat_ref, int) and 0 <= cat_ref < len(json_data):  
                    article_index_list = json_data[cat_ref]  
                else:  
                    article_index_list = []  
  
                if not isinstance(article_index_list, list):  
                    print(f"Unexpected type for category_all_news list: {type(article_index_list)}")  
                    article_index_list = []  
  
                print(f"Found {len(article_index_list)} article slots in category_all_news")  
  
                for article_idx in article_index_list:  
                    if not (isinstance(article_idx, int) and 0 <= article_idx < len(json_data)):  
                        continue  
  
                    item = json_data[article_idx]  
                    if not isinstance(item, dict):  
                        continue  
                    if "headline" not in item or "slug" not in item:  
                        continue  
  
                    slug = resolve_value(item.get("slug"))  
                    title = resolve_value(item.get("headline"))  
                    desc_raw = item.get("excerpt") or item.get("content")  
                    desc = resolve_value(desc_raw) if desc_raw is not None else ""  
                    pub = resolve_value(item.get("published_at"))  
                    img = resolve_value(item.get("thumb"))  
  
                    slug = str(slug) if slug else ""  
                    title = str(title) if title else ""  
                    desc = str(desc) if desc else ""  
                    pub = str(pub) if pub else ""  
                    img = str(img) if img else ""  
  
                    is_valid_slug = (  
                        slug  
                        and not slug.isdigit()  
                        and len(slug) > 10  
                        and slug.startswith("019")  
                    )  
  
                    is_valid_title = (  
                        title  
                        and not title.isdigit()  
                        and len(title) > 5  
                        and not title.startswith("http")  
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
        pattern = r'"headline":"([^"]+)"[^}]*"slug":"(019[^"]+)"[^}]*"thumb":"([^"]*)"[^}]*"published_at":"([^"]*)"'  
        for match in re.finditer(pattern, content):  
            title, slug, img, pub = match.group(1), match.group(2), match.group(3), match.group(4)  
            if title and slug and len(slug) > 10:  
                url = f"https://www.dainikamadershomoy.com/news/{slug}"  
                articles.append({"url": url, "title": title, "desc": "", "pub": pub, "img": img})  
                print(f"Found article (regex): {title[:50]}...")  
  
    return articles  
  
  
# ── Collect ──────────────────────────────────────────────────────────────────  
articles_by_file = {}  
for html_file in HTML_FILES:  
    articles_by_file[html_file] = extract_articles_from_file(html_file)  
  
# ── Deduplicate across files ──────────────────────────────────────────────────  
url_sets = {f: set(a["url"] for a in arts) for f, arts in articles_by_file.items()}  
all_urls = set().union(*url_sets.values())  
common_urls = {url for url in all_urls if sum(url in s for s in url_sets.values()) > 1}  
  
print(f"\nCommon URLs found in multiple files: {len(common_urls)}")  
for url in common_urls:  
    print(f"  - {url}")  
  
unique_articles = []  
seen_urls = set()  
eliminated_count = 0  
  
for arts in articles_by_file.values():  
    for art in arts:  
        if art["url"] in common_urls:  
            eliminated_count += 1  
            print(f"Eliminated common article: {art['title'][:50]}...")  
        elif art["url"] not in seen_urls:  
            unique_articles.append(art)  
            seen_urls.add(art["url"])  
  
articles = unique_articles  
  
print(f"\n=== Summary ===")  
print(f"Total articles found: {sum(len(a) for a in articles_by_file.values())}")  
print(f"Common articles eliminated: {eliminated_count}")  
print(f"Unique articles kept: {len(articles)}")  
  
if not articles:  
    print("WARNING: No articles found! Check HTML structure.")  
  
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
    ET.SubElement(item, "pubDate").text = (  
        str(art["pub"]) if art["pub"]  
        else datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")  
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