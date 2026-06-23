"""Real-data quality probe: live website enrichment -> rules vs LLM-judge scoring
on identical fetched evidence, plus a Gemini faithfulness judge on the narrative.

Unlike the seeded bake-off (which grades a static fixture against itself), this
fetches real public pages, so the scores reflect the live enrichment + scoring
path. Discovery (Perplexity) and Apollo PII are out of scope here (no keys); the
companies are supplied and the judge is Gemini-on-Vertex via the GCP project.

Run:
    GOOGLE_CLOUD_PROJECT=knowledge2-dev-9650 \
    GOOGLE_APPLICATION_CREDENTIALS=$HOME/.config/gcloud/application_default_credentials.json \
    GEMINI_MODEL=gemini-2.5-flash \
    python3 tools/judge_quality.py
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from icp_engine.apollo import ApolloClient  # noqa: E402
from icp_engine.enrichment import fetch_company_evidence  # noqa: E402
from icp_engine.gemini import classify_with_gemini, generate_outreach  # noqa: E402
from icp_engine.models import CompanyInput  # noqa: E402
from icp_engine.scoring import score_company  # noqa: E402

# Fallback buying-committee contact, used only when Apollo is unconfigured or
# returns no contact that passes the current-employer guard. When APOLLO_API_KEY
# is set (e.g. via .env), the harness reveals a REAL name/title/email instead.
DEMO_PERSONA = {
    "role": "VP Operations",
    "title": "VP of Operations",
    "rationale": "owns the core operational workflow the product runs on",
}


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Load KEY=VALUE pairs from a local .env into os.environ if not already set.
    Tools-only convenience (the product code does not auto-load .env); values are
    never logged."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _domain_root(domain: str) -> str:
    d = domain.lower().strip()
    for prefix in ("https://", "http://", "www."):
        d = d.replace(prefix, "")
    return d.split("/")[0]


def resolve_persona(apollo: ApolloClient, company: CompanyInput) -> tuple[dict, str]:
    """Resolve a real buying-committee contact via Apollo People-Match.

    Applies a current-employer guard (the contact's org website must match the
    target domain — Apollo's domain search occasionally returns someone whose
    *current* employer is elsewhere) and prefers a contact with a revealed email.
    Falls back to ``DEMO_PERSONA`` when Apollo is unconfigured or no guarded
    contact is found, so the harness still runs without a key. Each revealed
    contact spends one Apollo credit.
    """
    if not apollo.configured:
        return dict(DEMO_PERSONA), "synthetic"
    try:
        result = apollo.search_people(domain=company.domain, per_page=5)
    except Exception:  # noqa: BLE001
        return dict(DEMO_PERSONA), "synthetic"
    people = result.get("people", []) if isinstance(result, dict) else []
    target = _domain_root(company.domain)
    matched = [
        p for p in people
        if _domain_root(str((p.get("organization") or {}).get("website_url") or "")) == target
        and p.get("name")
    ]
    if not matched:
        return dict(DEMO_PERSONA), "synthetic"
    matched.sort(key=lambda p: 0 if p.get("revealed") else 1)  # revealed email first
    best = matched[0]
    persona = {
        "role": best.get("title") or DEMO_PERSONA["role"],
        "title": best.get("title") or "",
        "name": best.get("name") or "",
        "email": best.get("email") or "",
        "rationale": "buying-committee contact matched to the account domain via Apollo",
    }
    return persona, ("apollo" if best.get("revealed") else "apollo/unrevealed")

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "knowledge2-dev-9650")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
DIMS = ["ai_posture", "data_workflow", "commercial_urgency", "budget_access", "feasibility"]


def _evidence_text(evidence) -> str:
    return "\n\n".join(f"[{e.evidence_id}] {e.title}\n{e.text}" for e in evidence)[:12000]


def faithfulness_judge(
    client, company: CompanyInput, evidence, text: str, *, kind: str = "NARRATIVE", contact_context: str = ""
) -> dict:
    """Ask Gemini to rate whether generated text is supported by the fetched evidence.

    ``contact_context`` carries verified out-of-band facts (e.g. an Apollo-revealed
    recipient name/title) that the website evidence won't contain but that the text
    is allowed to state — otherwise a real, correctly-revealed contact would be
    scored as a fabrication.
    """
    from google.genai import types

    if not text.strip() or not evidence:
        return {"faithful": None, "unsupported": [], "note": "no text or evidence"}
    contact_block = (
        f"VERIFIED CONTACT (out-of-band, treat as supported fact):\n{contact_context}\n\n"
        if contact_context.strip() else ""
    )
    prompt = (
        "You are a strict fact-checker. Below is EVIDENCE scraped from a company's website, "
        f"and a {kind} a GTM tool generated about that company. Rate how faithful the "
        f"{kind.lower()} is to the evidence: 1.0 = every claim is supported by the evidence "
        "(or the verified contact block), 0.0 = the text is largely fabricated. List any "
        "specific claims NOT supported by the evidence or verified contact.\n\n"
        f"COMPANY: {company.company} ({company.domain})\n\n"
        f"{contact_block}"
        f"EVIDENCE:\n{_evidence_text(evidence)}\n\n"
        f"{kind}:\n{text}\n"
    )
    schema = {
        "type": "OBJECT",
        "required": ["faithful", "unsupported"],
        "properties": {
            "faithful": {"type": "NUMBER"},
            "unsupported": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
    }
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=schema,
            temperature=0.0,
        ),
    )
    data = json.loads(resp.text)
    return {"faithful": data.get("faithful"), "unsupported": data.get("unsupported", [])}


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    from google import genai

    _load_dotenv()
    rows = read_rows(Path(__file__).with_name("judge_companies.csv"))
    cache = Path("out/judge-cache")
    cache.mkdir(parents=True, exist_ok=True)
    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    apollo = ApolloClient.from_env()
    print(f"Apollo: {'configured (live reveal — spends credits)' if apollo.configured else 'not configured (synthetic persona)'}",
          file=sys.stderr)

    records = []
    for row in rows:
        company = CompanyInput(
            company=row["company"].strip(),
            domain=row["domain"].strip(),
            category=row.get("category", "").strip(),
        )
        expected = row.get("expected", "").strip()
        print(f"--- {company.company} ({company.domain}) expected={expected}", file=sys.stderr)
        t0 = time.perf_counter()
        evidence, warnings = fetch_company_evidence(
            company, cache / company.domain.replace("/", "_"),
            timeout_seconds=8, max_pages=3,
        )
        fetch_ms = round((time.perf_counter() - t0) * 1000)
        ev_chars = sum(len(e.text or "") for e in evidence)

        rules = score_company(company, evidence, model_classification=None, fetch_warnings=list(warnings))
        gem_class = None
        gem_err = None
        if evidence:
            try:
                gem_class = classify_with_gemini(company, evidence)
            except Exception as exc:  # noqa: BLE001
                gem_err = str(exc).splitlines()[0][:120]
        judge = score_company(company, evidence, model_classification=gem_class, fetch_warnings=list(warnings))

        faith = {"faithful": None, "unsupported": []}
        narrative = judge.ai_narrative or rules.ai_narrative
        if evidence:
            try:
                faith = faithfulness_judge(client, company, evidence, narrative, kind="NARRATIVE")
            except Exception as exc:  # noqa: BLE001
                faith = {"faithful": None, "unsupported": [], "note": str(exc).splitlines()[0][:120]}

        # Outreach is only generated for accounts that pass the gates (a Reject
        # never gets an email), so we mirror that: generate + judge only when the
        # judge tier is not Reject.
        outreach = None
        outreach_faith = {"faithful": None, "unsupported": []}
        persona, persona_source = DEMO_PERSONA, "synthetic"
        if evidence and judge.tier != "Reject":
            persona, persona_source = resolve_persona(apollo, company)
            contact_context = (
                f"Recipient: {persona.get('name') or '(name withheld)'}, "
                f"title \"{persona.get('title') or persona.get('role')}\", "
                f"email {'present' if persona.get('email') else 'not revealed'} "
                f"(source: {persona_source})."
            )
            try:
                outreach = generate_outreach(company, persona, evidence)
                outreach_faith = faithfulness_judge(
                    client, company, evidence, outreach.get("body", ""),
                    kind="OUTREACH EMAIL", contact_context=contact_context,
                )
            except Exception as exc:  # noqa: BLE001
                outreach_faith = {"faithful": None, "unsupported": [], "note": str(exc).splitlines()[0][:120]}

        rec = {
            "company": company.company,
            "domain": company.domain,
            "expected": expected,
            "fetch_ok": bool(evidence),
            "pages": len(evidence),
            "ev_chars": ev_chars,
            "fetch_ms": fetch_ms,
            "rules_tier": rules.tier,
            "rules_score": rules.total_score,
            "judge_tier": judge.tier,
            "judge_score": judge.total_score,
            "gem_dims": None if gem_class is None else {d: getattr(gem_class, d) for d in DIMS},
            "rules_dims": {d: getattr(rules.classification, d) for d in DIMS},
            "gem_err": gem_err,
            "faithful": faith.get("faithful"),
            "unsupported": faith.get("unsupported", []),
            "narrative": narrative,
            "outreach_subject": None if outreach is None else outreach.get("subject"),
            "outreach_body": None if outreach is None else outreach.get("body"),
            "outreach_faithful": outreach_faith.get("faithful"),
            "outreach_unsupported": outreach_faith.get("unsupported", []),
            "persona_source": persona_source,
            "persona_title": persona.get("title") or persona.get("role"),
            "persona_revealed": bool(persona.get("email")),  # email itself is never stored/logged
        }
        records.append(rec)
        print(f"    fetch={rec['pages']}p/{ev_chars}c  rules={rec['rules_tier']}/{rec['rules_score']}  "
              f"judge={rec['judge_tier']}/{rec['judge_score']}  faithful={rec['faithful']}  "
              f"outreach_faithful={rec['outreach_faithful']}", file=sys.stderr)

    out = Path("out/judge-quality-report.json")
    out.write_text(json.dumps(records, indent=2), encoding="utf-8")
    _summarize(records)
    print(f"\nWrote {out}", file=sys.stderr)
    return 0


def _tier_fit(tier: str) -> str:
    return "nonfit" if tier == "Reject" else "fit"


def _summarize(records: list[dict]) -> None:
    fetched = [r for r in records if r["fetch_ok"]]
    print("\n================ SUMMARY ================")
    print(f"companies: {len(records)}  | fetched real evidence: {len(fetched)}/{len(records)}")

    # Tier correctness vs expected label (fit = A/B/C, nonfit = Reject), on fetched only.
    def acc(key):
        labeled = [r for r in fetched if r["expected"] in {"fit", "nonfit"}]
        if not labeled:
            return None
        hits = sum(1 for r in labeled if _tier_fit(r[key]) == r["expected"])
        return f"{hits}/{len(labeled)} ({round(100*hits/len(labeled))}%)"

    print(f"fit/nonfit accuracy  rules: {acc('rules_tier')}   judge: {acc('judge_tier')}")

    # Rules vs judge agreement (fetched, where gemini ran).
    paired = [r for r in fetched if r["gem_dims"]]
    if paired:
        tier_agree = sum(1 for r in paired if r["rules_tier"] == r["judge_tier"])
        maes = []
        for d in DIMS:
            maes.append(sum(abs(r["gem_dims"][d] - r["rules_dims"][d]) for r in paired) / len(paired))
        print(f"rules vs judge tier agreement: {tier_agree}/{len(paired)}")
        print("per-dimension mean abs diff (gemini vs rules, 0-5 scale):")
        for d, m in zip(DIMS, maes):
            print(f"    {d:20s} {round(m, 2)}")

    faiths = [r["faithful"] for r in fetched if isinstance(r["faithful"], (int, float))]
    if faiths:
        print(f"narrative faithfulness (Gemini judge, 0-1): mean {round(sum(faiths)/len(faiths), 3)} over {len(faiths)}")
    ofaiths = [r["outreach_faithful"] for r in fetched if isinstance(r.get("outreach_faithful"), (int, float))]
    if ofaiths:
        print(f"outreach faithfulness (Gemini judge, 0-1): mean {round(sum(ofaiths)/len(ofaiths), 3)} over {len(ofaiths)}")

    # Persona provenance: how many outreach contacts came from a real Apollo
    # reveal vs the synthetic fallback (emails never logged, only the flag).
    with_outreach = [r for r in fetched if r.get("outreach_body")]
    if with_outreach:
        apollo_n = sum(1 for r in with_outreach if str(r.get("persona_source", "")).startswith("apollo"))
        revealed_n = sum(1 for r in with_outreach if r.get("persona_revealed"))
        print(f"persona source: {apollo_n}/{len(with_outreach)} via Apollo "
              f"({revealed_n} with a revealed email), rest synthetic")
    flagged = [(r["company"], r["unsupported"]) for r in fetched if r["unsupported"]]
    if flagged:
        print("unsupported narrative claims:")
        for name, claims in flagged:
            print(f"    {name}: {claims[:3]}")
    oflagged = [(r["company"], r["outreach_unsupported"]) for r in fetched if r.get("outreach_unsupported")]
    if oflagged:
        print("unsupported outreach claims:")
        for name, claims in oflagged:
            print(f"    {name}: {claims[:3]}")


if __name__ == "__main__":
    raise SystemExit(main())
