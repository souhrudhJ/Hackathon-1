#!/bin/bash

# Script to remove commits containing exposed API keys from git history
# WARNING: This will rewrite git history and require a force push
# All collaborators will need to re-clone the repository
#
# PREREQUISITES:
# - This script must be run from the repository root directory
# - Commit 2bf0d7b must exist with the original exposed keys
# - git-filter-repo must be available (script will install if needed)
#
# USAGE: ./cleanup_history.sh

set -e

echo "=== Git History Cleanup Script ==="
echo "This script will remove commits containing exposed API keys"
echo ""
echo "IMPORTANT: Before running this script:"
echo "1. Revoke all exposed API keys immediately"
echo "2. Backup your repository"
echo "3. Notify all collaborators that they need to re-clone"
echo ""
read -p "Have you revoked the API keys and backed up? Type 'yes' to continue: " confirm

if [ "$confirm" != "yes" ]; then
    echo "Aborting. Please revoke keys first."
    exit 1
fi

# Check if git-filter-repo is installed
if ! command -v git-filter-repo &> /dev/null; then
    echo "Installing git-filter-repo..."
    pip install git-filter-repo
fi

echo ""
echo "Step 1: Creating a fresh clone for filtering..."
# Capture current directory before moving
CURRENT_DIR="$PWD"
REPO_NAME=$(basename "$CURRENT_DIR")
PARENT_DIR=$(dirname "$CURRENT_DIR")
CLEAN_DIR="${PARENT_DIR}/${REPO_NAME}_cleaned"

if [ -d "$CLEAN_DIR" ]; then
    echo "Removing existing clean directory..."
    rm -rf "$CLEAN_DIR"
fi

git clone "file://${CURRENT_DIR}" "$CLEAN_DIR"
cd "$CLEAN_DIR"

echo ""
echo "Step 2: Removing commits before the security fix..."
# The commit c750ae7 removed the keys, so we want to keep from there forward
# We'll create a new root at the merge commit 727781c

echo "Step 2a: Extracting the exposed keys from git history..."
# Verify the commit exists first
if ! git cat-file -e 2bf0d7b^{commit} 2>/dev/null; then
    echo "ERROR: Commit 2bf0d7b not found in repository history"
    echo "This script requires the full git history. Run 'git fetch --unshallow' if needed."
    exit 1
fi

# Extract the keys from an old commit to use for filtering
# Try both double and single quote patterns for robustness
GEMINI_KEY=$(git show 2bf0d7b:config.py 2>/dev/null | grep -E 'GEMINI_API_KEY\s*=\s*["\']' | sed -E 's/.*["\']([^"'\'']+)["\'].*/\1/' || echo "")
ROBOFLOW_KEY=$(git show 2bf0d7b:train.py 2>/dev/null | grep -E 'api_key\s*=\s*["\']' | sed -E 's/.*["\']([^"'\'']+)["\'].*/\1/' || echo "")

if [ -z "$GEMINI_KEY" ] || [ -z "$ROBOFLOW_KEY" ]; then
    echo "ERROR: Could not extract keys from git history"
    echo "Expected to find keys in commit 2bf0d7b in files config.py and train.py"
    echo "You may need to manually identify the commit with exposed keys"
    exit 1
fi

# Validate that keys look reasonable (not empty, have minimum length)
if [ ${#GEMINI_KEY} -lt 20 ] || [ ${#ROBOFLOW_KEY} -lt 10 ]; then
    echo "ERROR: Extracted keys appear invalid (too short)"
    echo "GEMINI_KEY length: ${#GEMINI_KEY}, ROBOFLOW_KEY length: ${#ROBOFLOW_KEY}"
    exit 1
fi

# Validate keys contain only expected characters (alphanumeric, dashes, underscores)
# API keys typically don't contain quotes, spaces, or other special characters
if ! echo "$GEMINI_KEY" | grep -qE '^[A-Za-z0-9_-]+$'; then
    echo "WARNING: GEMINI_KEY contains unexpected characters, may indicate extraction error"
fi
if ! echo "$ROBOFLOW_KEY" | grep -qE '^[A-Za-z0-9_-]+$'; then
    echo "WARNING: ROBOFLOW_KEY contains unexpected characters, may indicate extraction error"
fi

echo "Successfully extracted 2 API keys from git history for removal"

# Option 1: Remove specific text patterns (the API keys themselves)
echo "Step 2b: Filtering out hardcoded API keys..."
# Double-check keys are not empty before filtering (defense in depth)
if [ -n "$GEMINI_KEY" ] && [ -n "$ROBOFLOW_KEY" ]; then
    git-filter-repo --force \
      --replace-text <(echo "${GEMINI_KEY}==>***REMOVED***") \
      --replace-text <(echo "${ROBOFLOW_KEY}==>***REMOVED***")
else
    echo "ERROR: Keys became empty before filtering step"
    exit 1
fi

# Option 2: Alternative - Start fresh from the merge commit
# Uncomment these lines if you want to create a completely new history
# git checkout 727781c
# git checkout -b main-clean
# git branch -D main
# git branch -m main

echo ""
echo "Step 3: Cleaning up refs and gc..."
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo ""
echo "Step 4: Preparing to push..."
# Get the original repository URL
REPO_URL=$(git -C "${CURRENT_DIR}" remote get-url origin)
echo "Original repository URL: $REPO_URL"
echo ""
echo "To complete the cleanup, run these commands manually:"
echo ""
echo "cd $CLEAN_DIR"
echo "git remote set-url origin $REPO_URL"
echo "git push --force --all"
echo "git push --force --tags"
echo ""
echo "Then delete the old repository directory and rename this one:"
echo "cd $PARENT_DIR"
echo "rm -rf $REPO_NAME"
echo "mv ${REPO_NAME}_cleaned $REPO_NAME"
echo ""
echo "=== IMPORTANT POST-CLEANUP STEPS ==="
echo "1. Verify the keys are gone: git log -p --all | grep -i 'AIzaSy' || echo 'Keys removed'"
echo "2. Delete branches with old references on GitHub:"
echo "   - copilot/remove-exposed-keys-and-folders"
echo "   - copilot/delete-commits-and-branch"
echo "3. Contact GitHub support to purge cached commits: https://support.github.com/"
echo "4. All collaborators must re-clone the repository"
echo ""
