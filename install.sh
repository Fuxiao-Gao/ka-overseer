#!/bin/zsh
# Symlink the skill into ~/.claude/skills and run the suite. Idempotent.
set -eu
here="${0:A:h}"
mkdir -p ~/.claude/skills
ln -sfn "$here/skills/working-with-the-overseer" ~/.claude/skills/working-with-the-overseer
echo "skill linked: ~/.claude/skills/working-with-the-overseer -> $here/skills/working-with-the-overseer"
chmod +x "$here/overseer/watch.sh"
python3 -m pytest "$here/overseer/tests" -q
echo
echo "Next: edit $here/overseer/config.json, run 'zsh $here/overseer/watch.sh' in a spare terminal,"
echo "then start a Claude Code session in $here with briefs/overseer-loop.txt as its /loop prompt."
