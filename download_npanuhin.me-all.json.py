import os
import json
import requests

# 0. You don't need this script, it's an old script that by now has been fully incorporated in 
# 1. grab_everything_singlethreaded_with_deduplication_and_automatic-npanuhin.me-all.json_download.py
# and in 2. grab_everything_multithreaded_with_deduplication_and_automatic-npanuhin.me-all.json_download.py
# So you don't need it... But it should still work in case you want. It will download the all.json for you
# The output file is .\all.json.latest and gets overwritten at each run.

# 1. Pipeline Configurations
JSON_URL = "https://bing.npanuhin.me/all.json"
TARGET_DIR = r"C:\_BingBackgrounds.py\anerg.com.py"
LOCAL_JSON_PATH = os.path.join(TARGET_DIR, "all.json.latest")

# Standardized headers optimized for automatic server stream decompression
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Connection": "keep-alive"
}

def download_database():
    """Downloads the remote all.json database and stores it locally as a pretty-printed archive."""
    print(f"[*] Initializing remote database synchronization routine...")
    print(f"[*] Target Endpoint: {JSON_URL}")
    print(f"[*] Output Target: {LOCAL_JSON_PATH} (Overwriting with restructured JSON)")
    
    try:
        # Enforce automatic stream handling and runtime decompression (GZIP/Brotli)
        response = requests.get(JSON_URL, headers=headers, timeout=60)
        
        if response.status_code == 200:
            print("[+] Connection established! Database payload received successfully.")
            print("[*] Restructuring remote dataset into pretty-printed local archive...")
            
            # Direct runtime parsing of the binary compressed stream bytes into a python dictionary
            parsed_json = response.json()
            
            # Serialize the dictionary to disk with indent=4 for optimal human-readability in text editors
            with open(LOCAL_JSON_PATH, 'w', encoding='utf-8') as f:
                json.dump(parsed_json, f, indent=4, ensure_ascii=False)
                
            # Verify the actual serialized file footprint on local storage
            final_size = os.path.getsize(LOCAL_JSON_PATH)
            print(f"[🎉] Sync complete! all.json.latest refreshed successfully ({final_size / (1024*1024):.2f} MB).")
            print("[+] Structural validation successful! The cache manifest text is ready for execution.")
        else:
            print(f"[!] Target endpoint rejected transaction. HTTP Status Code: {response.status_code}")
            
    except Exception as e:
        print(f"\n[!] Critical network failure during database ingestion: {e}")

if __name__ == "__main__":
    download_database()
