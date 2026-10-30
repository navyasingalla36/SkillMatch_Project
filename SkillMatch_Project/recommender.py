"""Hybrid job recommender: 75% exact skill coverage + 25% TF-IDF cosine similarity."""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

COVERAGE_WEIGHT = 0.75
TFIDF_WEIGHT = 0.25


def parse_skills(text):
    """'Python, Flask\nSQL' -> ['python', 'flask', 'sql'] (lowercase, no duplicates)."""
    seen, out = set(), []
    for s in (text or "").replace("\n", ",").replace(";", ",").split(","):
        s = s.strip().lower()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def analyze_job(user_skills_text, job_skills_text):
    """Skill gap analysis: matched skills, missing skills and coverage (0..1)."""
    user = set(parse_skills(user_skills_text))
    required = [s.strip() for s in (job_skills_text or "").split(",") if s.strip()]
    matched = [s for s in required if s.lower() in user]
    missing = [s for s in required if s.lower() not in user]
    coverage = len(matched) / len(required) if required else 0.0
    return {"matched": matched, "missing": missing, "coverage": coverage}


def rank_jobs(user_skills_text, jobs):
    """Return [{'job', 'score', 'matched', 'missing'}] sorted by score (highest first)."""
    jobs = list(jobs)
    if not jobs:
        return []
    user_doc = " ".join(parse_skills(user_skills_text))
    docs = [user_doc] + [f"{j['title']} {j['skills']} {j['description']}" for j in jobs]
    try:
        vec = TfidfVectorizer(token_pattern=r"[A-Za-z0-9+#.]+", stop_words="english")
        matrix = vec.fit_transform(docs)
        sims = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
    except ValueError:  # empty vocabulary
        sims = [0.0] * len(jobs)

    results = []
    for job, sim in zip(jobs, sims):
        a = analyze_job(user_skills_text, job["skills"])
        score = COVERAGE_WEIGHT * a["coverage"] + TFIDF_WEIGHT * float(sim)
        results.append({"job": job, "score": max(0, min(100, round(score * 100))),
                        "matched": a["matched"], "missing": a["missing"]})
    results.sort(key=lambda r: r["score"], reverse=True)
    return results
