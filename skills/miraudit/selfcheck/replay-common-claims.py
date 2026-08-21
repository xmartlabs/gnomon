"""_common.claims / COVERS_RX: which script covers which axis.

Discovery is a grep for a comment and not an import, and the reason is load-bearing: a check
with a syntax error must still be visible as claiming its axis, because silence from a broken
file reads as "no script exists" -- which is the exact distinction axis-coverage.py is for.
"""
import os
import harness

NEEDS = ()

_c = harness.load("_common.py")
TAG = "# " + "miraudit-covers:"     # split so this file does not claim an axis of its own


def _tree(root, files):
    for name, body in files.items():
        with open(os.path.join(root, name), "w") as fh:
            fh.write(body)
    return os.path.join(root, "*.py")


def check_a_tag_at_column_zero_is_claimed(t):
    with harness.tmpdir() as d:
        got = _c.claims(_tree(d, {"a.py": "x = 1\n%s Recovery\n" % TAG}))
        t.equal(got, {"Recovery": ["a.py"]}, "one tag, one axis, one file")


def check_two_tags_in_one_file_are_both_claimed(t):
    with harness.tmpdir() as d:
        got = _c.claims(_tree(d, {"a.py": "%s Recovery\n%s Discipline\n" % (TAG, TAG)}))
        t.equal(got, {"Recovery": ["a.py"], "Discipline": ["a.py"]},
                "a check covering two axes claims both")


def check_two_files_claiming_one_axis_are_both_listed(t):
    with harness.tmpdir() as d:
        got = _c.claims(_tree(d, {"a.py": "%s Recovery\n" % TAG,
                                  "b.py": "%s Recovery\n" % TAG}))
        t.equal(got, {"Recovery": ["a.py", "b.py"]}, "and the list is sorted by filename")


def check_an_indented_tag_is_invisible(t):
    # COVERS_RX anchors on ^#. Pinned rather than fixed: reformatting a script would silently
    # drop its axis from coverage, and that should be a decision somebody makes on purpose.
    with harness.tmpdir() as d:
        t.equal(_c.claims(_tree(d, {"a.py": "def f():\n    %s Recovery\n" % TAG})), {},
                "an indented tag does not claim -- the anchor is deliberate")


def check_a_syntactically_broken_file_still_claims_its_axis(t):
    """The whole reason claims() greps instead of importing.

    A refactor to import-based discovery passes every other check in this file and fails only
    here, which is what makes this one worth having.
    """
    with harness.tmpdir() as d:
        broken = "def (:\n%s Recovery\n" % TAG
        t.equal(_c.claims(_tree(d, {"a.py": broken})), {"Recovery": ["a.py"]},
                "a file Python cannot parse is still visible as covering its axis")


def check_claims_returns_basenames_not_paths(t):
    # run-checks.py joins the result onto HERE. A full path there would produce a doubled one.
    with harness.tmpdir() as d:
        got = _c.claims(_tree(d, {"a.py": "%s Recovery\n" % TAG}))
        t.equal(got["Recovery"], ["a.py"], "basename, never the path it was found at")


def check_the_real_scripts_directory_claims_something(t):
    # A control on the three synthetic cases above: if claims() broke in a way the fixtures
    # miss, the real tree going empty is the loudest possible signal.
    got = _c.claims(os.path.join(harness.SCRIPTS, "*.py"))
    t.equal(len(got) > 0, True, "CONTROL: the shipped scripts/ claims at least one axis")
