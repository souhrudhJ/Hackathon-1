# Post-Cleanup Branch Deletion Instructions

After completing the git history cleanup (see `SECURITY_INCIDENT_REPORT.md`), you must delete the following branches to complete the security remediation:

## Branches to Delete

### 1. copilot/remove-exposed-keys-and-folders
This branch contains the original fix commit that removed keys from files, but it still has access to parent commits with exposed keys.

```bash
# Delete from GitHub
git push origin --delete copilot/remove-exposed-keys-and-folders

# Delete locally if you have it
git branch -D copilot/remove-exposed-keys-and-folders
```

### 2. copilot/delete-commits-and-branch (THIS BRANCH)
This is the working branch used for the security audit. After you've completed the cleanup and verified everything works, this branch should also be deleted.

```bash
# First, merge any needed documentation to main
git checkout main
git merge copilot/delete-commits-and-branch  # or cherry-pick specific commits

# Then delete
git push origin --delete copilot/delete-commits-and-branch
git branch -D copilot/delete-commits-and-branch
```

## Why Delete These Branches?

Even though the `main` branch will have cleaned history after you run `cleanup_history.sh`, these feature branches still reference the old commits. If someone accesses these branches directly, they could potentially see the old history with exposed keys.

## Verification

After deletion, verify the branches are gone:
```bash
git branch -r | grep copilot
# Should return nothing
```

Also check on GitHub that the branches no longer appear in the branch dropdown.

## Order of Operations

1. ✅ Revoke API keys (DONE FIRST)
2. ✅ Read security documentation (You're doing this now)
3. ⏳ Run `cleanup_history.sh` to rewrite history
4. ⏳ Force push cleaned history
5. ⏳ Delete these copilot branches
6. ⏳ Contact GitHub support for cached commit removal
7. ⏳ Notify collaborators to re-clone
