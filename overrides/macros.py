"""mkdocs-macros entry point for the gnomon docs site.

Every number a reader sees on a metrics page is rendered from
docs/data/metrics.json by the functions in this module.
"""


def define_env(env):
    """Register the site's macros with mkdocs-macros."""
