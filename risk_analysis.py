from typing import Dict, Any, List, Optional
import os

from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def get_openrouter_client() -> Optional[OpenAI]:
    """Create OpenAI client configured for OpenRouter."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None
    
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


def build_risk_facts(activity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Take parsed BRRTS activity data and compute simple boolean flags.
    This is where we encode Cobalt-style red flags.
    """
    substances: List[Dict[str, Any]] = activity.get("substances") or []
    characteristics: List[str] = activity.get("characteristics") or []

    # Lowercase helpers
    chars_lower = [c.lower() for c in characteristics]
    names_lower = [
        f"{(s.get('name') or '').lower()} {(s.get('type') or '').lower()}"
        for s in substances
    ]

    has_pfas = any("pfas" in c for c in chars_lower) or any("pfas" in n for n in names_lower)
    has_petroleum = any("petroleum" in n or "gasoline" in n for n in names_lower)
    has_heavy_metals = any(
        any(m in n for m in ["arsenic", "lead", "chromium", "metal"])
        for n in names_lower
    )
    offsite_impact_flag = any("row impact" in c or "off-site" in c for c in chars_lower)

    num_substances = len(substances)

    return {
        "has_pfas": has_pfas,
        "has_petroleum": has_petroleum,
        "has_heavy_metals": has_heavy_metals,
        "offsite_impact_flag": offsite_impact_flag,
        "num_substances": num_substances,
        "status_flag": activity.get("status") or "UNKNOWN",
    }


def summarize_red_flags(activity: Dict[str, Any], risk_facts: Dict[str, Any]) -> str:
    """
    Use AI to generate a clean, professional, developer-ready risk summary.

    If the API call fails for any reason, fall back to a rule-based summary.
    """
    client = get_openrouter_client()
    if not client:
        return _fallback_summary(activity, risk_facts, error="OPENROUTER_API_KEY not set")
    
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an environmental due diligence analyst for a "
                    "commercial real estate developer. You are given parsed data "
                    "from the Wisconsin DNR BRRTS system. Produce a concise, "
                    "professional summary appropriate for a Phase I ESA memo."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Here is the parsed BRRTS activity data:\n"
                    f"{activity}\n\n"
                    "Here are derived risk flags:\n"
                    f"{risk_facts}\n\n"
                    "Write your analysis using the following structure:\n"
                    "1. Site Overview\n"
                    "2. Key Contaminants / Concerns\n"
                    "3. Regulatory / Status Notes\n"
                    "4. Recommended Next Steps\n\n"
                    "Be factual about what is known vs missing."
                ),
            },
        ]

        completion = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=messages,
            temperature=0.25,
        )

        return completion.choices[0].message.content.strip()

    except Exception as exc:
        return _fallback_summary(activity, risk_facts, error=str(exc))


def chat_with_context(
    activity: Dict[str, Any],
    risk_facts: Dict[str, Any],
    history: List[Dict[str, str]],
    message: str,
) -> str:
    """
    Chat endpoint helper: use BRRTS context + prior Q&A history.
    """
    client = get_openrouter_client()
    if not client:
        return "OPENROUTER_API_KEY not set in environment. Please configure your API key."
    
    try:
        base_system = {
            "role": "system",
            "content": (
                "You are an environmental due diligence analyst. "
                "Use the BRRTS data and risk facts provided to answer questions "
                "about environmental risk for this site. If you don't know "
                "something from the data, say so and suggest what documents or "
                "steps would be needed."
            ),
        }

        context_msg = {
            "role": "system",
            "content": f"BRRTS activity data: {activity}\n\nRisk flags: {risk_facts}",
        }

        messages: List[Dict[str, str]] = [base_system, context_msg]
        messages.extend(history or [])
        messages.append({"role": "user", "content": message})

        completion = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=messages,
            temperature=0.3,
        )

        return completion.choices[0].message.content.strip()

    except Exception as exc:
        return (
            "I ran into an error while trying to answer that question. "
            f"(Internal error: {exc})"
        )


def _fallback_summary(activity: Dict[str, Any], risk_facts: Dict[str, Any], error: str):
    """
    Basic rule-based fallback summary when the API fails.
    """
    lines = []
    lines.append("**Environmental Site Assessment Summary (Fallback)**\n")

    lines.append("**Site Overview**")
    lines.append(f"- Activity: {activity.get('activity_number') or 'Unknown'}")
    lines.append(f"- Status: {activity.get('status') or 'UNKNOWN'}\n")

    lines.append("**Key Contaminants / Concerns**")
    if risk_facts.get("has_pfas"):
        lines.append("- PFAS contamination concern.")
    if risk_facts.get("has_petroleum"):
        lines.append("- Petroleum-related contamination indicated.")
    if risk_facts.get("has_heavy_metals"):
        lines.append("- Heavy metals detected or suspected.")
    if risk_facts.get("offsite_impact_flag"):
        lines.append("- Possible off-site or right-of-way impacts flagged.")
    if risk_facts.get("num_substances") == 0:
        lines.append("- No substances listed.")
    lines.append("")

    lines.append("**Regulatory / Status Notes**")
    lines.append("- Further review of BRRTS ‘Actions and Documents’ recommended.\n")

    lines.append("**Recommended Next Steps**")
    lines.append("- Review supporting reports and DNR documents.")
    lines.append("- Confirm any continuing obligations, use restrictions, or EC/ICs.")
    lines.append("- Evaluate whether further investigation (e.g., Phase II) is needed.\n")

    lines.append(f"*Note: AI call failed – error: {error}*")

    return "\n".join(lines)
