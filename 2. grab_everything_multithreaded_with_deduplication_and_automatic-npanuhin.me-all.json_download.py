import os
import time
import json
import sys
import re
import requests
import piexif
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

# Enable Virtual Terminal Processing on Windows for ANSI escape sequences
if sys.platform == "win32":
    os.system('')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ARCHITECTURAL PATH ROUTING STRATEGY:
# False -> Persists assets inside structured hierarchical subdirectories (e.g., _OUT\2026\07\image.jpg)
# True  -> Flattens the dependency graph and writes assets directly into root (e.g., _OUT\image.jpg)
#
# WHY / SENIOR ARCHITECT: B-Tree and inode structures in standard OS filesystems (NTFS, ext4) degrade 
# during directory traversal once a single directory exceeds ~10,000 file descriptors. B-Tree rebalancing 
# introduces noticeable I/O bottlenecks during concurrent file creation. Distributing writes across 
# depth-2 hierarchical subdirectories (YYYY/MM) caps fan-out per node, maintaining O(log N) lookup time 
# and eliminating directory lock contention at scale.
#
# HOW / JUNIOR DEV: Set to True if you want all downloaded wallpapers dropped into a single flat folder (_OUT).
# Set to False to automatically sort them into year and month folders (e.g., _OUT/2026/07/).
FLATTEN_OUTPUT = False

# WHY / SENIOR ARCHITECT: Thread-pool size chosen to optimize throughput against remote HTTP/1.1 socket 
# saturation and local thread context-switching overhead. Beyond 15-20 threads, TCP slow-start and network 
# buffer contention yield diminishing returns, while incurring higher kernel thread overhead.
# HOW / JUNIOR DEV: Controls how many image downloads happen simultaneously.
MAX_WORKERS = 15
JSON_URL = "https://bing.npanuhin.me/all.json"

LOCAL_JSON_PATH = os.path.join(SCRIPT_DIR, "all.json.latest")
DOWNLOAD_DIR = os.path.join(SCRIPT_DIR, "_OUT")

REGIONS = {
    'us': 'US-en', 'uk': 'GB-en', 'de': 'DE-de', 'fr': 'FR-fr',
    'ja': 'JP-ja', 'au': 'AU-en', 'cn': 'CN-zh', 'ca': 'CA-en',
    'in': 'IN-en', 'br': 'BR-pt', 'row': 'ROW-en'
}

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# WHY / SENIOR ARCHITECT: Modern HTTP Edge Gateways and CDNs enforce strict User-Agent inspection 
# rules to eliminate generic crawler bots. Providing a deterministic desktop browser header bypasses 
# 403 Forbidden edge drop policies without adding full browser automation overhead.
# HOW / JUNIOR DEV: Headers sent with every HTTP request so Bing's server thinks we are a standard browser.
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}


