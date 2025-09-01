# scrape_wiki.py (Final, Complex-Parsing Version)
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
# These functions (get_reddit_access_token, fetch_wiki_data) remain the same.
# I've included them here for completeness.
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
    headers = {'User-Agent': f'SeanimeScraper/0.4 by {USERNAME}'}
    res = requests.post('https://www.reddit.com/api/v1/access_token', auth=auth, data=data, headers=headers)
    res.raise_for_status()
    print("Successfully obtained Reddit API access token.")
    return res.json()['access_token']

def fetch_wiki_data(access_token):
    wiki_url = "https://oauth.reddit.com/r/anime/wiki/watch_order"
    headers = {
        'User-Agent': f'SeanimeScraper/0.4 by {os.environ.get("REDDIT_USERNAME")}',
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
# This function (fetch_anilist_data_batch) also remains the same.
def fetch_anilist_data_batch(mal_ids):
    if not mal_ids:
        return {}
    query = '''
    query ($ids: [Int], $type: MediaType) {
      Page {
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

# --- NEW Parsing Logic ---
def get_content_between_tags(start_tag, end_tag_names):
    """Collects all sibling tags between a starting tag and the next tag in a given list."""
    content_tags = []
    for sibling in start_tag.find_next_siblings():
        if sibling.name in end_tag_names:
            break
        content_tags.append(sibling)
    return content_tags

def parse_steps_from_content(content_tags, anilist_map):
    """Parses a list of tags to extract watch order steps."""
    steps = []
    mal_ids_in_order = []

    # First pass: collect all MAL IDs in order
    for tag in content_tags:
        if isinstance(tag, Tag): # Ensure it's a tag before searching
            for a_tag in tag.find_all('a', href=re.compile(r'myanimelist\.net/anime/(\d+)')):
                match = re.search(r'myanimelist\.net/anime/(\d+)', a_tag['href'])
                if match:
                    mal_id = int(match.group(1))
                    if mal_id not in mal_ids_in_order:
                        mal_ids_in_order.append(mal_id)
    
    # Second pass: build the structured steps using the fetched AniList data
    for mal_id in mal_ids_in_order:
        media_data = anilist_map.get(mal_id)
        if not media_data:
            print(f"    - Warning: No AniList data found for MAL ID {mal_id}")
            continue

        # Find the original link to get context
        original_link_tag = None
        for tag in content_tags:
            if isinstance(tag, Tag):
                link = tag.find('a', href=re.compile(f'myanimelist.net/anime/{mal_id}'))
                if link:
                    original_link_tag = link
                    break
        
        step_title = original_link_tag.get_text(strip=True) if original_link_tag else media_data.get('title', {}).get('romaji', 'Unknown')
        
        # Check for optional status in the parent context
        is_optional = False
        if original_link_tag and original_link_tag.find_parent():
            parent_text = original_link_tag.find_parent().get_text()
            if '(optional)' in parent_text.lower():
                is_optional = True

        # Clean up studios list
        media_data['studios'] = [node['name'] for node in media_data.get('studios', {}).get('nodes', [])]

        steps.append({
            "step_title": step_title,
            "is_optional": is_optional,
            "media": media_data
        })
    return steps

def parse_all_watch_orders(html_content):
    """The main parsing function to handle both simple and complex entries."""
    soup = BeautifulSoup(html_content, 'lxml')
    api_entries = []
    
    all_mal_ids = set()
    # First, scan the entire document to collect all MAL IDs for one big batch request
    for a_tag in soup.find_all('a', href=re.compile(r'myanimelist\.net/anime/(\d+)')):
        match = re.search(r'myanimelist\.net/anime/(\d+)', a_tag['href'])
        if match:
            all_mal_ids.add(int(match.group(1)))

    print(f"Found {len(all_mal_ids)} unique MAL IDs. Fetching from AniList...")
    anilist_data_map = fetch_anilist_data_batch(list(all_mal_ids))
    print("Finished fetching AniList data.")

    # Now, parse each entry
    all_h3_tags = soup.find_all('h3', id=lambda x: x and x.startswith('wiki_'))
    for h3 in all_h3_tags:
        header_text = h3.get_text(strip=True)
        parts = [p.strip() for p in header_text.split('/')]
        title = parts[0]
        alternative_titles = parts[1:] if len(parts) > 1 else []
        
        print(f"Processing Entry: {title}")

        entry_content_tags = get_content_between_tags(h3, ['h3', 'hr'])
        entry_soup = BeautifulSoup("".join(map(str, entry_content_tags)), 'lxml')
        
        watch_orders = []
        
        # Find sub-headings (h4 or strong tags that act as headers)
        sub_headings = entry_soup.find_all(['h4', 'strong'])
        
        # Filter out 'strong' tags that are just for emphasis (like "Note:")
        actual_sub_headings = []
        for sh in sub_headings:
            # A simple heuristic: if the tag is the first thing in its parent paragraph, it's likely a heading.
            if sh.name == 'h4':
                 actual_sub_headings.append(sh)
            elif sh.name == 'strong' and sh.find_previous_sibling() is None and len(sh.get_text(strip=True)) < 50:
                 actual_sub_headings.append(sh)


        if actual_sub_headings and title not in ["FAQ"]:
            print(f"  - Complex entry found with {len(actual_sub_headings)} sub-sections.")
            for i, sub_head in enumerate(actual_sub_headings):
                sub_title = sub_head.get_text(strip=True).replace(':', '')
                
                # Determine the end boundary for this sub-section's content
                end_tags = ['h4', 'strong']
                
                sub_content_tags = get_content_between_tags(sub_head, end_tags)
                
                # The description is the text immediately following the sub-heading
                description_p = sub_head.find_next('p')
                description = description_p.get_text(strip=True) if description_p else None

                steps = parse_steps_from_content(sub_content_tags, anilist_data_map)
                
                if steps:
                    watch_orders.append({
                        "name": sub_title,
                        "description": description,
                        "steps": steps
                    })
        else:
            # Handle simple entries with no sub-headings
            print("  - Simple entry found.")
            steps = parse_steps_from_content(entry_content_tags, anilist_data_map)
            if steps:
                watch_orders.append({
                    "name": "Main Story",
                    "description": None,
                    "steps": steps
                })

        # Extract general notes for the entire entry
        entry_notes = None
        note_tag = entry_soup.find('strong', string=re.compile(r'Note:?', re.IGNORECASE))
        if note_tag:
            note_content_tags = get_content_between_tags(note_tag, ['h3', 'h4', 'hr', 'strong'])
            entry_notes = BeautifulSoup("".join(map(str, note_content_tags)), 'lxml').get_text(separator='\n', strip=True)

        if watch_orders:
            api_entries.append({
                "title": title,
                "alternative_titles": alternative_titles,
                "entry_notes": entry_notes,
                "watch_orders": watch_orders
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
                "version": "2.0",
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
