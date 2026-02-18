# Security Incident Report - Exposed API Keys

## Incident Summary
API keys and personal folder paths were accidentally committed to the repository and are visible in git history.

## Commits Affected
The following commits (and earlier) contained exposed sensitive data:
- All commits before `c750ae7807b09cd951ba6edbdcf55deef7a6607a` (Feb 18, 2026)
- Specifically commits: `2bf0d7b`, `9d40cfa`, `4b82570`, `686486397`, `870635bd`, `e573a582`, `0fa0a07c`, and earlier

## Exposed Information
The following API keys were hardcoded in commits before `c750ae7`:
- `config.py` - Gemini API Key: `AIzaSy***...eH50lhU` (full key visible in git history)
- `train.py` - Roboflow API Key: `XdP8NQ***...kMBxTP0r` (full key visible in git history)
- `train_colab.ipynb` - API keys (likely same as above)
- `README.md` - Personal folder paths

**CRITICAL**: These keys are visible in ALL commits from `605986e` through `2bf0d7b` (10 commits total)

## Immediate Actions Required

### 1. REVOKE ALL EXPOSED API KEYS (CRITICAL - DO THIS FIRST)
- **Gemini API Key**: Revoke at https://aistudio.google.com/apikey
- **Roboflow API Key**: Revoke at https://app.roboflow.com/settings/api
- Generate new keys and set them as environment variables only

### 2. Remove Commits from GitHub

⚠️ **CRITICAL LIMITATION**: Due to security constraints in this environment, force-push operations are not allowed. The git history cleanup MUST be performed by the repository owner locally.

#### Required Manual Steps (Repository Owner Only):

**Step A: Use the provided cleanup script**
```bash
chmod +x cleanup_history.sh
./cleanup_history.sh
```

**Step B: Or manually rewrite history**
```bash
# 1. Clone a fresh copy for filtering
git clone https://github.com/souhrudhJ/Hackathon-1 Hackathon-1-clean
cd Hackathon-1-clean

# 2. Install git-filter-repo
pip install git-filter-repo

# 3. Extract the keys from git history and remove them
# First, extract the exposed keys from an old commit
GEMINI_KEY=$(git show 2bf0d7b:config.py | grep "GEMINI_API_KEY = " | cut -d'"' -f2)
ROBOFLOW_KEY=$(git show 2bf0d7b:train.py | grep "api_key=" | cut -d'"' -f2)

# Now filter them out using git-filter-repo
git-filter-repo --force \
  --replace-text <(cat <<EOF
${GEMINI_KEY}==>***REMOVED***
${ROBOFLOW_KEY}==>***REMOVED***
EOF
)

# 4. Clean up
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# 5. Force push (THIS REWRITES HISTORY)
git push --force --all
git push --force --tags
```

**Step C: Delete stale branches on GitHub**
```bash
git push origin --delete copilot/remove-exposed-keys-and-folders
git push origin --delete copilot/delete-commits-and-branch
```

**Step D: Contact GitHub Support**
Even after force-pushing, old commits may be cached. Visit https://support.github.com/ and request removal of commits `605986e` through `2bf0d7b`.

## Verification Steps
After completing the manual cleanup:
1. Verify keys are removed: `git log -p --all | grep "AIzaSy\|XdP8" || echo "✓ Keys not found"`
2. Check that history stops at the merge commit: `git log --oneline | wc -l` (should be minimal)
3. Verify on GitHub that old commits are not accessible
4. Try accessing old commit URLs directly (should return 404)
5. Search GitHub for your leaked keys to ensure they're not indexed

## Prevention Measures
- ✅ Already implemented: Use environment variables for secrets
- ✅ Already implemented: Added `.gitignore` for sensitive files
- 🔄 Recommended: Enable GitHub secret scanning alerts
- 🔄 Recommended: Use pre-commit hooks to scan for secrets
- 🔄 Recommended: Regular security audits

## Status
✅ **Completed in this automated session:**
- [x] Analyzed repository and identified exposed secrets
- [x] Documented all exposed API keys and affected commits  
- [x] Created detailed security incident report
- [x] Provided cleanup script (`cleanup_history.sh`)
- [x] Listed exact commands for history rewrite

⚠️ **Requires manual action by repository owner:**
- [ ] **CRITICAL**: Revoke exposed Gemini API key at https://aistudio.google.com/apikey
- [ ] **CRITICAL**: Revoke exposed Roboflow API key at https://app.roboflow.com/settings/api
- [ ] Run `cleanup_history.sh` script OR manually rewrite git history
- [ ] Force push cleaned history to GitHub
- [ ] Delete stale branches: `copilot/remove-exposed-keys-and-folders` and `copilot/delete-commits-and-branch`
- [ ] Contact GitHub support to purge cached commits
- [ ] Notify all collaborators to re-clone the repository
- [ ] Verify all traces of keys are removed

**Why manual action is required:**
The automated environment does not allow force-push operations (required to rewrite git history). These operations must be performed by the repository owner with admin access.