class PipelineMonitor:
    """
    Thread-safe aggregated pipeline metrics tracker and dynamic terminal dashboard printer.
    Aggregates results across all concurrent workers into a single live console display.
    """
    def __init__(self, total_tasks):
        self.lock = threading.Lock()
        self.total_tasks = total_tasks
        self.processed = 0
        self.skipped = 0
        self.uhd_downloads = 0
        self.hd_downloads = 0
        self.failed = 0
        self.total_bytes = 0
        self.start_time = time.time()
        self.recent_transfers = []  # List of (timestamp, bytes_downloaded)
        self.rendered_lines = 0

    def record_result(self, status_type, bytes_count=0):
        with self.lock:
            now = time.time()
            self.processed += 1
            if status_type == "SKIPPED":
                self.skipped += 1
            elif status_type == "UHD":
                self.uhd_downloads += 1
                self.total_bytes += bytes_count
                self.recent_transfers.append((now, bytes_count))
            elif status_type == "HD":
                self.hd_downloads += 1
                self.total_bytes += bytes_count
                self.recent_transfers.append((now, bytes_count))
            elif status_type == "FAILED":
                self.failed += 1

            # Keep rolling window of last 10 seconds for transfer speed calculation
            cutoff = now - 10.0
            self.recent_transfers = [t for t in self.recent_transfers if t[0] >= cutoff]

            self.render_dashboard()

    def render_dashboard(self):
        elapsed = time.time() - self.start_time
        downloaded_count = self.uhd_downloads + self.hd_downloads
        
        # Progress Bar calculation
        percentage = (self.processed / self.total_tasks * 100) if self.total_tasks > 0 else 100.0
        bar_length = 20
        filled_len = int(bar_length * self.processed // self.total_tasks) if self.total_tasks > 0 else bar_length
        bar = "=" * filled_len + (">" if filled_len < bar_length else "")
        bar = bar.ljust(bar_length)

        # ETA calculation
        items_remaining = self.total_tasks - self.processed
        rate = self.processed / elapsed if elapsed > 0 else 0
        eta_seconds = int(items_remaining / rate) if rate > 0 else 0
        eta_str = time.strftime("%H:%M:%S", time.gmtime(eta_seconds))
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(int(elapsed)))

        # Network speed calculation (rolling 10s window)
        window_time = min(elapsed, 10.0)
        recent_bytes = sum(b for t, b in self.recent_transfers)
        recent_count = len(self.recent_transfers)
        speed_mbps = (recent_bytes / (1024 * 1024)) / window_time if window_time > 0 else 0.0
        speed_imgs = recent_count / window_time if window_time > 0 else 0.0

        # Payload Metrics
        total_mb = self.total_bytes / (1024 * 1024)
        avg_mb = (total_mb / downloaded_count) if downloaded_count > 0 else 0.0

        lines = [
            f"[*] PROGRESS: [{bar}] {percentage:5.1f}% | {self.processed:,}/{self.total_tasks:,} items | ETA: {eta_str}",
            "+------------------------------------------------------------------+",
            "| REAL-TIME PIPELINE EXECUTION MONITOR                             |",
            "+------------------------------------------------------------------+",
            f"| Total Unique Items Processed : {self.processed:<35,}|",
            f"| Already Up-to-Date (Skipped) : {self.skipped:<35,}|",
            f"| New Wallpapers Downloaded    : {downloaded_count:<35,}|",
            f"|   ├── New UHD (4K) Quality   : {self.uhd_downloads:<35,}|",
            f"|   └── New HD Quality         : {self.hd_downloads:<35,}|",
            f"| Failed / Unavailable Assets  : {self.failed:<35,}|",
            f"| Total Payload Downloaded     : {total_mb:<32.2f} MB |",
            f"| Average Image Payload Size   : {avg_mb:<32.2f} MB |",
            f"| Current Network Speed        : {speed_mbps:<5.2f} MB/s ({speed_imgs:<2.0f} img/s)".ljust(67) + "|",
            f"| Total Pipeline Execution Time: {elapsed_str:<35}|",
            "+------------------------------------------------------------------+"
        ]

        # Rewind cursor to overwrite previous dashboard frame
        if self.rendered_lines > 0:
            sys.stdout.write(f"\033[{self.rendered_lines}F")

        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
        self.rendered_lines = len(lines)


def print_ascii_banner():
    banner = """
================================================================================
 ____  _               ____  
|  _ \| | _ __   __ _ / ___|  ___ _ __ __ _ _ __   ___ _ __ 
| |_) | | '_ \ / _` \___ \ / __| '__/ _` | '_ \ / _ \ '__|
|  _ <| | | | | (_| |___) | (__| | | (_| | |_) |  __/ |   
|____/|_|_| |_|\__, |____/ \___|_|  \__,_| .__/ \___|_|   
               |___/                     |_|              
               (Npanuhin Edition)
================================================================================"""
    print(banner)


