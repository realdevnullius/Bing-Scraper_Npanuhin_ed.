import os
import time
import json
import sys
import re
import requests
import piexif
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

# 1. Global Architectural Configurations
REGIONS = {
    'us': 'US-en', 'uk': 'GB-en', 'de': 'DE-de', 'fr': 'FR-fr',
    'ja': 'JP-ja', 'au': 'AU-en', 'cn': 'CN-zh', 'ca': 'CA-en',
    'in': 'IN-en', 'br': 'BR-pt', 'row': 'ROW-en'
}

MAX_WORKERS = 3 

# N. Pahunin's all.json for his Bing Image of the Day archive
JSON_URL = "https://bing.npanuhin.me/all.json"

# Change the value of SCRIPT_DIR to the installation folder where you put this script
SCRIPT_DIR = r"C:\_BingBackgrounds.py\anerg.com.py"
LOCAL_JSON_PATH = os.path.join(SCRIPT_DIR, "all.json.latest")
DOWNLOAD_DIR = os.path.join(SCRIPT_DIR, "_OUT")

# THE CONFIGURATION TOGGLE SWITCH:
# Set to False -> Saves assets inside structured nested directories (e.g., _OUT\2026\07\image.jpg)
# Set to True  -> Saves all assets directly into a single flattened root folder (e.g., _OUT\image.jpg)
# TIP: https://johnsad.ventures/software/backgroundswitcher/ does not recurse subdirectories and needs a FLAT structure!
FLATTEN_OUTPUT = True

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Standardized client identification payload to prevent remote connection drops
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}

def sync_central_database():
    """Downloads the all.json remote manifest and updates the local all.json.latest archive."""
    print(f"[*] Initialising remote database synchronization routine...")
    print(f"[*] Target Endpoint: {JSON_URL}")
    print(f"[*] Fetching payload... Automatic runtime stream decoding active.")
    
    api_headers = {
        "User-Agent": headers["User-Agent"],
        "Accept": "application/json",
        "Connection": "keep-alive"
    }
    
    try:
        response = requests.get(JSON_URL, headers=api_headers, timeout=60)
        if response.status_code == 200:
            print("[+] Connection established! Database payload received successfully.")
            print("[*] Restructuring remote dataset into pretty-printed local archive...")
            
            parsed_json = response.json()
            with open(LOCAL_JSON_PATH, 'w', encoding='utf-8') as f:
                json.dump(parsed_json, f, indent=4, ensure_ascii=False)
                
            final_size = os.path.getsize(LOCAL_JSON_PATH)
            print(f"[🎉] Sync complete! all.json.latest refreshed successfully ({final_size / (1024*1024):.2f} MB).")
            return True
        else:
            print(f"[!] Target endpoint rejected transaction. HTTP Status Code: {response.status_code}")
            return False
    except Exception as e:
        print(f"[!] Critical network failure during database ingestion: {e}")
        return False


def inject_metadata_iptc(file_path, title, description, copyright_text):
    """Injects contextual EXIF metadata tags optimized for Windows Explorer shell indexing."""
    try:
        # Note: Windows file properties parsing requires strict UTF-16LE Byte Order Mark strings for XP tags
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "Interop": {}, "1st": {}, "thumbnail": None}
        
        # Win32 Shell API specific mappings: 0x9c9b = XPTitle, 0x9c9c = XPComment, 0x8298 = Copyright
        if title:
            exif_dict["0th"][0x9c9b] = title.encode('utf-16le')
            exif_dict["0th"][0x010e] = title.encode('utf-8') # Standard fallback ImageDescription
            
        if description:
            exif_dict["0th"][0x9c9c] = description.encode('utf-16le')
            
        if copyright_text:
            exif_dict["0th"][0x8298] = copyright_text.encode('utf-8')
            
        # Compile dictionary layout into a raw binary EXIF stream
        exif_bytes = piexif.dump(exif_dict)
        
        # Hard-inject compiled binary payload into target JPEG marker headers
        piexif.insert(exif_bytes, file_path)
        return True
    except Exception as e:
        print(f" [Warning] Shell metadata injection vector failed: {e}")
        return False

