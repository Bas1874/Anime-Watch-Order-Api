# scrape_wiki.py (Final Authentication Version)
import requests
import json
import sys
import os

# --- Step 1: Get Credentials from Environment Variables ---
# GitHub Actions will populate these from the secrets we just set
CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")
USERNAME = os.environ.get("REDDIT_USERNAME")
PASSWORD = os.environ.get("REDDIT_PASSWORD")

# Check if all secrets are available
if not all([CLIENT_ID, CLIENT_SECRET, USERNAME, PASSWORD]):
    print("Error: Missing one or more Reddit credentials in environment variables.")
    sys.exit(1)

# --- Step 2: Authenticate and Get Access Token ---
try:
    print("Authenticating with Reddit API...")
    auth = requests.auth.HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET)
    data = {
        'grant_type': 'password',
        'username': USERNAME,
        'password': PASSWORD,
    }
    headers = {'User-Agent': 'SeanimeScraper/0.1 by ' + USERNAME}
    
    res = requests.post('https://www.reddit.com/api/v1/access_token',
                        auth=auth, data=data, headers=headers)
    res.raise_for_status()
    
    access_token = res.json()['access_token']
    print("Successfully obtained API access token.")
    
except Exception as e:
    print(f"Error during authentication: {e}")
    sys.exit(1)

# --- Step 3: Fetch Wiki Data Using the Access Token ---
try:
    # Use the oauth.reddit.com endpoint for authenticated requests
    wiki_url = "https://oauth.reddit.com/r/anime/wiki/watch_order"
    # Add the access token to the headers
    headers['Authorization'] = f'bearer {access_token}'
    
    print(f"Fetching data from {wiki_url}...")
    response = requests.get(wiki_url, headers=headers)
    response.raise_for_status()
    
    data = response.json()
    html_content = data.get("data", {}).get("content_html", "")

    if not html_content:
        print("Error: Could not find 'content_html' in the response.")
        sys.exit(1)

    # --- Step 4: Save the Data ---
    output_filepath = sys.argv[1]
    output_data = {"html": html_content}

    with open(output_filepath, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4)
    
    print(f"Successfully saved wiki data to {output_filepath}")

except Exception as e:
    print(f"An error occurred during data fetching or saving: {e}")
    sys.exit(1)
