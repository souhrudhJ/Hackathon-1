#!/bin/bash

# Script to remove commits containing exposed API keys from git history
# WARNING: This will rewrite git history and require a force push
# All collaborators will need to re-clone the repository

set -e

echo "=== Git History Cleanup Script ==="
echo "This script will remove commits containing exposed API keys"
echo ""
echo "IMPORTANT: Before running this script:"
echo "1. Revoke all exposed API keys immediately"
echo "2. Backup your repository"
echo "3. Notify all collaborators that they need to re-clone"
echo ""
read -p "Have you revoked the API keys and backed up? (yes/no): " confirm

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
# Extract the keys from an old commit to use for filtering
GEMINI_KEY=$(git show 2bf0d7b:config.py | grep "GEMINI_API_KEY = " | cut -d'"' -f2)
ROBOFLOW_KEY=$(git show 2bf0d7b:train.py | grep "api_key=" | cut -d'"' -f2)

if [ -z "$GEMINI_KEY" ] || [ -z "$ROBOFLOW_KEY" ]; then
    echo "ERROR: Could not extract keys from git history"
    echo "You may need to manually provide the keys to remove"
    exit 1
fi

echo "Found keys to remove (redacted): ${GEMINI_KEY:0:10}... and ${ROBOFLOW_KEY:0:10}..."

# Option 1: Remove specific text patterns (the API keys themselves)
echo "Step 2b: Filtering out hardcoded API keys..."
git-filter-repo --force \
  --replace-text <(echo "${GEMINI_KEY}==>***REMOVED***") \
  --replace-text <(echo "${ROBOFLOW_KEY}==>***REMOVED***")

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
