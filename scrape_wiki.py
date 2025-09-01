# scrape_wiki.py (Final, Granular Parsing v3)
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

# --- Reddit API Functions ---
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
    headers = {'User-Agent': f'SeanimeScraper/0.8 by {USERNAME}'}
    res = requests.post('https://www.reddit.com/api/v1/access_token', auth=auth, data=data, headers=headers)
    res.raise_for_status()
    print("Successfully obtained Reddit API access token.")
    return res.json()['access_token']

def fetch_wiki_data(access_token):
    wiki_url = "https://oauth.reddit.com/r/anime/wiki/watch_order"
    headers = {
        'User-Agent': f'SeanimeScraper/0.8 by {os.environ.get("REDDIT_USERNAME")}',
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

# --- AniList API Function ---
def fetch_anilist_data_batch(mal_ids):
    if not mal_ids:
        return {}
    # Batched requests to not overload the API
    mal_id_chunks = [mal_ids[i:i + 50] for i in range(0, len(mal_ids), 50)]
    anilist_map = {}
    
    query = '''
    query ($ids: [Int], $type: MediaType) {
      Page(perPage: 50) {
        media(idMal_in: $ids, type: $type) {
          id
          idMal
          title { romaji english native userPreferred }
          format
          status
          episodes
          duration
          season
          seasonYear
          averageScore
          popularity
          genres
          studios(isMain: true) { nodes { name } }
          coverImage { extraLarge large color }
        }
      }
    }
    '''
    for chunk in mal_id_chunks:
        variables = {'ids': chunk, 'type': 'ANIME'}
        try:
            time.sleep(1) # Rate limit between chunks
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
def get_content_between_tags(start_tag, end_tag_names):
    content_tags = []
    for sibling in start_tag.find_next_siblings():
        if sibling.name in end_tag_names:
            break
        content_tags.append(sibling)
    return content_tags

def parse_steps_from_html_slice(html_slice, anilist_map):
    steps = []
    processed_mal_ids_in_slice = set()
    
    links = html_slice.find_all('a', href=re.compile(r'myanimelist\.net/anime/(\d+)'))

    for a_tag in links:
        match = re.search(r'myanimelist\.net/anime/(\d+)', a_tag['href'])
        if not match:
            continue

        mal_id = int(match.group(1))
        if mal_id in processed_mal_ids_in_slice:
            continue
            
        media_data = anilist_map.get(mal_id)
        if not media_data:
            continue

        processed_mal_ids_in_slice.add(mal_id)

        step_title = a_tag.get_text(strip=True)
        
        # Check for optional status in the link's parent context
        parent_text = a_tag.find_parent().get_text() if a_tag.find_parent() else ""
        is_optional = '(optional)' in parent_text.lower()

        clean_media_data = media_data.copy()
        clean_media_data['studios'] = [node['name'] for node in clean_media_data.get('studios', {}).get('nodes', [])]

        steps.append({
            "step_title": step_title,
            "is_optional": is_optional,
            "media": clean_media_data
        })
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
        # Improved title parsing
        raw_title = h3.get_text(strip=True)
        clean_title = raw_title.replace('//', '##SLASH##')
        parts = [p.strip().replace('##SLASH##', '//') for p in clean_title.split('/')]
        title = parts[0]
        alternative_titles = parts[1:] if len(parts) > 1 else []
        
        print(f"Processing Entry: {title}")

        entry_content_html = "".join(map(str, get_content_between_tags(h3, ['h3', 'hr'])))
        entry_soup = BeautifulSoup(entry_content_html, 'lxml')
        
        watch_orders_list = []
        
        sub_headings = entry_soup.find_all(['h4', lambda tag: tag.name == 'p' and tag.strong and len(tag.get_text(strip=True)) == len(tag.strong.get_text(strip=True)) and len(tag.get_text(strip=True)) < 100])
        
        if sub_headings:
            print(f"  - Complex entry found with {len(sub_headings)} sub-sections.")
            for i, sub_head in enumerate(sub_headings):
                sub_title = sub_head.get_text(strip=True).replace(':', '')
                
                next_sub_head = sub_headings[i+1] if i + 1 < len(sub_headings) else None
                
                sub_content_tags = []
                for sibling in sub_head.find_next_siblings():
                    if sibling == next_sub_head:
                        break
                    sub_content_tags.append(sibling)
                
                sub_slice_soup = BeautifulSoup("".join(map(str, sub_content_tags)), 'lxml')
                
                description_p = sub_head.find_next('p')
                description = description_p.get_text(strip=True) if description_p and description_p not in sub_headings else None
                
                steps = parse_steps_from_html_slice(sub_slice_soup, anilist_data_map)
                
                if steps:
                    watch_orders_list.append({"name": sub_title, "description": description, "steps": steps})
        else:
            print("  - Simple entry found.")
            steps = parse_steps_from_html_slice(entry_soup, anilist_data_map)
            if steps:
                watch_orders_list.append({"name": "Main Story", "description": None, "steps": steps})

        entry_notes = None
        note_tag = entry_soup.find(['strong', 'b'], string=re.compile(r'Note:?', re.IGNORECASE))
        if note_tag:
             note_parent = note_tag.find_parent()
             if note_parent:
                  entry_notes = note_parent.get_text(strip=True)

        if watch_orders_list:
            api_entries.append({
                "title": title,
                "alternative_titles": alternative_titles,
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
                "version": "2.4",
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
