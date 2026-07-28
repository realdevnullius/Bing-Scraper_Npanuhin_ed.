import os
import time
import json
import sys
import re
import requests
import piexif
from PIL import Image

# Dynamic execution path resolution (portable across drives/directories)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ARCHITECTURAL PATH ROUTING STRATEGY:
# False -> Persists assets inside structured hierarchical subdirectories (e.g., _OUT\2026\image.jpg)
# True  -> Flattens the dependency graph and writes assets directly into root (e.g., _OUT\image.jpg)
# NOTE: Required for legacy shell background switchers lacking recursive directory traversal support.
FLATTEN_OUTPUT = False
#FLATTEN_OUTPUT = True

# Remote JSON Manifest Source for Bing Image of the Day archive
JSON_URL = "https://bing.npanuhin.me/all.json"

LOCAL_JSON_PATH = os.path.join(SCRIPT_DIR, "all.json.latest")
DOWNLOAD_DIR = os.path.join(SCRIPT_DIR, "_OUT")

# ISO-639-1 / BCP 47 Region Mapping Architecture
REGIONS = {
    'us': 'US-en', 'uk': 'GB-en', 'de': 'DE-de', 'fr': 'FR-fr',
    'ja': 'JP-ja', 'au': 'AU-en', 'cn': 'CN-zh', 'ca': 'CA-en',
    'in': 'IN-en', 'br': 'BR-pt', 'row': 'ROW-en'
}

# Guarantee root target directory existence prior to sequential execution
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Standardized User-Agent headers to satisfy CDN edge firewall inspection rules
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}


def sync_central_database():
    """Fetches the remote database manifest and serializes an updated local AST representation."""
    print(" [*] Initializing remote database synchronization routine...")
    print(f" [*] Target Endpoint: {JSON_URL}")
    print("[*] Fetching payload... Automatic runtime stream decoding active.")

    api_headers = {
        "User-Agent": headers["User-Agent"],
        "Accept": "application/json",
        "Connection": "keep-alive"
    }

    try:
        response = requests.get(JSON_URL, headers=api_headers, timeout=60)
        if response.status_code == 200:
            print("[+] Connection established! Database payload received successfully.")
            print(" [*] Restructuring remote dataset into pretty-printed local archive...")

            parsed_json = response.json()
            with open(LOCAL_JSON_PATH, 'w', encoding='utf-8') as f:
                json.dump(parsed_json, f, indent=4, ensure_ascii=False)

            final_size = os.path.getsize(LOCAL_JSON_PATH)
            print(f"[ ] Sync complete! all.json.latest refreshed successfully 🎉 ({final_size / (1024*1024):.2f} MB).")
            return True
        else:
            print(f"[!] Target endpoint rejected transaction. HTTP Status Code: {response.status_code}")
            return False
    except Exception as e:
        print(f"[!] Critical network failure during database ingestion: {e}")
        return False


def inject_metadata_iptc(file_path, title, description, copyright_text):
    """Hard-injects EXIF/IPTC metadata into target JPEG markers optimized for Windows Shell indexers."""
    try:
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "Interop": {}, "1st": {}, "thumbnail": None}

        if title:
            exif_dict["0th"][0x9c9b] = title.encode('utf-16le')
            exif_dict["0th"][0x010e] = title.encode('utf-8')

        if description:
            exif_dict["0th"][0x9c9c] = description.encode('utf-16le')

        if copyright_text:
            exif_dict["0th"][0x8298] = copyright_text.encode('utf-8')

        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, file_path)
        return True
    except Exception as e:
        print(f" [Warning] Shell metadata injection vector failed: {e}")
        return False


def clean_title(title_str):
    """Sanitizes raw string payloads into deterministic signatures while preserving global Unicode (CJK) glyphs."""
    if not title_str:
        return "BingImage"

    stop_words = {
        'the', 'in', 'on', 'at', 'of', 'and', 'a', 'an', 'to', 'for', 'with', 'off',
        'from', 'by', 'as', 'into', 'over', 'through', 'about', 'under', 'above',
        'between', 'among', 'during', 'without', 'against', 'including', 'across'
    }

    clean = re.sub(r'[\x00-\x1f\\/:*?"<>|,\. !?’’“” ]|，|。|！|＿|：', ' ', title_str)
    words = clean.split()

    filtered_words = []
    for w in words:
        if w.lower() not in stop_words:
            filtered_words.append(w.capitalize() if w.isascii() else w)

    if not filtered_words:
        return "BingImage"

    raw_cleaned = " ".join(filtered_words)

    if len(raw_cleaned) > 60:
        raw_cleaned = raw_cleaned[:60].rstrip(' ')

    return raw_cleaned