def sync_central_database():
    """
    Synchronizes local JSON state with upstream endpoint using an HTTP Time-To-Live (TTL) cache strategy.
    
    WHY / SENIOR ARCHITECT: Eliminates redundant WAN bandwidth utilization and protects upstream CDNs from 
    thundering herd requests. Evaluates file modification timestamp (`mtime`) on disk prior to network 
    handshake to preserve zero-IO network roundtrips. Implements graceful local cache degradation on 
    upstream transport failure.
    
    HOW / JUNIOR DEV: Checks if 'all.json.latest' exists and is under 5 hours old. If so, reuses it.
    If older or missing, downloads fresh data. If offline, falls back to local cache safely.
    """
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
    """
    Direct binary EXIF header modification via low-level byte serialization.
    
    WHY / SENIOR ARCHITECT: Preserves digital provenance across media asset pipelines. Modifies 0th IFD 
    tags in-place without re-encoding binary JPEG frame data (preventing generation loss and saving CPU cycles).
    Encodes UTF-16LE specifically for Windows Shell/NTFS indexing metadata tags (0x9C9B, 0x9C9C) while maintaining 
    standard UTF-8 byte arrays for cross-platform EXIF 2.2 tags (0x010E, 0x8298).
    
    HOW / JUNIOR DEV: Writes Title, Description, and Copyright info directly inside the JPEG image file 
    properties using EXIF tags so Windows, Mac, and photo managers display the metadata.
    """
    try:
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "Interop": {}, "1st": {}, "thumbnail": None}

        # Tag 0x9C9B: XPTitle (Windows UTF-16LE), Tag 0x010E: ImageDescription (Standard EXIF UTF-8)
        if title:
            exif_dict["0th"][0x9c9b] = title.encode('utf-16le')
            exif_dict["0th"][0x010e] = title.encode('utf-8')

        # Tag 0x9C9C: XPComment / Description (Windows UTF-16LE)
        if description:
            exif_dict["0th"][0x9c9c] = description.encode('utf-16le')

        # Tag 0x8298: Copyright notice (Standard EXIF ASCII/UTF-8)
        if copyright_text:
            exif_dict["0th"][0x8298] = copyright_text.encode('utf-8')

        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, file_path)
        return True
    except Exception as e:
        print(f" [Warning] Shell metadata injection vector failed: {e}")
        return False


def clean_title(title_str):
    """
    Sanitizes string inputs to comply with strict OS path constraints and ASCII/Unicode file system APIs.
    
    WHY / SENIOR ARCHITECT: Prevents path traversal vulnerabilities and invalid file descriptor creation across 
    POSIX and Win32 subsystems by scrubbing reserved characters (`\ / : * ? " < > |`). Implements 
    linguistic filtering to reduce token noise in long names, enforcing a strict 60-character ceiling to prevent 
    exceeding legacy Win32 `MAX_PATH` (260 char) buffer limitations when nested deep in dynamic subdirectories.
    
    HOW / JUNIOR DEV: Strip out invalid file characters, remove clutter words like 'the' or 'in', 
    capitalize words, and truncate to a max length of 60 characters for a clean file name.
    """
    if not title_str:
        return "BingImage"

    stop_words = {
        'the', 'in', 'on', 'at', 'of', 'and', 'a', 'an', 'to', 'for', 'with', 'off',
        'from', 'by', 'as', 'between', 'among', 'into', 'over', 'through', 'about',
        'under', 'above', 'during', 'without', 'against', 'including', 'across'
    }

    # Scrub control chars, OS reserved path symbols, and CJK punctuation
    clean = re.sub(r'[\x00-\x1f\\/:*?"<>|,\. !?’’“” ]|，|。|！|＿|：', ' ', title_str)
    words = clean.split()
    filtered_words = [w.capitalize() if w.isascii() else w for w in words if w.lower() not in stop_words]

    if not filtered_words:
        return "BingImage"

    raw_cleaned = " ".join(filtered_words)
    return raw_cleaned[:60].rstrip(' ') if len(raw_cleaned) > 60 else raw_cleaned