def clean_title(title_str):
    """Sanitizes raw string payloads into deterministic, underscore-delimited signatures, preserving global Unicode characters."""
    if not title_str:
        return "BingImage"
        
    stop_words = {
        'the', 'in', 'on', 'at', 'of', 'and', 'a', 'an', 'to', 'for', 'with', 'off', 
        'from', 'by', 'as', 'into', 'over', 'through', 'about', 'under', 'above', 
        'between', 'among', 'during', 'without', 'against', 'including', 'across'
    }
    
    # STANDARDIZED UNICODE REGEX: Filtert Windows pad-leestekens en behoudt Aziatische tekens vloeiend
    clean = re.sub(r'[\x00-\x1f\\/:*?"<>|,\. !?’’“”，。！＿：]', ' ', title_str)
    words = clean.split()
    
    filtered_words = []
    for w in words:
        if w.lower() not in stop_words:
            # Capitalize western words, keep Asian scripts untouched
            filtered_words.append(w.capitalize() if w.isascii() else w)
            
    if not filtered_words:
        return "BingImage"
        
    raw_cleaned = "_".join(filtered_words)
    
    # LENGTEBEVEILIGING: Harde knip op 90 tekens tegen de Windows MAX_PATH-crashes
    if len(raw_cleaned) > 90:
        raw_cleaned = raw_cleaned[:90].rstrip('_')
        
    return raw_cleaned


def load_local_json(path):
    """Reads the local all.json.latest cache file and attempts to hot-fix missing structural trailing tokens."""
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read().strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        print("[!] Local JSON payload is corrupted or incomplete. Executing automated recovery block...")
        if not content.endswith('}'):
            if content.endswith(']'):
                content += '}'
            else:
                content += ']}'
        try:
            return json.loads(content)
        except Exception as e:
            print(f"[!] Critical structural failure parsing recovered all.json.latest: {e}")
            return None


def download_single_wallpaper(task):
    """Processes the download, enforces file integrity, and listens to the FLATTEN_OUTPUT setting."""
    date_str, img_name, img_url, title, description, copyright_text = task
    
    clean_date = date_str.replace("-", "")          # e.g., "20260727"
    year_str = clean_date[:4]                       # Extracts "2026"
    month_str = clean_date[4:6]                     # Extracts "07"
    
    # 1. Choice of Quality: determine the target folder based on the setting FLATTEN_OUTPUT at the top
    if FLATTEN_OUTPUT:
        target_folder = DOWNLOAD_DIR
        log_path_display = ""
    else:
        target_folder = os.path.join(DOWNLOAD_DIR, year_str, month_str)
        log_path_display = f"{year_str}\\{month_str}\\"
        
    # FIX: Zorg dat de map altijd veilig wordt aangemaakt, ongeacht de FLATTEN_OUTPUT stand
    os.makedirs(target_folder, exist_ok=True)

    # 2. PRESERVE ORIGINAL FILENAME FORMAT: Maintain exact clean formatting architecture
    filename = f"{clean_date}_{img_name}.jpg"
    file_path = os.path.join(target_folder, filename)

    # EXTRA FAIL-SAFE: Overslaan mits het bestand bestaat EN groter is dan 0 bytes (repareert corrupte downloads)
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return None

    # Upgrade asset path resolution to Ultra HD (4K)
    if "1920x1080" in img_url:
        target_url = img_url.replace("1920x1080", "UHD")
    elif "1366x768" in img_url:
        target_url = img_url.replace("1366x768", "UHD")
    elif "_UHD.jpg" in img_url:
        target_url = img_url
    else:
        target_url = img_url + "&rf=LaDigue_UHD.jpg"

    # Enforce secure fully-qualified domain endpoints to eliminate redirect latency
    if target_url.startswith("/"):
        target_url = "https://bing.com" + target_url
    elif "bing.com" in target_url and not target_url.startswith("http"):
        target_url = "https://" + target_url

    # Add atomic throttling delay to safeguard client against rate-limiting blocks
    time.sleep(0.2)

    try:
        # --- EXECUTE UHD ATTEMPT ---
        img_res = requests.get(target_url, headers=headers, timeout=15, stream=True)
        if img_res.status_code == 200:
            with open(file_path, 'wb') as f:
                for chunk in img_res.iter_content(chunk_size=65536):
                    f.write(chunk)
            
            # INTEGRITEITSFAIL-SAFE: Controleer of de JPEG niet corrupt is binnengekomen in deze thread
            try:
                if os.path.getsize(file_path) > 0:
                    with Image.open(file_path) as img:
                        img.verify()  # Gooit een exception als de binaire data incompleet/corrupt is
                    
                    meta_status = inject_metadata_iptc(file_path, title, description, copyright_text)
                    meta_tag = " + Metadata EXIF/IPTC" if meta_status else ""
                    return f"[UHD Download] -> {log_path_display}{filename}{meta_tag}"
            except Exception:
                if os.path.exists(file_path):
                    os.remove(file_path)  # Direct vernietigen om loze bestanden te voorkomen
                # Schakel geruisloos over naar de HD Fallback routine hieronder

        # --- EXECUTE HD FALLBACK ROUTINE ---
        fallback_url = "https://bing.com" + img_url if img_url.startswith("/") else img_url
        if "bing.com" in fallback_url and not fallback_url.startswith("http"):
            fallback_url = "https://" + fallback_url
                
        fb_res = requests.get(fallback_url, headers=headers, timeout=15, stream=True)
        if fb_res.status_code == 200:
            with open(file_path, 'wb') as f:
                for chunk in fb_res.iter_content(chunk_size=65536):
                    f.write(chunk)
            
            # INTEGRITEITSFAIL-SAFE OOK OP HD FALLBACK:
            try:
                if os.path.getsize(file_path) > 0:
                    with Image.open(file_path) as img:
                        img.verify()
                    inject_metadata_iptc(file_path, title, description, copyright_text)
                    return f"[HD Fallback]  -> {log_path_display}{filename} + Metadata EXIF/IPTC"
            except Exception:
                if os.path.exists(file_path):
                    os.remove(file_path)
    except Exception:
        if os.path.exists(file_path):
            os.remove(file_path)
    
    return f"[Failed]      -> {filename}"


