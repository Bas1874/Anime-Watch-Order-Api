# scrape_wiki.py (Advanced API Version)
import requests
import json
import sys
import os
import re
import time
from bs4 import BeautifulSoup
from datetime import datetime, timezone

# --- Constants ---
ANILIST_API_URL = 'https://graphql.anilist.co'

# --- Reddit API Functions ---
def get_reddit_access_token():
    # ... (this function remains the same as the previous version)
    CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
    CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")
    USERNAME = os.environ.get("REDDIT_USERNAME")
    PASSWORD = os.environ.get("REDDIT_PASSWORD")
    if not all([CLIENT_ID, CLIENT_SECRET, USERNAME, PASSWORD]):
        raise ValueError("Error: Missing one or more Reddit credentials.")
    print("Authenticating with Reddit API...")
    auth = requests.auth.HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET)
    data = {'grant_type': 'password', 'username': USERNAME, 'password': PASSWORD}
    headers = {'User-Agent': f'SeanimeScraper/0.3 by {USERNAME}'}
    res = requests.post('https://www.reddit.com/api/v1/access_token', auth=auth, data=data, headers=headers)
    res.raise_for_status()
    print("Successfully obtained Reddit API access token.")
    return res.json()['access_token']

def fetch_wiki_data(access_token):
    # ... (this function remains the same as the previous version)
    wiki_url = "https://oauth.reddit.com/r/anime/wiki/watch_order"
    headers = {
        'User-Agent': f'SeanimeScraper/0.3 by {os.environ.get("REDDIT_USERNAME")}',
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
    """Fetches comprehensive data for a list of MAL IDs from AniList in a single query."""
    if not mal_ids:
        return {}
        
    query = '''
    query ($ids: [Int], $type: MediaType) {
      Page {
        media(idMal_in: $ids, type: $type) {
          id
          idMal
          title {
            romaji
            english
          }
          format
          status
          episodes
          duration
          season
          seasonYear
          averageScore
          popularity
          genres
          studios(isMain: true) {
            nodes {
              name
            }
          }
          coverImage {
            extraLarge
            large
          }
        }
      }
    }
    '''
    variables = {'ids': mal_ids, 'type': 'ANIME'}
    try:
        response = requests.post(ANILIST_API_URL, json={'query': query, 'variables': variables})
        response.raise_for_status()
        data = response.json()
        # Create a mapping from mal_id -> anilist_data for easy lookup
        if data.get('data') and data['data'].get('Page'):
            return {media['idMal']: media for media in data['data']['Page']['media']}
    except Exception as e:
        print(f"  - AniList batch query failed: {e}")
    return {}

# --- Parsing Functions ---
def parse_and_enrich_watch_orders(html_content):
    """Parses the HTML and enriches it with AniList data to create the final API structure."""
    soup = BeautifulSoup(html_content, 'lxml')
    api_entries = []
    
    for h3 in soup.find_all('h3', id=lambda x: x and x.startswith('wiki_')):
        header_text = h3.get_text(strip=True)
        # Extract title and alternative titles
        parts = [p.strip() for p in header_text.split('/')]
        title = parts[0]
        alternative_titles = parts[1:] if len(parts) > 1 else []
        
        print(f"Processing: {title}")
        
        entry_notes = []
        steps = []
        
        # Collect content until the next separator
        content_html = ""
        for sibling in h3.find_next_siblings():
            if sibling.name == 'h3' or sibling.name == 'hr':
                break
            content_html += str(sibling)
        
        content_soup = BeautifulSoup(content_html, 'lxml')
        
        # --- Find all MAL links to create the steps ---
        all_mal_links = content_soup.find_all('a', href=re.compile(r'myanimelist\.net/anime/(\d+)'))
        mal_ids_in_order = []
        for a_tag in all_mal_links:
            match = re.search(r'myanimelist\.net/anime/(\d+)', a_tag['href'])
            if match:
                mal_id = int(match.group(1))
                if mal_id not in mal_ids_in_order:
                    mal_ids_in_order.append(mal_id)
        
        # --- Batch fetch data from AniList ---
        time.sleep(1) # Rate limit
        anilist_data_map = fetch_anilist_data_batch(mal_ids_in_order)
        
        # --- Process each link into a structured step ---
        for mal_id in mal_ids_in_order:
            media_data = anilist_data_map.get(mal_id)
            if not media_data:
                continue

            # Find the original link tag to get its context
            link_tag = content_soup.find('a', href=re.compile(f'myanimelist.net/anime/{mal_id}'))
            step_text = link_tag.get_text(strip=True) if link_tag else "Unknown"

            # Check for optional tag
            is_optional = '(Optional)' in link_tag.find_parent().get_text() if link_tag and link_tag.find_parent() else False

            # Clean up studio data
            media_data['studios'] = [node['name'] for node in media_data.get('studios', {}).get('nodes', [])]

            steps.append({
                "step_title": step_text,
                "is_optional": is_optional,
                "notes": None, # More advanced parsing would be needed for this
                "media": {
                    "anilist_id": media_data.get('id'),
                    "mal_id": mal_id,
                    **media_data
                }
            })

        # --- Extract general notes for the entry ---
        note_tag = content_soup.find('strong', string=re.compile(r'Note:?'))
        if note_tag:
            notes_text = []
            for note_sibling in note_tag.find_next_siblings():
                if note_sibling.name not in ['p', 'ul', 'li']:
                    break
                notes_text.append(note_sibling.get_text(separator='\n', strip=True))
            entry_notes.append("\n".join(notes_text))
            
        api_entries.append({
            "title": title,
            "alternative_titles": alternative_titles,
            "entry_notes": "\n".join(entry_notes).strip() or None,
            "steps": steps
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

        api_data = parse_and_enrich_watch_orders(html)
        
        final_output = {
            "metadata": {
                "version": "1.0",
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
        sys.exit(1)

if __name__ == "__main__":
    main()
