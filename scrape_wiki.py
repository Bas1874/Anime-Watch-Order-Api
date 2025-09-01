# scrape_wiki.py (Final, Corrected NameError v2.9)
import requests
import json
import sys
import os
import re
import time
import html
from bs4 import BeautifulSoup, Tag
from datetime import datetime, timezone

# --- Constants ---
ANILIST_API_URL = 'https://graphql.anilist.co'

# --- Reddit API & AniList API Functions (No changes needed here) ---
def get_reddit_access_token():
    CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
    CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")
    USERNAME = os.environ.get("REDDIT_USERNAME")
    PASSWORD = os.environ.get("REDDIT_PASSWORD")
    if not all([CLIENT_ID, CLIENT_SECRET, USERNAME, PASSWORD]):
        raise ValueError("Error: Missing one or more Reddit credentials.")
    print("Authenticating with Reddit API...")
    auth = requests.auth.HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET)
    data = {'grant_type': 'password', 'username': USERNAME, 'password': PASSWORD}
    headers = {'User-Agent': f'SeanimeScraper/1.2 by {USERNAME}'}
    res = requests.post('https://www.reddit.com/api/v1/access_token', auth=auth, data=data, headers=headers)
    res.raise_for_status()
    print("Successfully obtained Reddit API access token.")
    return res.json()['access_token']

def fetch_wiki_data(access_token):
    wiki_url = "https://oauth.reddit.com/r/anime/wiki/watch_order"
    headers = {
        'User-Agent': f'SeanimeScraper/1.2 by {os.environ.get("REDDIT_USERNAME")}',
        'Authorization': f'bearer {access_token}'
    }
    print(f"Fetching data from {wiki_url}...")
    response = requests.get(wiki_url, headers=headers)
    response.raise_for_status()
    data = response.json()
    html_content = data.get("data", {}).get("content_html", "")
    if not html_content:
        raise ValueError("Reddit API returned an empty 'content_html' field.")
    unescaped_html = html.unescape(html_content)
    temp_soup = BeautifulSoup(unescaped_html, 'lxml')
    if not temp_soup.find('h2', id='wiki_watch_orders'):
        raise ValueError("Fetched HTML from Reddit is invalid: Missing 'Watch Orders' section.")
    print("Fetched and unescaped HTML content is valid.")
    return unescaped_html

def fetch_anilist_data_batch(mal_ids):
    if not mal_ids: return {}
    mal_id_chunks = [mal_ids[i:i + 50] for i in range(0, len(mal_ids), 50)]
    anilist_map = {}
    query = '''
    query ($ids: [Int], $type: MediaType) {
      Page(perPage: 50) {
        media(idMal_in: $ids, type: $type) {
          id idMal title { romaji english native userPreferred } format status episodes duration season seasonYear averageScore popularity genres
          studios(isMain: true) { nodes { name } }
          coverImage { extraLarge large color }
        }
      }
    }
    '''
    for chunk in mal_id_chunks:
        variables = {'ids': chunk, 'type': 'ANIME'}
        try:
            time.sleep(1)
            response = requests.post(ANILIST_API_URL, json={'query': query, 'variables': variables})
            response.raise_for_status()
            data = response.json()
            if data.get('data') and data['data'].get('Page'):
                for media in data['data']['Page']['media']:
                    anilist_map[media['idMal']] = media
        except requests.exceptions.RequestException as e:
            print(f"  - AniList chunk query failed: {e}")
    return anilist_map

# --- Parsing Logic ---
def get_content_between_tags(start_tag, end_tags):
    content = []
    for sibling in start_tag.find_next_siblings():
        if sibling in end_tags:
            break
        content.append(sibling)
    return content

def parse_steps_from_slice(html_slice, anilist_map):
    steps = []
    processed_mal_ids = set()
    links = html_slice.find_all('a', href=re.compile(r'myanimelist\.net/anime/(\d+)'))
    for a_tag in links:
        match = re.search(r'myanimelist\.net/anime/(\d+)', a_tag['href'])
        if not match: continue
        mal_id = int(match.group(1))
        if mal_id in processed_mal_ids: continue
        media_data = anilist_map.get(mal_id)
        if not media_data: continue
        processed_mal_ids.add(mal_id)
        step_title = a_tag.get_text(strip=True)
        parent_text = a_tag.find_parent().get_text(strip=True) if a_tag.find_parent() else ""
        is_optional = '(optional)' in parent_text.lower()
        clean_media_data = media_data.copy()
        clean_media_data['studios'] = [node['name'] for node in clean_media_data.get('studios', {}).get('nodes', [])]
        steps.append({"step_title": step_title, "is_optional": is_optional, "media": clean_media_data})
    return steps

