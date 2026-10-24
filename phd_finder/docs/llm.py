from __future__ import annotations

import os
import textwrap

from phd_finder.config_loader import load_profile


SYSTEM = (
    "You write concise academic cover letters for a PhD applicant. "
    "Use only facts provided. Do not invent publications, grades, or employers. "
    "Return plain paragraphs separated by blank lines, no markdown."
)


def tailor_letter(position: dict, fallback: str) -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return fallback
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key, base_url=os.getenv("OPENAI_BASE_URL") or None)
        full = load_profile()
        profile = full["applicant"]
        facts = full.get("letter_facts") or []
        facts_block = "\n".join(f"- {f}" for f in facts) or "- (none beyond thesis title)"
        skills = full.get("skills_summary") or ""
        prompt = textwrap.dedent(
            f"""
            Write a one-page cover letter from {profile['full_name']}
            ({profile['highest_degree']}, {profile['university']})
            for this PhD opening.

            Position: {position.get('title')}
            Institution: {position.get('institution')}
            City/Country: {position.get('city')} {position.get('country')}
            Contact: {position.get('pi_or_contact') or 'Hiring committee'}
            Description excerpt:
            {(position.get('description') or '')[:1800]}

            Facts you may use:
            - Thesis: {profile['thesis_title']}
            {facts_block}
            - Skills: {skills or 'use only skills implied by the facts above'}
            - Email: {profile['email']}

            Tone: specific, modest, not salesy. 4 short paragraphs.
            """
        ).strip()
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or fallback
    except Exception as exc:  # noqa: BLE001
        print(f"[llm] falling back to template: {exc}")
        return fallback
