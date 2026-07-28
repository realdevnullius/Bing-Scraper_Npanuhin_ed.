import os
import time
import json
import sys
import re
import requests
import piexif
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ARCHITECTURAL PATH ROUTING STRATEGY:
# False -> Persists assets inside structured hierarchical subdirectories (e.g., _OUT\2026\07\image.jpg)
# True  -> Flattens the dependency graph and writes assets directly into root (e.g., _OUT\image.jpg)
FLATTEN_OUTPUT = False

MAX_WORKERS = 6
JSON_URL = "https://bing.npanuhin.me/all.json"

LOCAL_JSON_PATH = os.path.join(SCRIPT_DIR, "all.json.latest")
DOWNLOAD_DIR = os.path.join(SCRIPT_DIR, "_OUT")

REGIONS = {
    'us': 'US-en', 'uk': 'GB-en', 'de': 'DE-de', 'fr': 'FR-fr',
    'ja': 'JP-ja', 'au': 'AU-en', 'cn': 'CN-zh', 'ca': 'CA-en',
    'in': 'IN-en', 'br': 'BR-pt', 'row': 'ROW-en'
}

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}


def sync_central_database():
    CACHE_TTL_SECONDS = 5 * 3600  # 5 hours

    print(f"[*] Initialising remote database synchronization routine...")

    # Check if local cache exists and is younger than 5 hours
    if os.path.exists(LOCAL_JSON_PATH):
        file_age = time.time() - os.path.getmtime(LOCAL_JSON_PATH)
        if file_age < CACHE_TTL_SECONDS:
            hours_old = file_age / 3600
            print(f"[ ] Cache hit! 'all.json.latest' is {hours_old:.2f} hours old (< 5 hours). Skipping download. ⚡")
            return True

    print(f"[*] Cache expired or missing. Refreshing from endpoint...")
    print(f"[*] Target Endpoint: {JSON_URL}")

    api_headers = {
        "User-Agent": headers["User-Agent"],
        "Accept": "application/json",
        "Connection": "keep-alive"
    }

    try:
        response = requests.get(JSON_URL, headers=api_headers, timeout=60)
        if response.status_code == 200:
            parsed_json = response.json()
            with open(LOCAL_JSON_PATH, 'w', encoding='utf-8') as f:
                json.dump(parsed_json, f, indent=4, ensure_ascii=False)

            final_size = os.path.getsize(LOCAL_JSON_PATH)
            print(f"[ ] Sync complete! all.json.latest refreshed successfully 🎉 ({final_size / (1024*1024):.2f} MB).")
            return True
        else:
            print(f"[!] HTTP Status Code: {response.status_code}")
            return False
    except Exception as e:
        print(f"[!] Critical network failure during database ingestion: {e}")
        if os.path.exists(LOCAL_JSON_PATH):
            print("[!] Falling back to existing local 'all.json.latest' file.")
            return True
        return False


def inject_metadata_iptc(file_path, title, description, copyright_text):
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
    if not title_str:
        return "BingImage"

    stop_words = {
        'the', 'in', 'on', 'at', 'of', 'and', 'a', 'an', 'to', 'for', 'with', 'off',
        'from', 'by', 'as', 'between', 'among', 'into', 'over', 'through', 'about',
        'under', 'above', 'during', 'without', 'against', 'including', 'across'
    }

    clean = re.sub(r'[\x00-\x1f\\/:*?"<>|,\. !?’’“” ]|，|。|！|＿|：', ' ', title_str)
    words = clean.split()
    filtered_words = [w.capitalize() if w.isascii() else w for w in words if w.lower() not in stop_words]

    if not filtered_words:
        return "BingImage"

    raw_cleaned = " ".join(filtered_words)
    return raw_cleaned[:60].rstrip(' ') if len(raw_cleaned) > 60 else raw_cleaned


def load_local_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read().strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        if not content.endswith('}'):
            content += '}' if content.endswith(']') else ']}'
        try:
            return json.loads(content)
        except Exception:
            return None


