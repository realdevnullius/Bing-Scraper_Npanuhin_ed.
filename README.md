# 🖼️ Bing Wallpaper Archive Pipeline

A robust, cross-region deduplicating downloader pipeline for the global **Bing Image of the Day**
archive. Available in both **Single-Threaded (Sequential)** and **Multi-Threaded (Concurrent)** 
editions.

This pipeline syncs manifests across 11 worldwide regional endpoints, performs in-memory
deduplication, enforces Ultra HD (4K) image quality, verifies binary payload integrity, and
hard-injects Windows Shell-compatible EXIF/IPTC metadata into every asset.

---

## 📸 Key Features

* **🌍 Worldwide Cross-Region Deduplication:** Evaluates regional Bing markets (`US`, `UK`, `DE`,
`FR`, `JA`, `AU`, `CN`, `CA`, `IN`, `BR`, `ROW`) in RAM to ensure duplicate global images are
downloaded exactly once.
* **⚡ Dual Execution Engines:**
* **Multi-Threaded Engine:** Uses `ThreadPoolExecutor` TCP multiplexing for speed (5x–15x
throughput gains).
* **Single-Threaded Engine:** Strict sequential ingestion for connection stability on low-bandwidth
networks or strict firewalls.
* **🎯 Unicode & CJK Script Preservation:** Prevents descriptive international filenames (Chinese,
Japanese, Korean, German, etc.) from being overwritten with generic fallback strings.
* **✨ Automatic 4K Ultra HD Upgrading:** Dynamically rewrites standard high-definition asset URLs 
to target Ultra HD (`_UHD.jpg`) streams on Bing's CDNs.
* **🏷️ Windows Explorer Metadata Injection:** Directly writes native `EXIF/IPTC` metadata tags using
UTF-16LE Byte Order Mark (BOM) encoding. Windows Explorer reads image titles, descriptions, and
copyrights natively in File Explorer properties.
* **🔄 Flexible Directory Architecture:** Supports both structured `_OUT\YYYY\MM\filename.jpg` output
and flat `_OUT\filename.jpg` storage via a simple global toggle.
* **🖼️ Background Switcher Ready:** Optimized for seamless integration with desktop wallpaper 
rotation software, such as *John's Background Switcher*.

---

## 🏎️ Pipeline Comparison: Single-Threaded vs. Multi-Threaded

| Feature / Dimension | Single-Threaded Edition | Multi-Threaded Edition |
| --- | --- | --- |
| **Execution Vector** | Sequential (1 asset at a time) | Concurrent (`ThreadPoolExecutor`) |
| **Speed / Throughput** | Standard Network Throughput | ~max. 6x Speedup |
| **Default Concurrency** | `1 worker` | `6 workers` (Hard Limit: Max 6) |
| **Graceful Shutdown** | Standard `Ctrl+C` interrupt | Signal intercept + `executor.shutdown()` |
| **Best Used For** | Metered links, strict VPNs/proxies | Bulk archiving, high-speed initial runs |

---

## 🏁 Quick Start (For Beginners)

### 1. Requirements

* Windows 10 or Windows 11
* Python 3.8 or higher installed on your system

### 2. Setup & Execution

