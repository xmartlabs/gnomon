"""_common.Window and _common.parse(): the window every check filters with.

An off-by-one here does not break one check, it silently re-scopes the whole skill.
"""
import datetime
import harness

NEEDS = ()

_c = harness.load("_common.py")
UTC = datetime.timezone.utc
START = datetime.datetime(2026, 7, 12, tzinfo=UTC)
END = datetime.datetime(2026, 8, 11, tzinfo=UTC)
TICK = datetime.timedelta(microseconds=1)


def check_window_is_half_open(t):
    w = _c.Window(START, END)
    t.equal(START in w, True, "the start is inside")
    t.equal(END in w, False, "the end is OUTSIDE -- [start, end), not [start, end]")
    t.equal(END - TICK in w, True, "one tick before the end is inside")
    t.equal(START - TICK in w, False, "one tick before the start is outside")


def check_window_rejects_none(t):
    t.equal(None in _c.Window(START, END), False, "an event with no timestamp is not inside")


def check_parse_requires_a_gnomon_shaped_checkout(t):
    with harness.tmpdir() as empty:
        with harness.argv(["x", "--checkout", empty]):
            exc = t.raises(SystemExit, lambda: _c.parse("probe", needs_corpus=False),
                           "a directory with no gnomon/ is refused")
        if exc:
            t.contains(str(exc), "does not look like a gnomon checkout", "and says why")
    # CONTROL: the same call against a directory that does have gnomon/ must NOT exit.
    # Without it, "is refused" could mean "refuses everything", which is a different function.
    with harness.fake_checkout() as ok:
        with harness.argv(["x", "--checkout", ok]):
            t.completes(lambda: _c.parse("probe", needs_corpus=False),
                        "CONTROL: a directory that DOES have gnomon/ is accepted")


def check_parse_requires_the_corpus_by_default(t):
    with harness.fake_checkout() as ok:
        with harness.argv(["x", "--checkout", ok, "--corpus", "/no/such/dir"]):
            exc = t.raises(SystemExit, lambda: _c.parse("probe"),
                           "needs_corpus defaults to True and the missing corpus is refused")
        if exc:
            t.contains(str(exc), "corpus not found", "and says which input was missing")


def check_needs_corpus_false_skips_that_check(t):
    # This pair IS the specification the three synthetic-fixture scripts rely on. It has to
    # stay green before and after they are switched over.
    with harness.fake_checkout() as ok:
        with harness.argv(["x", "--checkout", ok, "--corpus", "/no/such/dir"]):
            got = t.completes(lambda: _c.parse("probe", needs_corpus=False),
                              "needs_corpus=False does not require the corpus to exist")
        if got:
            t.equal(got[0].corpus, "/no/such/dir",
                    "the flag is still ACCEPTED, just not required")


def check_until_is_exclusive_and_utc(t):
    with harness.fake_checkout() as ok:
        with harness.argv(["x", "--checkout", ok, "--until", "2026-07-31"]):
            _args, w = _c.parse("probe", needs_corpus=False)
    boundary = datetime.datetime(2026, 7, 31, tzinfo=UTC)
    t.equal(w.end, boundary, "--until parses as midnight UTC of that day")
    t.equal(boundary in w, False, "and that instant is OUTSIDE the window")
    t.equal(boundary - TICK in w, True, "the last instant of the 30th is inside")


def check_since_until_span_conflict_exits(t):
    with harness.fake_checkout() as ok:
        with harness.argv(["x", "--checkout", ok, "--since", "2026-07-01",
                           "--until", "2026-07-31", "--days", "5"]):
            exc = t.raises(SystemExit, lambda: _c.parse("probe", needs_corpus=False),
                           "--days that disagrees with the --since/--until span is refused")
        if exc:
            t.contains(str(exc), "--days", "and names the flag that disagrees")
        # CONTROL: --days left at its 30 default over a 20-day span is EXEMPT on purpose.
        # Pinning the exemption means removing it is a decision and not a silent tightening.
        with harness.argv(["x", "--checkout", ok, "--since", "2026-07-01",
                           "--until", "2026-07-21"]):
            _args, w = _c.parse("probe", needs_corpus=False)
        t.equal((w.end - w.start).days, 20, "the span wins over the default")


def check_since_not_before_until_exits(t):
    with harness.fake_checkout() as ok:
        with harness.argv(["x", "--checkout", ok, "--since", "2026-07-31",
                           "--until", "2026-07-31"]):
            t.raises(SystemExit, lambda: _c.parse("probe", needs_corpus=False),
                     "an empty window is refused rather than measured")


def check_bad_date_shape_exits(t):
    with harness.fake_checkout() as ok:
        with harness.argv(["x", "--checkout", ok, "--until", "31-07-2026"]):
            exc = t.raises(SystemExit, lambda: _c.parse("probe", needs_corpus=False),
                           "a day-first date is refused, not silently reinterpreted")
        if exc:
            t.contains(str(exc), "YYYY-MM-DD", "and says the shape it wanted")


def check_header_states_fixed_vs_rolling(t):
    with harness.fake_checkout() as ok:
        with harness.argv(["x", "--checkout", ok, "--until", "2026-07-31"]):
            args, w = _c.parse("probe", needs_corpus=False)
        t.contains(_c.header(args, w), "fixed", "a pinned window says so in the banner")
        with harness.argv(["x", "--checkout", ok]):
            args, w = _c.parse("probe", needs_corpus=False)
        t.contains(_c.header(args, w), "rolling, ends now", "and a rolling one says that")