def extract_ms_code(url, default_quality="HD"):
    """
    Extracts Microsoft Bing market codes and asset IDs.
    Normalizes all resolution strings (\d+x\d+) to either 'UHD' or 'HD',
    completely removing dimension numbers like 1920x1080 from filenames.
    """
    if not url:
        return default_quality

    raw = url
    if "id=OHR." in raw:
        raw = raw.split("id=OHR.")[-1]
    elif "/OHR." in raw:
        raw = raw.split("/OHR.")[-1]
    elif "OHR." in raw:
        raw = raw.split("OHR.")[-1]

    raw = raw.split("&")[0].split("?")[0]
    raw = re.sub(r'\.(jpg|jpeg|png)$', '', raw, flags=re.IGNORECASE)

    # Determine Quality Tag (UHD vs HD)
    if "uhd" in url.lower():
        quality_tag = "UHD"
    else:
        quality_tag = "HD"

    # 1. Full Market Code + ID (e.g., EN-US0450019921 or ZH-CN12345)
    m = re.search(r'([A-Za-z]{2,4}-?[A-Za-z]{2,4}?\d{5,12})', raw, re.IGNORECASE)
    if m:
        return f"{m.group(1)}_{quality_tag}"

    # 2. Market Code alone without numeric ID (e.g., EN-US, DE-DE, ROW)
    m = re.search(r'([A-Za-z]{2,4}-[A-Za-z]{2,4}|ROW)', raw, re.IGNORECASE)
    if m:
        return f"{m.group(1)}_{quality_tag}"

    # 3. Legacy Fallback (No market/asset ID) -> Returns just 'UHD' or 'HD'
    return quality_tag


