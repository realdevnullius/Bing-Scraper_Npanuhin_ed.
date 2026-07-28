# Zoek alle .jpg bestanden in alle onderliggende mappen en verplaats ze naar de huidige hoofdmap (.)
# Search all .jpg files in all sub folders and move them to the current main folder (.)
Get-ChildItem -Path . -Filter *.jpg -Recurse | Move-Item -Destination .\_OUT -Force