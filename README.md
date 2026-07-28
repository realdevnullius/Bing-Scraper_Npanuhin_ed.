\# Bing Wallpaper Archive Pipeline



A production-grade, cross-region deduplicating downloader pipeline for the global Bing Image of the Day archive. This pipeline aggregates manifests across multiple worldwide endpoints, enforces strict asset binary integrity checks, and injects explorer-readable shell metadata directly into the image files.



Optimized specifically for seamless integration with advanced third-party wallpaper rotators such as \*\*John's Background Switcher\*\*.



\## 🚀 Key Architectural Features



\*   \*\*Worldwide Cross-Region Deduplication:\*\* Evaluates shifting regional markets (`US`, `CN`, `JP`, `DE`, etc.) in memory via a unified tracking index, ensuring identical assets are downloaded exactly once.

\*   \*\*Unicode Script Preservation Strategy:\*\* Gives absolute priority to descriptive English titles while actively preserving rich native script titles (Chinese, Japanese, etc.) as premium fallback filenames instead of assigning generic string signatures.

\*   \*\*Automatic 4K Resolution Upgrading:\*\* Automatically rewrites standard high-definition asset manifests into Ultra HD (`UHD`) resolution endpoints before initializing transactions.

\*   \*\*Fault-Tolerant Dynamic Fallbacks:\*\* Automatically activates an asynchronous standard high-definition recovery routine if the target UHD asset is truncated, missing, or drops packets during download.

\*   \*\*Win32 Shell Explorer Metadata Injection:\*\* Hard-injects clean custom `EXIF/IPTC` metadata blocks directly into target JPEGs using strict UTF-16LE Byte Order Mark configurations for seamless native Windows desktop shell properties parsing.

\*   \*\*Flexible Structural Routing Toggle:\*\* Employs a `FLATTEN\_OUTPUT` switcher configuration. Set to `True` to store all structural imagery flat inside a single root workspace folder (highly recommended for John's Background Switcher, which does not recurse subdirectories).



\## 📁 Directory Structure Alignment



The pipeline expects and maintains the following clean workspace directory taxonomy:



```text

📁 C:\_BingBackgrounds.py\\anerg.com.py\

│

├── 📄 1. grab_everything_singlethreaded_with_deduplication_and_automatic-npanuhin.me-all.json_download.py

├── 📄 2. grab_everything_multithreaded_with_deduplication_and_automatic-npanuhin.me-all.json_download.py

├── 📄 download_npanuhin.me-all.json.py (optional: use when you only want to download all.json)

├── 📄 test_unicode.py (optional: do a quick test if path + file length is too large and how it handles Asian characters)

├── 📄 run.cmd (One-Click Launcher) (optional: installs dependencies then starts downloading with multithread)

├── 📄 flatten_out-folder.ps1 (optional: move all .\_OUT\YYYY\MM\*.jpg files to .\_OUT\*.jpg)

├── 📄 requirements.txt (Dependencies)

├── 📄 all.json.latest (Auto-Generated Cache Manifest)

│

└── 📁 \_OUT\ (Target Download Assets Repository Workspace)

```



\## 🛠️ Quick Start Configuration



1\. Clone or download this repository into your target installation folder (e.g., `C:\_BingBackgrounds.py\anerg.com.py\`).

2\. Edit \*\*`1. grab_everything_singlethreaded_with_deduplication_and_automatic-npanuhin.me-all.json_download.py`\*\* and \*\*`2. grab_everything_multithreaded_with_deduplication_and_automatic-npanuhin.me-all.json_download.py files`\*\*.

3\. Double-click \*\*`run.cmd`\*\*. This automated batch layer will instantly verify your Python environment, install required library dependencies (`requests`, `piexif`, `Pillow`), correct working directory scopes, and launch the multi-threaded connection worker pool.

4\. Once completed, your `\_OUT` directory will be fully synchronized with metadata-enriched 4K wallpaper assets (when they were available - e.g., 2010 had no 4k!).

5\. Instead of the \*\*`run.cmd`\*\*, you can also run the two .py scripts from (2) directly.  Use: python.exe '.\1. grab_everything_singlethreaded_with_deduplication_and_automatic-npanuhin.me-all.json_download.py'


\## 📄 License



This project is licensed under the terms chosen within the repository file structure.



\## PEACE! By order of Devnullius.



