#!/bin/bash
echo "Pulling remote changes with rebase and autostash..."
git pull -r --autostash

# If there are conflicts, git pull will pause and the script will exit or wait.
# We check if a rebase is in progress
if [ -d ".git/rebase-merge" ] || [ -d ".git/rebase-apply" ]; then
    echo "There are merge conflicts! Please resolve them manually."
    echo "After resolving, run 'git rebase --continue' and then 'git push'."
    exit 1
fi

echo "Pushing changes back to remote..."
git push

echo "Merge and push completed successfully."
