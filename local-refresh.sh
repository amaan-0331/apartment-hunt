#!/bin/bash
# Scrape Property Finder from this Mac and push the new data to GitHub.
# The push triggers the GitHub workflow, which republishes the Pages site.
# Property Finder blocks GitHub's servers, so the scrape has to run here.
set -euo pipefail
cd "$(dirname "$0")"

echo "=== $(date) ==="
git pull --rebase --autostash
python3 hunt.py --refresh            # Google key comes from google_key.txt
git add listings.json commute_cache.json
if git diff --cached --quiet; then
  echo "No changes."
else
  git commit -m "Refresh listings"
  git push
fi