def load_local_json(path):
    """
    Reads JSON file with automatic recovery for truncated write operations.
    
    WHY / SENIOR ARCHITECT: Robust failure recovery for file I/O interruptions (e.g., process termination 
    mid-write). If JSON termination tokens (`}` or `]`) were missing due to an unbuffered stream crash, 
    it dynamically appends closing tags to preserve parsing without throwing fatal unhandled exceptions.
    
    HOW / JUNIOR DEV: Opens and parses 'all.json.latest'. If the file was corrupted or cut short mid-write, 
    it attempts to repair the trailing JSON syntax automatically before failing.
    """
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read().strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Self-healing syntax patch for truncated streams
        if not content.endswith('}'):
            content += '}' if content.endswith(']') else ']}'
        try:
            return json.loads(content)
        except Exception:
            return None


def extract_ms_code(url, default_quality="HD"):
    """
    Extracts Microsoft Bing market codes and unique asset IDs from asset URIs.
    
    WHY / SENIOR ARCHITECT: Parses Bing's internal URL schema to derive a canonical asset fingerprint. 
    Decouples raw dimensional resolution markers (e.g., `1920x1080`) from asset names, mapping them strictly 
    to high-level semantic tags (`UHD` vs `HD`) while preserving market specificity (`EN-US`, `DE-DE`, etc.).
    
    HOW / JUNIOR DEV: Reads the URL to pull out regional market codes (like EN-US or DE-DE) and tags the name 
    with 'UHD' or 'HD', removing resolution numbers like 1920x1080 from the filename.
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
    """
    Atomic execution unit for concurrent image acquisition, validation, and metadata processing.
    
    WHY / SENIOR ARCHITECT: 
    1. Zero-Lock Idempotency Check: Proactively checks local disk paths for existing payloads (UHD, HD, legacy) 
       *prior* to initiating network sockets, preserving I/O bandwidth.
    2. Streamed Memory Buffer: Uses chunked streaming writes (`64KB` buffer) to keep process RAM flat, 
       preventing memory spikes regardless of image file size.
    3. Defensive Verification: Employs `PIL.Image.verify()` to validate structural byte integrity (detecting 
       partial TCP drops or HTTP 200 HTML error pages masquerading as JPEGs). Corrupted payloads are 
       purged immediately.
    4. Two-Tier Tiered Resolution Fallback: Tries 4K UHD endpoint first; falls back to 1080p HD if 4K fails.
    
    HOW / JUNIOR DEV: Takes a download task, determines the folder path, checks if we already downloaded 
    it, fetches the 4K version (or falls back to HD), verifies the file isn't broken, injects EXIF metadata, 
    and returns a status structure for dashboard aggregation.
    """
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
        return ("SKIPPED", 0)

    # Minor rate-limit buffer to prevent edge throttling
    time.sleep(0.2)

    try:
        # Attempt 1: 4K UHD Download
        img_res = requests.get(target_url, headers=headers, timeout=15, stream=True)
        if img_res.status_code == 200:
            with open(uhd_file_path, 'wb') as f:
                for chunk in img_res.iter_content(chunk_size=65536):
                    f.write(chunk)

            try:
                file_size = os.path.getsize(uhd_file_path)
                if file_size > 0:
                    with Image.open(uhd_file_path) as img:
                        img.verify()

                    inject_metadata_iptc(uhd_file_path, title, description, copyright_text)
                    return ("UHD", file_size)
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
                file_size = os.path.getsize(hd_file_path)
                if file_size > 0:
                    with Image.open(hd_file_path) as img:
                        img.verify()

                    inject_metadata_iptc(hd_file_path, title, description, copyright_text)
                    return ("HD", file_size)
            except Exception:
                if os.path.exists(hd_file_path):
                    os.remove(hd_file_path)

    except Exception:
        if os.path.exists(uhd_file_path):
            os.remove(uhd_file_path)
        if os.path.exists(hd_file_path):
            os.remove(hd_file_path)

    return ("FAILED", 0)


def main():
    """
    Primary Application Lifecycle Controller.
    
    WHY / SENIOR ARCHITECT:
    1. Cross-Regional Ingestion & Merging: Aggregates localized metadata structures across 11 global regions 
       into a unified memory graph.
    2. Key Normalization & Collision Resolution: Normalizes string keys (`base_key`) to eliminate regional 
       duplication of identical assets. When collisions occur, prioritizes records containing descriptive 
       metadata over generic placeholders (`Wallpaper_...`), while preferring `US`/`UK` locale strings for naming.
    3. Non-Blocking SIGINT Signal Trap: Wraps execution in explicit `KeyboardInterrupt` blocks that force an 
       immediate, clean process exit via `os._exit(0)`, immediately terminating orphan worker threads without 
       waiting for active socket timeouts.
    
    HOW / JUNIOR DEV: Triggers database sync, loops through all 11 world regions in the JSON file, removes 
    duplicate images, generates clean filenames, sorts tasks chronologically, and executes parallel downloads 
    across 15 threads with real-time dynamic dashboard display.
    """
    print_ascii_banner()
    print("[*] Initialising Bing Wallpaper Synchroniser (Schema Engine)\n")

    sync_central_database()
    print("-" * 60)

    print(f"[*] Reading local JSON database: {LOCAL_JSON_PATH}")
    if not os.path.exists(LOCAL_JSON_PATH):
        print(f"[!] CRITICAL ERROR: all.json.latest is missing!")
        return

    db = load_local_json(LOCAL_JSON_PATH)
    if not db:
        print(f"[!] CRITICAL ERROR: Could not parse all.json.latest!")
        return

    total_entries = sum(len(entries) for entries in db.values() if isinstance(entries, list))
    print(f"[+] Successfully loaded {total_entries} entries from database schema.")

    unique_wallpapers = {}

    # Aggregation Loop: Iterates over geographical region definitions
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

            # Extract canonical base key for cross-region deduplication
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

            # Synthesize descriptive title from available record fields
            img_name = None
            if title and title.strip():
                img_name = clean_title(title)
            if not img_name and caption and caption.strip() and caption.lower() != "info":
                img_name = clean_title(caption)
            if not img_name and entry.get('name'):
                img_name = entry.get('name')

            # Fallback title parser: Splits camelCase or concatenated key strings into human-readable titles
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

            # Priority Deduplication Arbitrator
            if base_key not in unique_wallpapers:
                unique_wallpapers[base_key] = (date_str, img_name, img_url, title, description, copyright_text)
            else:
                existing_task = unique_wallpapers[base_key]
                existing_name = existing_task[1]

                is_existing_generic = existing_name.lower().startswith("wallpaper_") or existing_name.lower().startswith("bingimage_")
                is_new_better = not img_name.lower().startswith("wallpaper_") and not img_name.lower().startswith("bingimage_")

                if (is_existing_generic and is_new_better) or (short_name in ['us', 'uk'] and is_new_better):
                    unique_wallpapers[base_key] = (date_str, img_name, img_url, title, description, copyright_text)

    # Sort queue descending by date (process latest wallpapers first)
    download_queue = list(unique_wallpapers.values())
    download_queue.sort(key=lambda x: x[0] if x[0] else "", reverse=True)

    total_tasks = len(download_queue)
    print(f"[+] Cross-date Latin-preferred deduplication complete: {total_tasks} unique download tasks queued.")
    print(f"[*] ThreadPoolExecutor active ({MAX_WORKERS} parallel workers)... (Press Ctrl+C to interrupt)\n")

    monitor = PipelineMonitor(total_tasks)

    # Thread Pool Concurrency Engine
    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(download_single_wallpaper, task): task for task in download_queue}

            try:
                for future in as_completed(futures):
                    status_type, bytes_count = future.result()
                    monitor.record_result(status_type, bytes_count)
            except KeyboardInterrupt:
                print("\n[!] Ctrl+C detected! Emptying multi-threaded task queue...")
                executor.shutdown(wait=False, cancel_futures=True)
                os._exit(0)

    except KeyboardInterrupt:
        print("\n[X] Script execution successfully aborted.")
        os._exit(0)

    print(f"\n\n[ ] Outstanding! Archiving process complete 🎉\nin:\n{DOWNLOAD_DIR}")


if __name__ == "__main__":
    main()