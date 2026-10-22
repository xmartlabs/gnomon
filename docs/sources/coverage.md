---
hide: [navigation, toc]
---

<span class="gn-label">Sources</span>

# What each source measures

<p class="gn-thesis">Each tool records a different set of signals, so each one can feed a different set of AQ axes. A signal a tool cannot record is never scored as zero: it is left out, and its weight goes to what the tool can measure.</p>

The table below comes from what each tool writes to disk, as declared in `SOURCE_CAPS` in `gnomon/config.py`. Each cell reads:

- **Full**: every term of the axis can be measured from this tool.
- **Partial**: some terms can't be measured. They are dropped and the remaining terms carry the axis. Hover the cell to see which terms count.
- **Not scored**: the tool can't record what the axis needs, so the axis is dropped and the rest of its pillar carries the weight.

{{ coverage_matrix() }}

When you use several tools in one month, gnomon merges their sessions and scores them once, so an axis counts as long as any of your tools can measure it.

Some limits depend on your data, not on the tool, for example an axis that needs at least 5 eligible sessions. Those are explained on each axis's page. [Steering leverage](../metrics/efficiency/steering-leverage.md) is left out of the table because it is not scored yet for any tool.