def clean_title(title_str):
    """Sanitizes raw string payloads into deterministic, underscore-delimited title signatures by stripping noise and stopwords."""
    if not title_str:
        return "BingImage"
        
    stop_words = {
        'the', 'in', 'on', 'at', 'of', 'and', 'a', 'an', 'to', 'for', 'with', 'off', 
        'from', 'by', 'as', 'into', 'over', 'through', 'about', 'under', 'above', 
        'between', 'among', 'during', 'without', 'against', 'including', 'across'
    }
    
    # Strip syntax noise, capture tokens, and capitalize non-stopword components
    clean = re.sub(r'[^a-zA-Z0-9\s]', '', title_str)
    words = clean.split()
    
    filtered_words = []
    for w in words:
        if w.lower() not in stop_words:
            filtered_words.append(w.capitalize())
            
    if not filtered_words:
        return "BingImage"
        
    return "_".join(filtered_words)


def main():
    sync_central_database()
    print("-" * 60)
    
    if not os.path.exists(LOCAL_JSON_PATH):
        print(f"[!] CRITICAL ERROR: all.json.latest is missing!")
        return
        
    db = load_local_json(LOCAL_JSON_PATH)
    if not db:
        print(f"[!] CRITICAL ERROR: Could not parse all.json.latest!")
        return
        
    print("[+] The database has been loaded successfully! Starting fool-proof cross-region deduplication in RAM...")
    
    unique_wallpapers = {}
    
    for short_name, json_key in REGIONS.items():
        actual_key = next((k for k in db.keys() if k.lower() == json_key.lower()), None)
        if not actual_key:
            continue
            
        for entry in db[actual_key]:
            date_str = entry.get('date')
            bing_url = entry.get('bing_url')
            storage_url = entry.get('url')
            title = entry.get('title')
            caption = entry.get('caption')
            description = entry.get('description')
            copyright_text = entry.get('copyright')
            
            if not date_str:
                continue
                
            img_url = bing_url if bing_url else storage_url
            if not img_url:
                continue
                
            # 1. Grab the ORIGINAL Microsoft-codename
            base_key = None
            try:
                if "id=OHR." in img_url:
                    raw_part = img_url.split("id=OHR.")[-1]
                    base_key = re.split(r'_[A-Za-z]{2}-[A-Za-z]{2}|_[A-Za-z]{3,4}\d', raw_part)[0].lower()
                else:
                    base_key = img_url.split("/")[-1].split("_")[0].replace(".jpg", "").lower()
            except Exception:
                base_key = date_str.replace("-", "")
                
            if not base_key or len(base_key) < 3 or base_key in ["bingimage", "wallpaper", "image"]:
                base_key = f"date_{date_str.replace('-', '')}"
                
            if base_key:
                base_key = re.sub(r'(\d{2})y$', r'20\1', base_key)
                if 'lanterfestival' in base_key:
                    base_key = base_key.replace('lanterfestival', 'lanternfestival')
                    
            # 2. Generate the clean geographical filename for the local disk based on the local title
            img_name = None
            if title and re.search(r'[a-zA-Z]', title):
                img_name = clean_title(title)
            if not img_name and caption and caption.lower() != "info" and re.search(r'[a-zA-Z]', caption):
                img_name = clean_title(caption)
            if not img_name and entry.get('name'):
                img_name = entry.get('name')
                
            # Step E: CamelCase Washer en splitser
            if not img_name or img_name.lower() in ["bingimage", "wallpaper", "image"]:
                if base_key and not base_key.startswith("date_"):
                    working_name = base_key
                    
                    bing_keywords = [
                        'day', 'season', 'festival', 'summer', 'spring', 'autumn', 'winter',
                        'labor', 'work', 'may', 'sky', 'tree', 'tower', 'bridge', 'beach',
                        'bay', 'lake', 'river', 'park', 'shiba', 'zakura', 'showa', 'era',
                        'lunar', 'new', 'year', 'eve', 'of', 'lantern'
                    ]
                    for kw in bing_keywords:
                        working_name = re.sub(f'(?<=[A-Za-z])({kw})(?=[A-Za-z])|(?<=[A-Za-z])({kw})$|^({kw})(?=[A-Za-z])', r' \1\2\3 ', working_name, flags=re.IGNORECASE)
                        
                    working_name = working_name if any(c.isupper() for c in working_name) else working_name.capitalize()
                    working_name = re.sub(r'(?<!^)(?=[A-Z])', ' ', working_name)
                    working_name = re.sub(r'\b25\b', '2025', str(working_name))
                    working_name = re.sub(r'\b26\b', '2026', str(working_name))
                    working_name = re.sub(r'(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])', ' ', working_name)
                    img_name = clean_title(working_name)
            
            # Priority 5 (THE ULTIMATE PREMIUM UNICODE BACKUP): Native character injection
            if not img_name or img_name.lower() in ["bingimage", "wallpaper", "image"] or img_name.startswith("date_"):
                if title and title.strip():
                    img_name = clean_title(title)
                elif caption and caption.strip() and caption.lower() != "info":
                    img_name = clean_title(caption)
                    
            if not img_name or img_name.lower() in ["bingimage", "wallpaper", "image"]:
                img_name = f"Wallpaper_{date_str.replace('-', '')}"
            if len(img_name) < 3:
                img_name = f"Wallpaper_{date_str.replace('-', '')}"
                
            # 3. Smart cross-region deduplication with enhanced quality and UNICODE PROTECTION check
            if base_key not in unique_wallpapers:
                unique_wallpapers[base_key] = (date_str, img_name, img_url, title, description, copyright_text)
            else:
                existing_task = unique_wallpapers[base_key]
                existing_name = existing_task[1]
                
                is_existing_generic = existing_name.lower().startswith("wallpaper_") or existing_name.lower().startswith("bingimage_")
                is_new_better = not img_name.lower().startswith("wallpaper_") and not img_name.lower().startswith("bingimage_")
                
                # UNICODE PROTECTOR: Voorkomt dat rijke Aziatische Unicode-titels worden overschreven door US/UK-regio's
                if (is_existing_generic and is_new_better) or (short_name in ['us', 'uk'] and is_existing_generic):
                    unique_wallpapers[base_key] = (date_str, img_name, img_url, title, description, copyright_text)
                    
    download_queue = list(unique_wallpapers.values())
    download_queue.sort(key=lambda x: x[0], reverse=True)
    
    total_tasks = len(download_queue)
    print(f"[+] Deduplication complete! {total_tasks} TRULY WORLDWIDE UNIQUE images with metadata ready.")
    print(f"[*] Multi-threading started with {MAX_WORKERS} concurrent connections (Safe mode with EXIF/IPTC injection)...\n")
    
    # ACTIVATES THE MULTI-THREADED THREADPOOL ENGINES
    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(download_single_wallpaper, task): task for task in download_queue}
            
            try:
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        print(result)
            except KeyboardInterrupt:
                print("\n[!] Ctrl+C detected! Emptying multi-threaded task queue...")
                executor.shutdown(wait=False, cancel_futures=True)
                print("[X] Hard-killing active network background threads...")
                os._exit(0)
                
    except KeyboardInterrupt:
        print("\n[X] Script execution successfully aborted.")
        os._exit(0)
        
    print(f"\n[ ] Outstanding! The metadata-enriched asset archiving is complete 🎉\nin:\n{DOWNLOAD_DIR}")

if __name__ == "__main__":
    main()
