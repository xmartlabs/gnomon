"""_common.find_all / find_key / dig: how every check reads the tool's own payload.

find_key exists because hardcoding a path does not survive the payload being re-nested. What
it does not survive is a name that repeats with different values, and an earlier version
answered `tool_calls` with ONE MONTH's count while presenting it as the window's.
"""
import harness

NEEDS = ()

_c = harness.load("_common.py")


def check_find_key_refuses_ambiguity(t):
    payload = {"a": {"tool_calls": 1}, "b": {"tool_calls": 2}}
    exc = t.raises(KeyError, lambda: _c.find_key(payload, "tool_calls"),
                   "the same name with two values is refused, not resolved")
    if exc:
        t.contains(str(exc), "/a/tool_calls", "and names the first path")
        t.contains(str(exc), "/b/tool_calls", "and the second")
    # CONTROL: the same NAME repeated with the same VALUE is not ambiguous, and must return.
    # Without this, "refuses ambiguity" could mean "refuses any repeat", which is a different
    # and much more annoying function.
    t.equal(_c.find_key({"a": {"tool_calls": 7}, "b": {"tool_calls": 7}}, "tool_calls"), 7,
            "CONTROL: repeated name, one value, returns it")


def check_find_key_absent_and_unique(t):
    t.equal(_c.find_key({"a": 1}, "nope"), None, "an absent key is None, not an error")
    t.equal(_c.find_key({"a": {"b": {"sessions": 281}}}, "sessions"), 281,
            "a unique name is found however deeply it is nested")


def check_find_key_compares_by_repr(t):
    # 1 == 1.0 and 1 == True, so an == comparison would call these unambiguous and return a
    # number of the wrong type. Pinning repr makes that a decision rather than an accident.
    for other in (1.0, True):
        t.raises(KeyError, lambda o=other: _c.find_key({"a": {"n": 1}, "b": {"n": o}}, "n"),
                 "1 and %r are distinct values even though == says otherwise" % other)


def check_find_all_paths_are_document_order(t):
    payload = {"a": {"x": 1}, "b": [{"x": 2}, {"x": 3}]}
    t.equal([p for p, _ in _c.find_all(payload, "x")], ["/a/x", "/b[0]/x", "/b[1]/x"],
            "paths use / for dicts and [i] for lists, in document order")


def check_signals_path_filter_still_matches(t):
    """fingerprint.py filters find_all's paths on the literal substring "/signals/".

    A mirror, not a unit test: change find_all's separator to "." and every assertion about
    find_all still passes while fingerprint.py silently reports None for the tool's own
    numbers. Only this check sees it.
    """
    payload = {"agentic": {"pillars": [{"axes": [{"signals": {"tool_calls": 7}},
                                                 {"signals": {"tool_calls": 7}}]}]}}
    hits = [v for p, v in _c.find_all(payload, "tool_calls") if "/signals/" in p]
    t.equal(hits, [7, 7], "the paths fingerprint.py greps for are the paths find_all emits")


def check_dig_reads_an_explicit_path(t):
    payload = {"volume": {"total_sessions": 50}, "list": [{"k": "v"}]}
    t.equal(_c.dig(payload, "volume", "total_sessions"), 50, "a dict path")
    t.equal(_c.dig(payload, "list", 0, "k"), "v", "a list index mid-path")
    t.equal(_c.dig(payload, "list", -1, "k"), "v", "a negative index")
    t.equal(_c.dig(payload, "nope", "deeper"), None, "a missing path is the default")
    t.equal(_c.dig(payload, "list", 9, default="fallback"), "fallback",
            "an out-of-range index is the default, not an IndexError")
