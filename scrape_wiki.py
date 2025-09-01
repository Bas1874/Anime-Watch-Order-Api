# scrape_wiki.py (Final, Complex-Parsing v2)
import requests
import json
import sys
import os
import re
import time
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
    headers = {'User-Agent': f'SeanimeScraper/0.5 by {USERNAME}'}
    res = requests.post('https://www.reddit.com/api/v1/access_token', auth=auth, data=data, headers=headers)
    res.raise_for_status()
    print("Successfully obtained Reddit API access token.")
    return res.json()['access_token']

def fetch_wiki_data(access_token):
    wiki_url = "https://oauth.reddit.com/r/anime/wiki/watch_order"
    headers = {
        'User-Agent': f'SeanimeScraper/0.5 by {os.environ.get("REDDIT_USERNAME")}',
        'Authorization': f'bearer {access_token}'
    }
    print(f"Fetching data from {wiki_url}...")
    response = requests.get(wiki_url, headers=headers)
    response.raise_for_status()
    data = response.json()
    html_content = data.get("data", {}).get("content_html", "")
    if not html_content:
        raise ValueError("Error: Could not find 'content_html' in the response.")
    return html_content

# --- AniList API Function ---
def fetch_anilist_data_batch(mal_ids):
    if not mal_ids:
        return {}
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
    variables = {'ids': list(set(mal_ids)), 'type': 'ANIME'}
    try:
        response = requests.post(ANILIST_API_URL, json={'query': query, 'variables': variables})
        response.raise_for_status()
        data = response.json()
        if data.get('data') and data['data'].get('Page'):
            return {media['idMal']: media for media in data['data']['Page']['media']}
    except requests.exceptions.RequestException as e:
        print(f"  - AniList batch query failed: {e}")
    return {}

# --- Parsing Logic ---
def get_content_between_tags(start_tag, end_tag_names):
    content_tags = []
    for sibling in start_tag.find_next_siblings():
        if sibling.name in end_tag_names:
            break
        content_tags.append(sibling)
    return content_tags

def parse_steps_from_content(content_tags, anilist_map):
    steps = []
    processed_mal_ids = set()

    content_soup = BeautifulSoup("".join(map(str, content_tags)), 'lxml')
    
    # Process all list items and paragraphs that might contain links
    for item in content_soup.find_all(['li', 'p']):
        links = item.find_all('a', href=re.compile(r'myanimelist\.net/anime/(\d+)'))
        for a_tag in links:
            match = re.search(r'myanimelist\.net/anime/(\d+)', a_tag['href'])
            if match:
                mal_id = int(match.group(1))
                if mal_id in processed_mal_ids:
                    continue

                media_data = anilist_map.get(mal_id)
                if not media_data:
                    continue
                
                processed_mal_ids.add(mal_id)
                
                # Use the whole list item's text as the title for context
                step_title = item.get_text(strip=True)
                is_optional = '(optional)' in step_title.lower()

                # Clean up studio data
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

    # Batch fetch all MAL IDs at once for efficiency
    all_mal_ids = {int(m.group(1)) for m in (re.search(r'myanimelist\.net/anime/(\d+)', a['href']) for a in soup.find_all('a', href=True)) if m}
    print(f"Found {len(all_mal_ids)} unique MAL IDs. Fetching from AniList...")
    anilist_data_map = fetch_anilist_data_batch(list(all_mal_ids))
    print("Finished fetching AniList data.")

    # Find the "Watch Orders" H2 tag to start parsing from there, ignoring the FAQ
    watch_orders_h2 = soup.find('h2', id='wiki_watch_orders')
    if not watch_orders_h2:
        raise ValueError("Could not find the 'Watch Orders' section header (h2) in the wiki.")

    all_h3_tags = watch_orders_h2.find_next_siblings('h3')

    for h3 in all_h3_tags:
        header_text = h3.get_text(strip=True)
        parts = [p.strip() for p in header_text.split('/')]
        title = parts[0]
        alternative_titles = parts[1:] if len(parts) > 1 else []
        
        print(f"Processing Entry: {title}")

        entry_content_tags = get_content_between_tags(h3, ['h3', 'hr'])
        entry_soup = BeautifulSoup("".join(map(str, entry_content_tags)), 'lxml')
        
        watch_orders_list = []
        
        # Find sub-headings. A sub-heading is an H4 or a P tag containing only a STRONG tag.
        sub_headings = entry_soup.find_all(['h4', lambda tag: tag.name == 'p' and tag.strong and len(tag.get_text(strip=True)) == len(tag.strong.get_text(strip=True))])

        if sub_headings:
            print(f"  - Complex entry found with {len(sub_headings)} sub-sections.")
            for i, sub_head in enumerate(sub_headings):
                sub_title = sub_head.get_text(strip=True).replace(':', '')
                
                # Get content between this subheading and the next one
                sub_content_tags = get_content_between_tags(sub_head, ['h4', 'p'])
                
                description_p = sub_head.find_next('p')
                description = description_p.get_text(strip=True) if description_p and description_p not in sub_headings else None

                steps = parse_steps_from_content(sub_content_tags, anilist_data_map)
                
                if steps:
                    watch_orders_list.append({
                        "name": sub_title,
                        "description": description,
                        "steps": steps
                    })
        else:
            # Handle simple entries
            print("  - Simple entry found.")
            steps = parse_steps_from_content(entry_content_tags, anilist_data_map)
            if steps:
                watch_orders_list.append({
                    "name": "Main Story",
                    "description": None,
                    "steps": steps
                })

        # Extract general notes for the entire entry
        entry_notes = None
        note_tag = entry_soup.find('strong', string=re.compile(r'Note:?', re.IGNORECASE))
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
        html = fetch_wiki_data(token)

        with open(raw_output_path, 'w', encoding='utf-8') as f:
            json.dump({"html": html}, f, ensure_ascii=False, indent=4)
        print(f"Successfully saved raw wiki data to {raw_output_path}")

        api_data = parse_all_watch_orders(html)
        
        final_output = {
            "metadata": {
                "version": "2.1",
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
