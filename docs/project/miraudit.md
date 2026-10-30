<span class="gn-label">Project</span>

# miraudit

<p class="gn-thesis">miraudit is a Claude Code skill that checks whether your AQ reflects what you actually did. It reproduces your published number on your own machine, re-measures each axis from your transcripts, and reports any gap with proof you can run.</p>

## Quick start

Install it with the skills CLI, for this project or for all your projects:

```bash
npx skills add xmartlabs/gnomon -s miraudit -a claude-code -y      # this project
npx skills add xmartlabs/gnomon -s miraudit -a claude-code -g -y   # all projects
```

Then run it from Claude Code:

```
/miraudit
```

A report with no AQ to compare against is the normal case, not a failure. Leave `--published` out and the anchor still checks the scoring contract and prints the number, but records `anchor.ok: null`, which every later step reads as "nobody compared this" rather than as a pass. The checks still run. The gate that matters comes when the report is written: a run with findings whose anchor is not `ok: true` must say in `anchor.note` what was checked and what was not.

The full guide follows. It is maintained next to the skill, in [`skills/miraudit/README.md`](https://github.com/xmartlabs/gnomon/blob/main/skills/miraudit/README.md).

## About miraudit

--8<-- "skills/miraudit/README.md:2"
