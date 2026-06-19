def pick_archetype(stats, scores):
    """Honest level read — NOT a flattering identity. One vocabulary, driven by AQ
    (the score that actually separates level): Novice < Apprentice < Adequate <
    Proficient < Advanced < Elite. A low score reads low; we don't dress it up. The
    quote names the thinnest AQ pillar so the gap is visible, not hidden — if you fall
    short somewhere, it says so."""
    aq = stats.get("agentic", {})
    rung = aq.get("tier", "Novice")
    score = aq.get("aq_0_100", 0)
    pillars = aq.get("pillars", [])
    gap = min(pillars, key=lambda p: p["score"])["name"].lower() if pillars else None
    g = f" Your thinnest axis is {gap} — that's where the next gain is." if gap else ""
    if score >= 75:
        q = "You operate at the top — broad machinery, well used." + g
    elif score >= 60:
        q = "Proficient and consistent, but not yet at the top tier." + g
    elif score >= 45:
        q = "Adequate. The fundamentals are there, with real room to grow." + g
    elif score >= 25:
        q = "Still developing — the habits aren't compounding yet." + g
    else:
        q = "Just getting started. Broad gaps to close before the rest pays off." + g
    return rung, q
