import os
import json
import time
import requests
from datetime import datetime, timezone

# ── Auth ──────────────────────────────────────────────────────────────────────
LEETCODE_SESSION   = os.environ["LEETCODE_SESSION"]
LEETCODE_CSRF_TOKEN = os.environ["LEETCODE_CSRF_TOKEN"]

GRAPHQL_URL = "https://leetcode.com/graphql"
HEADERS = {
    "Content-Type": "application/json",
    "Cookie": f"LEETCODE_SESSION={LEETCODE_SESSION}; csrftoken={LEETCODE_CSRF_TOKEN}",
    "x-csrftoken": LEETCODE_CSRF_TOKEN,
    "Referer": "https://leetcode.com",
}

# ── Language → file extension ─────────────────────────────────────────────────
LANG_EXT = {
    "python": "py", "python3": "py",
    "c": "c", "cpp": "cpp",
    "java": "java",
    "javascript": "js", "typescript": "ts",
    "go": "go", "rust": "rs",
    "swift": "swift", "kotlin": "kt",
    "ruby": "rb", "scala": "scala",
    "csharp": "cs", "php": "php",
}

C_STYLE = {"c", "cpp", "java", "js", "ts", "go", "rs", "swift", "kt", "cs", "php", "scala"}


# ── GraphQL helpers ───────────────────────────────────────────────────────────
def gql(query: str, variables: dict) -> dict:
    resp = requests.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_accepted_submissions() -> list[dict]:
    """Return one submission per unique problem (most-recent accepted)."""
    QUERY = """
    query submissionList($offset: Int!, $limit: Int!, $status: Int) {
      submissionList(offset: $offset, limit: $limit, status: $status) {
        hasNext
        submissions {
          id lang timestamp statusDisplay title titleSlug
        }
      }
    }
    """
    seen, results, offset = set(), [], 0
    print("  Fetching submission list", end="", flush=True)
    while True:
        data = gql(QUERY, {"offset": offset, "limit": 20, "status": 10})["data"]["submissionList"]
        for s in data["submissions"]:
            if s["titleSlug"] not in seen:
                seen.add(s["titleSlug"])
                results.append(s)
        print(".", end="", flush=True)
        if not data["hasNext"]:
            break
        offset += 20
        time.sleep(0.4)
    print(f"  {len(results)} unique accepted problems")
    return results


def fetch_code(submission_id: str) -> dict | None:
    QUERY = """
    query submissionDetails($submissionId: Int!) {
      submissionDetails(id: $submissionId) {
        code
        lang { name verboseName }
        question {
          title titleSlug difficulty
          topicTags { name }
        }
      }
    }
    """
    try:
        return gql(QUERY, {"submissionId": int(submission_id)})["data"]["submissionDetails"]
    except Exception as e:
        print(f"    ⚠ Could not fetch code for #{submission_id}: {e}")
        return None


# ── File writing ──────────────────────────────────────────────────────────────
def build_header(title: str, difficulty: str, tags: list[str], lang_verbose: str, ext: str) -> str:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tag_str = ", ".join(tags) if tags else "—"
    lines = [
        f"  {title}",
        f"  Difficulty : {difficulty}",
        f"  Tags       : {tag_str}",
        f"  Language   : {lang_verbose}",
        f"  Synced     : {date}",
    ]
    if ext in C_STYLE:
        body = "\n".join(f" * {l.strip()}" for l in lines)
        return f"/*\n{body}\n */\n\n"
    else:  # Python, Ruby, etc.
        body = "\n".join(f"# {l.strip()}" for l in lines)
        return f"{body}\n\n"


def save_solution(submission: dict, details: dict) -> bool:
    slug       = submission["titleSlug"]
    lang       = submission["lang"]
    ext        = LANG_EXT.get(lang, lang)
    difficulty = details["question"]["difficulty"]
    tags       = [t["name"] for t in details["question"]["topicTags"]]
    title      = details["question"]["title"]
    lang_verb  = details["lang"]["verboseName"]

    # solutions/Easy/two-sum/solution.py
    folder = os.path.join("solutions", difficulty, slug)
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, f"solution.{ext}")

    if os.path.exists(filepath):
        return False  # already synced, skip

    header = build_header(title, difficulty, tags, lang_verb, ext)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(header + details["code"])

    print(f"  ✓  [{difficulty:<6}] {title}  ({lang_verb})")
    return True


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    print("\n🔍 Fetching accepted submissions from LeetCode...\n")
    submissions = fetch_accepted_submissions()

    synced = skipped = errors = 0
    print("\n📥 Syncing solutions...\n")
    for sub in submissions:
        details = fetch_code(sub["id"])
        if details is None:
            errors += 1
            continue
        try:
            if save_solution(sub, details):
                synced += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  ✗  Failed to save {sub['title']}: {e}")
            errors += 1
        time.sleep(0.25)   # be polite to LeetCode's API

    print(f"\n✅  Done — {synced} new  |  {skipped} already synced  |  {errors} errors\n")

    # Lightweight summary file committed alongside solutions
    summary_path = os.path.join("solutions", "sync_summary.json")
    summary = {
        "last_sync_utc": datetime.now(timezone.utc).isoformat(),
        "total_unique_problems": len(submissions),
        "synced_this_run": synced,
    }
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
