# ⚠️ CRITICAL SECURITY ALERT ⚠️

## EXPOSED API KEYS IN GIT HISTORY

Your repository contains exposed API keys in previous commits. **IMMEDIATE ACTION REQUIRED.**

### 🚨 URGENT - Do This First (< 5 minutes)

1. **Revoke Gemini API Key**: https://aistudio.google.com/apikey
2. **Revoke Roboflow API Key**: https://app.roboflow.com/settings/api  
3. Generate new keys and set as environment variables

### 📋 Full Details

Read `SECURITY_INCIDENT_REPORT.md` for:
- List of all exposed keys
- All affected commits  
- Step-by-step cleanup instructions
- Automated cleanup script

### 🛠️ Quick Cleanup

```bash
# After revoking keys, run:
chmod +x cleanup_history.sh
./cleanup_history.sh
```

### ℹ️ What Happened

API keys were hardcoded in `config.py` and `train.py` in commits from Feb 15-16, 2026. While they were removed from current files, they remain visible in git history and must be purged.

### 📞 Need Help?

- GitHub Support: https://support.github.com/ (select "Remove sensitive data")
- Git filter-repo docs: https://github.com/newren/git-filter-repo

---
**This alert was generated automatically by the security audit system.**
