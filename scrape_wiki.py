# scrape_wiki.py
import requests
import json
import os

# The URL for the Reddit wiki JSON content
REDDIT_WIKI_URL = "https://www.reddit.com/r/anime/wiki/watch_order.json"
# The name of the file we will save the data to
OUTPUT_FILENAME = "watch_order.json"

# We still need a User-Agent header for the script to work
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def scrape_and_save():
    print(f"Fetching data from {REDDIT_WIKI_URL}...")
    try:
        # Make the request to Reddit
        response = requests.get(REDDIT_WIKI_URL, headers=HEADERS)
        response.raise_for_status()  # This will raise an error for non-200 statuses

        # Parse the JSON response
        data = response.json()
        
        # Extract the HTML content
        html_content = data.get("data", {}).get("content_html", "")

        if not html_content:
            print("Error: Could not find 'content_html' in the response.")
            return

        # We will save it in a simple JSON structure for our plugin
        output_data = {
            "html": html_content
        }

        # Write the data to our output file
        with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
        
        print(f"Successfully saved wiki data to {OUTPUT_FILENAME}")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
    except json.JSONDecodeError:
        print("Error: Failed to decode JSON from response.")

if __name__ == "__main__":
    scrape_and_save()