1. Download or clone this repository to your computer (e.g., `C:\_BingBackgrounds.py\anerg.com.py\`).
2. Double-click **`run.cmd`**.

> **What `run.cmd` does automatically:**
> * Checks your Python installation.
> * Installs missing Python libraries (`requests`, `piexif`, `Pillow`).
> * Synchronizes the central Bing manifest database (`all.json.latest`).
> * Downloads and metadata-enriches all available wallpapers into the `_OUT` directory.

---

## 💻 Manual / Advanced Usage (For Power Users)

If you prefer running the script manually from PowerShell or Command Prompt:

```powershell
# 1. Install required dependencies
pip install requests piexif Pillow

# 2. Run the Multi-Threaded Edition (Fastest)
python '.\2. grab_everything_multithreaded_with_deduplication_and_automatic-npanuhin.me-all.json_download.py'

# 3. OR Run the Single-Threaded Edition (Sequential / Safe Mode)
python '.\1. grab_everything_singlethreaded_with_deduplication_and_automatic-npanuhin.me-all.json_download.py'
```

---

## ⚙️ Configuration & Tuning Options

Open either `.py` script in any code editor to adjust global runtime parameters:

```python
# SCRIPT_DIR: Workspace installation target root
SCRIPT_DIR = r"C:\_BingBackgrounds.py\anerg.com.py"

# FLATTEN_OUTPUT Routing Toggle:
# False -> Saves assets inside structured subdirectories: _OUT\YYYY\MM\filename.jpg
# True  -> Flattens folder output directly into root:     _OUT\filename.jpg
# (Set to True for legacy wallpaper rotators that cannot recurse subdirectories)
FLATTEN_OUTPUT = False

# MAX_WORKERS (default = 6) (Multi-Threaded Script Only):
# ------------------------------------------------------------------
# NOTE: Going above 6 workers triggers HTTP 429 rate-limiting / CDN socket blocks.
# Safe    (2 - 5 workers): Minimal I/O footprint for metered links or shared VPNs.
# Default (6 workers)    : Recommended hard maximum for Bing edge CDN sockets.
MAX_WORKERS = 6
```

---

## 📁 Repository Directory Taxonomy

```text
📁 C:\_BingBackgrounds.py\anerg.com.py\
│
├── 📄 1. grab_everything_singlethreaded_with_deduplication_and_automatic-npanuhin.me-all.json_download.py
├── 📄 2. grab_everything_multithreaded_with_deduplication_and_automatic-npanuhin.me-all.json_download.py
├── 📄 run.cmd                    <-- One-Click Launcher script
├── 📄 requirements.txt           <-- Python dependencies list
├── 📄 all.json.latest            <-- Auto-generated/cached Bing database manifest
│
└── 📁 _OUT\                      <-- Download workspace output target
    ├── 📁 2026\
    │   └── 📁 07\
    │       └── 📄 20260727_ExampleTitle (EN-US6345786269_UHD).jpg
    └── ...
```

---

## 🔬 Architectural Mechanics & Fallback Flow

```text
[ Remote JSON Manifest ] ---> [ In-Memory RAM Deduplication ]
                                        │
                                        ▼
                           [ Concurrency ThreadPool ]
                                        │
                           [ Resolve 4K UHD Target URL ]
                                        │
                         ┌──────────────┴──────────────┐
                         ▼                             ▼
                 [ HTTP 200 Stream ]           [ Request Error / 404 ]
                         │                             │
                         ▼                             ▼
                 [ Pillow Verification ]      [ 1080p HD Fallback Route ]
                         │                             │
                         └──────────────┬──────────────┘
                                        ▼
                        [ Inject EXIF/IPTC Metadata ]
                                        ▼
                       [ Save Asset to _OUT Workspace ]
```

* **Manifest Ingestion:** Syncs the central database archive from [bing.npanuhin.me/all.json](https://bing.npanuhin.me/all.json).
* **Deterministic Deduplication:** Extracts Microsoft inner archival keys (`OHR.Codename`) across 11
 regional markets to prevent duplicate downloads while protecting non-Latin CJK title strings.
* **Quality Upgrading:** Intercepts standard resolution strings and modifies the stream parameters to
 pull 4K UHD renditions (`&rf=LaDigue_UHD.jpg`).
* **Binary Integrity Check:** Streamed bytes pass through PIL/Pillow (`Image.verify()`) to ensure no
 truncated or damaged JPEGs are written to disk.
* **EXIF/IPTC Enrichment:** Injects metadata directly into JPEG APP1 headers (`0x9c9b XPTitle`, 
`0x010e ImageDescription`, `0x8298 Copyright`).

---

## 📄 License & Credits

* **Data Archive Source:** Remote Bing Image manifest provided via [npanuhin/bing-wallpaper](https://github.com/npanuhin/bing-wallpaper).
* **Author / Maintainer:** Devnullius *(Devvie Nuis - the Realdevnullius)*.

```