def download_single_wallpaper(task):
    date_str, img_name, img_url, title, description, copyright_text = task

    # --- ACCURATE YYYY\MM PATH ROUTING ENGINE ---
    digits_only = re.sub(r'\D', '', str(date_str)) if date_str else ""

    if len(digits_only) >= 6:
        year_str = digits_only[:4]
        month_str = digits_only[4:6]
        date_prefix = digits_only[:8] if len(digits_only) >= 8 else digits_only
    elif len(digits_only) >= 4:
        year_str = digits_only[:4]
        month_str = None
        date_prefix = year_str
    else:
        year_str = "0000"
        month_str = None
        date_prefix = "0000"

    if FLATTEN_OUTPUT:
        target_folder = DOWNLOAD_DIR
        log_path_display = ""
    else:
        if year_str == "0000":
            target_folder = os.path.join(DOWNLOAD_DIR, "0000")
            log_path_display = "0000\\"
        elif month_str:
            target_folder = os.path.join(DOWNLOAD_DIR, year_str, month_str)
            log_path_display = f"{year_str}\\{month_str}\\"
        else:
            target_folder = os.path.join(DOWNLOAD_DIR, year_str)
            log_path_display = f"{year_str}\\"

    os.makedirs(target_folder, exist_ok=True)

    # Resolve UHD target URL
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

    # Resolve HD Fallback URL
    fallback_url = "https://bing.com" + img_url if img_url.startswith("/") else img_url
    if "bing.com" in fallback_url and not fallback_url.startswith("http"):
        fallback_url = "https://" + fallback_url

    # Compute clean target filenames with UHD/HD indicators
    uhd_code = extract_ms_code(target_url, default_quality="UHD")
    uhd_filename = f"{date_prefix}_{img_name} ({uhd_code}).jpg"
    uhd_file_path = os.path.join(target_folder, uhd_filename)

    hd_code = extract_ms_code(fallback_url, default_quality="HD")
    hd_filename = f"{date_prefix}_{img_name} ({hd_code}).jpg"
    hd_file_path = os.path.join(target_folder, hd_filename)

    # Check for unparenthesized/legacy filenames to prevent duplicate downloads
    legacy_filename = f"{date_prefix}_{img_name}.jpg"
    legacy_file_path = os.path.join(target_folder, legacy_filename)

    # Skip download if file already exists on disk in any valid format
    if (os.path.exists(uhd_file_path) and os.path.getsize(uhd_file_path) > 0) or \
       (os.path.exists(hd_file_path) and os.path.getsize(hd_file_path) > 0) or \
       (os.path.exists(legacy_file_path) and os.path.getsize(legacy_file_path) > 0):
        return None

    time.sleep(0.2)

    try:
        # Attempt 1: 4K UHD Download
        img_res = requests.get(target_url, headers=headers, timeout=15, stream=True)
        if img_res.status_code == 200:
            with open(uhd_file_path, 'wb') as f:
                for chunk in img_res.iter_content(chunk_size=65536):
                    f.write(chunk)

            try:
                if os.path.getsize(uhd_file_path) > 0:
                    with Image.open(uhd_file_path) as img:
                        img.verify()

                    meta_status = inject_metadata_iptc(uhd_file_path, title, description, copyright_text)
                    meta_tag = " + Metadata EXIF/IPTC" if meta_status else ""
                    return f"[UHD Download] -> {log_path_display}{uhd_filename}{meta_tag}"
            except Exception:
                if os.path.exists(uhd_file_path):
                    os.remove(uhd_file_path)

        # Attempt 2: 1080p HD Fallback Download
        fb_res = requests.get(fallback_url, headers=headers, timeout=15, stream=True)
        if fb_res.status_code == 200:
            with open(hd_file_path, 'wb') as f:
                for chunk in fb_res.iter_content(chunk_size=65536):
                    f.write(chunk)

            try:
                if os.path.getsize(hd_file_path) > 0:
                    with Image.open(hd_file_path) as img:
                        img.verify()

                    meta_status = inject_metadata_iptc(hd_file_path, title, description, copyright_text)
                    meta_tag = " + Metadata EXIF/IPTC" if meta_status else ""
                    return f"[HD Fallback] -> {log_path_display}{hd_filename}{meta_tag}"
            except Exception:
                if os.path.exists(hd_file_path):
                    os.remove(hd_file_path)

    except Exception:
        if os.path.exists(uhd_file_path):
            os.remove(uhd_file_path)
        if os.path.exists(hd_file_path):
            os.remove(hd_file_path)

    return f"[Failed] -> {uhd_filename}"


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

            base_key = None
            try:
                if "id=OHR." in img_url:
                    raw_part = img_url.split("id=OHR.")[-1]
                    base_key = re.split(r'_[A-Za-z]{2}-[A-Za-z]{2}|_[A-Za-z]{3,4}\d', raw_part)[0].lower()
                else:
                    base_key = img_url.split("/")[-1].split("_")[0].replace(".jpg", "").lower()
            except Exception:
                base_key = date_str.replace("-", "") if date_str else "0000"

            if not base_key or len(base_key) < 3 or base_key in ["bingimage", "wallpaper", "image"]:
                base_key = f"date_{date_str.replace('-', '')}" if date_str else "date_0000"

            if base_key:
                base_key = re.sub(r'(\d{2})y$', r'20\1', base_key)
                if 'lanterfestival' in base_key:
                    base_key = base_key.replace('lanterfestival', 'lanternfestival')

            img_name = None
            if title and title.strip():
                img_name = clean_title(title)
            if not img_name and caption and caption.strip() and caption.lower() != "info":
                img_name = clean_title(caption)
            if not img_name and entry.get('name'):
                img_name = entry.get('name')

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

            if not img_name or img_name.lower() in ["bingimage", "wallpaper", "image"] or img_name.startswith("date_"):
                if title and title.strip():
                    img_name = clean_title(title)
                elif caption and caption.strip() and caption.lower() != "info":
                    img_name = clean_title(caption)

            fallback_suffix = date_str.replace('-', '') if date_str else "0000"
            if not img_name or img_name.lower() in ["bingimage", "wallpaper", "image"] or len(img_name) < 3:
                img_name = f"Wallpaper_{fallback_suffix}"

            if base_key not in unique_wallpapers:
                unique_wallpapers[base_key] = (date_str, img_name, img_url, title, description, copyright_text)
            else:
                existing_task = unique_wallpapers[base_key]
                existing_name = existing_task[1]

                is_existing_generic = existing_name.lower().startswith("wallpaper_") or existing_name.lower().startswith("bingimage_")
                is_new_better = not img_name.lower().startswith("wallpaper_") and not img_name.lower().startswith("bingimage_")

                if (is_existing_generic and is_new_better) or (short_name in ['us', 'uk'] and is_new_better):
                    unique_wallpapers[base_key] = (date_str, img_name, img_url, title, description, copyright_text)

    download_queue = list(unique_wallpapers.values())
    download_queue.sort(key=lambda x: x[0] if x[0] else "", reverse=True)

    total_tasks = len(download_queue)
    print(f"[+] Deduplication complete! {total_tasks} TRULY WORLDWIDE UNIQUE images with metadata ready.")
    print(f"[*] Multi-threading started with {MAX_WORKERS} concurrent connections...\n")

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
                os._exit(0)

    except KeyboardInterrupt:
        print("\n[X] Script execution successfully aborted.")
        os._exit(0)

    print(f"\n[ ] Outstanding! Archiving process complete 🎉\nin:\n{DOWNLOAD_DIR}")


if __name__ == "__main__":
    main()