def load_local_json(path):
    """Deserializes local JSON cache and executes fallback token recovery on truncated streams."""
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
    """Executes single-threaded I/O stream ingestion, asserts binary validity, and injects metadata tags."""
    date_str, img_name, img_url, title, description, copyright_text = task

    # --- STRICT ARCHIVAL DATE & YEAR DIRECTORY EXTRACTION ---
    raw_date_str = str(date_str) if date_str else ""
    year_match = re.search(r'\b(\d{4})\b', raw_date_str)

    if year_match:
        year_str = year_match.group(1)
        # Preserve all digits found (e.g. 20260728, 202607, 2026) for filename prefix without inventing fake values
        clean_date = re.sub(r'[^\d]', '', raw_date_str)
        if not clean_date:
            clean_date = year_str
    else:
        # Unknown year fallback: Assets without year go directly to 0000 folder
        year_str = "0000"
        clean_date = "(Date missing)"

    # Evaluate dynamic path resolver based on global FLATTEN_OUTPUT toggle
    if FLATTEN_OUTPUT:
        target_folder = DOWNLOAD_DIR
        log_path_display = ""
    else:
        target_folder = os.path.join(DOWNLOAD_DIR, year_str)
        log_path_display = f"{year_str}\\"

    # Idempotent directory tree generation
    os.makedirs(target_folder, exist_ok=True)

    # --- MICROSOFT ARCHIVAL IDENTIFIER EXTRACTION ---
    ms_code = None
    try:
        raw_code = img_url.split("id=OHR.")[-1].split("&")[0] if "id=OHR." in img_url else (
            img_url.split("/OHR.")[-1] if "/OHR." in img_url else img_url.split("/")[-1]
        )
        match = re.search(r'([A-Za-z]{2,4}-?[A-Za-z]{2,4}?\d{5,12}_(?:UHD|\d{3,4}x\d{3,4}))', raw_code, re.IGNORECASE)
        if match:
            ms_code = match.group(1)
    except Exception:
        ms_code = None

    # Construct target filename with optional Microsoft codename signature
    if ms_code:
        filename = f"{clean_date}_{img_name} ({ms_code}).jpg"
    else:
        filename = f"{clean_date}_{img_name}.jpg"

    file_path = os.path.join(target_folder, filename)

    # Local disk deduplication: Skip I/O cycles if non-empty target already exists
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return None

    # Mutate resolution path parameters to request 4K Ultra HD streams
    if "1920x1080" in img_url:
        target_url = img_url.replace("1920x1080", "UHD")
    elif "1366x768" in img_url:
        target_url = img_url.replace("1366x768", "UHD")
    elif "_UHD.jpg" in img_url:
        target_url = img_url
    else:
        target_url = img_url + "&rf=LaDigue_UHD.jpg"

    if target_url.startswith("/"):
        target_url = "https://bing.com" + target_url
    elif "bing.com" in target_url and not target_url.startswith("http"):
        target_url = "https://" + target_url

    time.sleep(0.2) # Throttle connection initiation rate

    try:
        # --- EXECUTE ULTRA HD (4K) DOWNLOAD VECTOR ---
        img_res = requests.get(target_url, headers=headers, timeout=15, stream=True)
        if img_res.status_code == 200:
            with open(file_path, 'wb') as f:
                for chunk in img_res.iter_content(chunk_size=65536):
                    f.write(chunk)

            # BINARY VALIDATION: Assert image stream integrity before proceeding
            try:
                if os.path.getsize(file_path) > 0:
                    with Image.open(file_path) as img:
                        img.verify()

                    meta_status = inject_metadata_iptc(file_path, title, description, copyright_text)
                    meta_tag = " + Metadata EXIF/IPTC" if meta_status else ""
                    return f"[UHD Download] -> {log_path_display}{filename}{meta_tag}"
            except Exception:
                if os.path.exists(file_path):
                    os.remove(file_path) # Purge corrupt payload

        # --- EXECUTE 1080p HD FALLBACK ROUTINE ---
        fallback_url = "https://bing.com" + img_url if img_url.startswith("/") else img_url
        if "bing.com" in fallback_url and not fallback_url.startswith("http"):
            fallback_url = "https://" + fallback_url

        fb_res = requests.get(fallback_url, headers=headers, timeout=15, stream=True)
        if fb_res.status_code == 200:
            with open(file_path, 'wb') as f:
                for chunk in fb_res.iter_content(chunk_size=65536):
                    f.write(chunk)

            # BINARY VALIDATION (FALLBACK STREAM):
            try:
                if os.path.getsize(file_path) > 0:
                    with Image.open(file_path) as img:
                        img.verify()
                    inject_metadata_iptc(file_path, title, description, copyright_text)
                    return f"[HD Fallback] -> {log_path_display}{filename} + Metadata EXIF/IPTC"
            except Exception:
                if os.path.exists(file_path):
                    os.remove(file_path)
    except Exception:
        if os.path.exists(file_path):
            os.remove(file_path)

    return f"[FAILED] -> {filename}"


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

            img_url = bing_url if bing_url else storage_url
            if not img_url:
                continue

            # 1. Extract canonical Microsoft internally-assigned codename
            base_key = None
            try:
                if "id=OHR." in img_url:
                    raw_part = img_url.split("id=OHR.")[-1]
                    base_key = re.split(r'_[A-Za-z]{2}-[A-Za-z]{2}|_[A-Za-z]{3,4}\d', raw_part)[0].lower()
                else:
                    base_key = img_url.split("/")[-1].split("_")[0].replace(".jpg", "").lower()
            except Exception:
                base_key = str(date_str).replace("-", "") if date_str else "unknown_date"

            if not base_key or len(base_key) < 3 or base_key in ["bingimage", "wallpaper", "image"]:
                base_key = f"date_{str(date_str).replace('-', '')}"

            if base_key:
                base_key = re.sub(r'(\d{2})y$', r'20\1', base_key)
                if 'lanterfestival' in base_key:
                    base_key = base_key.replace('lanterfestival', 'lanternfestival')

            # 2. Resolve localized geographic entity string (CJK/Unicode Unlocked)
            img_name = None
            if title and title.strip():
                img_name = clean_title(title)
            if not img_name and caption and caption.strip() and caption.lower() != "info":
                img_name = clean_title(caption)
            if not img_name and entry.get('name'):
                img_name = entry.get('name')

            # Fallback Strategy: Tokenize and re-space raw CamelCase codenames
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
                        working_name = re.sub(
                            f'(?<=[A-Za-z])({kw})(?=[A-Za-z])|(?<=[A-Za-z])({kw})$|^({kw})(?=[A-Za-z])',
                            r' \1\2\3 ', working_name, flags=re.IGNORECASE
                        )

                    working_name = working_name if any(c.isupper() for c in working_name) else working_name.capitalize()
                    working_name = re.sub(r'(?<!^)(?=[A-Z])', ' ', working_name)
                    working_name = re.sub(r'\b25\b', '2025', str(working_name))
                    working_name = re.sub(r'\b26\b', '2026', str(working_name))
                    working_name = re.sub(r'(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])', ' ', working_name)
                    img_name = clean_title(working_name)

            # High-Priority Unicode Protection Fallback
            if not img_name or img_name.lower() in ["bingimage", "wallpaper", "image"] or img_name.startswith("date_"):
                if title and title.strip():
                    img_name = clean_title(title)
                elif caption and caption.strip() and caption.lower() != "info":
                    img_name = clean_title(caption)

            safe_date_label = str(date_str).replace('-', '') if date_str else "(Date missing)"
            if not img_name or img_name.lower() in ["bingimage", "wallpaper", "image"]:
                img_name = f"Wallpaper_{safe_date_label}"
            if len(img_name) < 3:
                img_name = f"Wallpaper_{safe_date_label}"

            # 3. State-Collision Resolution: RAM Deduplication with CJK Glyph Guard
            if base_key not in unique_wallpapers:
                unique_wallpapers[base_key] = (date_str, img_name, img_url, title, description, copyright_text)
            else:
                existing_task = unique_wallpapers[base_key]
                existing_name = existing_task[1]

                is_existing_generic = existing_name.lower().startswith("wallpaper_") or existing_name.lower().startswith("bingimage_")
                is_new_better = not img_name.lower().startswith("wallpaper_") and not img_name.lower().startswith("bingimage_")

                # UNICODE GUARD: Prevents rich non-Latin metadata entries from being overwritten by US/UK regional defaults
                if (is_existing_generic and is_new_better) or (short_name in ['us', 'uk'] and is_existing_generic):
                    unique_wallpapers[base_key] = (date_str, img_name, img_url, title, description, copyright_text)

    download_queue = list(unique_wallpapers.values())
    download_queue.sort(key=lambda x: str(x[0]), reverse=True)

    total_tasks = len(download_queue)
    print(f"[+] Deduplication complete! {total_tasks} TRULY WORLDWIDE UNIQUE images with metadata ready.")
    print(f"[*] Starting single-threaded download pipeline (Safe mode with EXIF/IPTC injection)...\n")

    # SEQUENTIAL SINGLE-THREADED INGESTION LOOP
    try:
        for task in download_queue:
            result = download_single_wallpaper(task)
            if result:
                print(result)
    except KeyboardInterrupt:
        print("\n[!] Ctrl+C detected! Aborting script execution immediately.")
        sys.exit(0)

    print(f"\n[ ] Outstanding! The metadata-enriched asset archiving is complete 🎉\nin:\n{DOWNLOAD_DIR}")


if __name__ == "__main__":
    main()