def parse_all_watch_orders(html_content):
    soup = BeautifulSoup(html_content, 'lxml')
    api_entries = []
    all_mal_ids = {int(m.group(1)) for m in (re.search(r'myanimelist\.net/anime/(\d+)', a['href']) for a in soup.find_all('a', href=True)) if m}
    print(f"Found {len(all_mal_ids)} unique MAL IDs. Fetching from AniList...")
    anilist_data_map = fetch_anilist_data_batch(list(all_mal_ids))
    print("Finished fetching AniList data.")

    watch_orders_h2 = soup.find('h2', id='wiki_watch_orders')
    all_h3_tags = watch_orders_h2.find_next_siblings('h3')

    for h3 in all_h3_tags:
        raw_title = h3.get_text(strip=True)
        clean_title = raw_title.replace('//', '##SLASH##')
        parts = [p.strip().replace('##SLASH##', '//') for p in clean_title.split('/')]
        title = parts[0]
        alternative_titles = parts[1:] if len(parts) > 1 else []
        
        print(f"Processing Entry: {title}")

        content_tags = get_content_between_tags(h3, all_h3_tags)
        entry_soup = BeautifulSoup("".join(map(str, content_tags)), 'lxml')
        
        watch_orders_list = []
        prologue_html = ""
        
        sub_headings = entry_soup.find_all(['h4', lambda tag: tag.name == 'p' and tag.strong and len(tag.get_text(strip=True)) == len(tag.strong.get_text(strip=True)) and len(tag.get_text(strip=True)) < 100 and 'note' not in tag.get_text(strip=True).lower()])

        if sub_headings:
            prologue_tags = []
            for tag in entry_soup.contents:
                if tag in sub_headings: break
                prologue_tags.append(str(tag))
            prologue_html = "".join(prologue_tags)

            for i, sub_head in enumerate(sub_headings):
                sub_title = sub_head.get_text(strip=True).replace(':', '')
                next_sub_head = sub_headings[i+1] if i + 1 < len(sub_headings) else None
                
                sub_content_tags = get_content_between_tags(sub_head, [next_sub_head] if next_sub_head else [])
                sub_content_html = "".join(map(str, sub_content_tags))
                sub_soup = BeautifulSoup(sub_content_html, 'lxml')
                
                description = sub_soup.get_text(separator='\n', strip=True)
                steps = parse_steps_from_slice(sub_soup, anilist_data_map)
                
                if steps or description:
                    watch_orders_list.append({"name": sub_title, "description": description, "description_html": sub_content_html, "steps": steps})
        else:
            description = entry_soup.get_text(separator='\n', strip=True)
            description_html = str(entry_soup)
            steps = parse_steps_from_slice(entry_soup, anilist_data_map)
            if steps:
                watch_orders_list.append({"name": "Main Story", "description": description, "description_html": description_html, "steps": steps})

        notes_list = []
        for note_tag in entry_soup.find_all(['strong', 'b'], string=re.compile(r'Note:?', re.IGNORECASE)):
            parent = note_tag.find_parent()
            if parent: notes_list.append(parent.get_text(strip=True))
        entry_notes = "\n".join(notes_list) if notes_list else None

        if watch_orders_list:
            prologue_soup = BeautifulSoup(prologue_html, 'lxml')
            api_entries.append({
                "title": title,
                "alternative_titles": alternative_titles,
                "prologue": prologue_soup.get_text(separator='\n', strip=True) or None,
                "prologue_html": prologue_html or None,
                "entry_notes": entry_notes,
                "watch_orders": watch_orders_list
            })

    return api_entries

# --- Main Execution ---
def main():
    if len(sys.argv) < 2:
        print("Usage: python scrape_wiki.py <output_directory>")
        sys.exit(1)
        
    output_dir = sys.argv[1]
    os.makedirs(output_dir, exist_ok=True)
    raw_output_path = os.path.join(output_dir, "watch_order.json")
    api_output_path = os.path.join(output_dir, "watch_order_api.json")

    try:
        token = get_reddit_access_token()
        html_content = fetch_wiki_data(token)

        with open(raw_output_path, 'w', encoding='utf-8') as f:
            json.dump({"unescaped_html": html_content}, f, ensure_ascii=False, indent=4)
        print(f"Successfully saved raw wiki data to {raw_output_path}")

        api_data = parse_all_watch_orders(html_content)
        
        final_output = {
            "metadata": {
                "version": "2.9",
                "last_updated_utc": datetime.now(timezone.utc).isoformat(),
                "source_url": "https://www.reddit.com/r/anime/wiki/watch_order"
            },
            "data": api_data
        }

        with open(api_output_path, 'w', encoding='utf-8') as f:
            json.dump(final_output, f, ensure_ascii=False, indent=4)
        print(f"Successfully created and saved API data to {api_output_path}")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
