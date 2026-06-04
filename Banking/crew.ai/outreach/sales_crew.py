import os
import asyncio
from datetime import datetime, timedelta
from crewai import Agent, Task, Crew, Process
from crewai_tools import tool
import httpx

HUBSPOT_TOKEN = os.environ["HUBSPOT_API_TOKEN"]
HUBSPOT_HEADERS = {
    "Authorization": f"Bearer {HUBSPOT_TOKEN}",
    "Content-Type": "application/json",
}

SENDGRID_KEY = os.environ["SENDGRID_API_KEY"]
LINKEDIN_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "hello@awittivations.com")
CALENDLY_LINK = os.environ.get("CALENDLY_LINK", "https://calendly.com/awittivations/intro")

TOUCH_DELAYS_DAYS = {"touch_1": 0, "touch_2": 3, "touch_3": 7}


# ── Tools ────────────────────────────────────────────────────────────────────

@tool("Research lead profile")
def research_lead(linkedin_url: str) -> dict:
    """Fetches profile and company data for a LinkedIn lead."""
    resp = httpx.get(
        f"https://api.linkedin.com/v2/people/(url={linkedin_url})",
        headers={"Authorization": f"Bearer {LINKEDIN_TOKEN}"},
    )
    if resp.status_code != 200:
        return {"error": resp.text, "linkedin_url": linkedin_url}
    return resp.json()


@tool("Look up HubSpot contact")
def get_hubspot_contact(email: str) -> dict:
    """Retrieves an existing HubSpot contact by email."""
    resp = httpx.get(
        f"https://api.hubapi.com/crm/v3/objects/contacts/{email}",
        headers=HUBSPOT_HEADERS,
        params={"idProperty": "email"},
    )
    return resp.json() if resp.status_code == 200 else {}


@tool("Map services to lead needs")
def map_services(industry: str, role: str, company_size: str) -> dict:
    """Returns Awittivations service recommendations based on lead profile."""
    mapping = {
        "finance": ["AI Credit Scoring API", "Bankit Lending Platform", "Harmonic Financial Protocol"],
        "nbfc":    ["AI Credit Scoring API", "WhatsApp Loan Intake Automation", "Bankit Risk Dashboard"],
        "retail":  ["Merchant Cash Advance Automation", "Bankit POS Integration"],
        "tech":    ["AI Agent Workforce", "Custom CrewAI Pipelines"],
    }
    matched = mapping.get(industry.lower(), ["AI-Powered SME Financial Intelligence"])
    return {"recommended_services": matched, "industry": industry, "role": role}


@tool("Generate 3-touch outreach sequence")
def generate_outreach(name: str, company: str, services: list[str], booking_link: str) -> dict:
    """Produces a personalized 3-touch outreach sequence with scheduled send dates."""
    now = datetime.utcnow()
    return {
        "touch_1": {
            "channel": "linkedin",
            "send_at": now.isoformat(),
            "subject": None,
            "body": (
                f"Hi {name}, great to connect! I noticed {company} is active in financial services — "
                f"we've been helping NBFCs cut loan processing time by 60% with {services[0]}. "
                f"Would love to share what we've built. Open to a quick chat?"
            ),
        },
        "touch_2": {
            "channel": "email",
            "send_at": (now + timedelta(days=TOUCH_DELAYS_DAYS["touch_2"])).isoformat(),
            "subject": f"Quick follow-up — {services[0]} for {company}",
            "body": (
                f"Hi {name},\n\nFollowing up on my LinkedIn note. "
                f"We recently deployed {services[0]} for a mid-size NBFC in India — "
                f"reduced manual underwriting by 80%.\n\n"
                f"Here's a 30-min slot to see a live demo: {booking_link}\n\n"
                f"Worth 30 minutes?\n\nBest,\nAwittivations"
            ),
        },
        "touch_3": {
            "channel": "email",
            "send_at": (now + timedelta(days=TOUCH_DELAYS_DAYS["touch_3"])).isoformat(),
            "subject": f"Custom scope for {company} — take 2 mins to review",
            "body": (
                f"Hi {name},\n\nLast note — I've put together a short custom scope for {company} "
                f"covering {' and '.join(services[:2])}.\n\n"
                f"[Proposal attached]\n\n"
                f"Happy to walk through it: {booking_link}\n\nBest,\nAwittivations"
            ),
        },
    }


@tool("Generate personalised Calendly booking link")
def book_meeting(name: str, email: str) -> str:
    """Returns a pre-filled Calendly URL for the lead."""
    return f"{CALENDLY_LINK}?name={name}&email={email}"


@tool("Generate custom proposal")
def generate_proposal(company: str, services: list[str], pain_points: str) -> str:
    """Drafts a short custom scope document for the lead."""
    services_list = "\n".join(f"  • {s}" for s in services)
    return f"""CUSTOM SCOPE — {company}
Prepared by Awittivations LLC
==============================
Recommended Services:
{services_list}

Approach:
2-week discovery sprint to map {company}'s current workflows,
followed by targeted AI agent deployment to address: {pain_points}.

Timeline  : 4–6 weeks
Engagement: Retainer or project-based
Next Step : {CALENDLY_LINK}
""".strip()


@tool("Send LinkedIn direct message")
def send_linkedin_dm(recipient_linkedin_id: str, message: str) -> str:
    """Sends a direct message to a LinkedIn member via the Messaging API."""
    payload = {
        "recipients": [{"person": {"~urn": f"urn:li:person:{recipient_linkedin_id}"}}],
        "subject": "",
        "body": message,
        "messageType": "MEMBER_TO_MEMBER",
    }
    resp = httpx.post(
        "https://api.linkedin.com/v2/messages",
        headers={"Authorization": f"Bearer {LINKEDIN_TOKEN}", "Content-Type": "application/json"},
        json=payload,
    )
    return "sent" if resp.status_code in (200, 201) else f"error: {resp.text}"


@tool("Send email via SendGrid")
def send_email(to_email: str, subject: str, body: str) -> str:
    """Sends an email via SendGrid."""
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": SENDER_EMAIL},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }
    resp = httpx.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {SENDGRID_KEY}", "Content-Type": "application/json"},
        json=payload,
    )
    return "sent" if resp.status_code == 202 else f"error: {resp.text}"


@tool("Schedule future outreach touches")
def schedule_touches(touches: dict, email: str, linkedin_id: str) -> dict:
    """Queues touch_2 and touch_3 for future delivery by storing them in HubSpot as tasks."""
    results = {}
    for touch_key in ("touch_2", "touch_3"):
        touch = touches.get(touch_key, {})
        payload = {
            "properties": {
                "hs_task_subject": touch.get("subject", f"Outreach {touch_key}"),
                "hs_task_body": touch.get("body", ""),
                "hs_task_status": "NOT_STARTED",
                "hs_timestamp": touch.get("send_at", ""),
            }
        }
        resp = httpx.post(
            "https://api.hubapi.com/crm/v3/objects/tasks",
            headers=HUBSPOT_HEADERS,
            json=payload,
        )
        results[touch_key] = "scheduled" if resp.status_code in (200, 201) else f"error: {resp.text}"
    return results


# ── Agents ───────────────────────────────────────────────────────────────────

lead_researcher = Agent(
    role="Lead Research Agent",
    goal="Build a complete profile of the newly connected LinkedIn lead.",
    backstory="You are a B2B intelligence specialist. You gather name, role, company, industry, and infer pain points.",
    tools=[research_lead, get_hubspot_contact],
    verbose=True,
)

value_mapper = Agent(
    role="Value Mapping Agent",
    goal="Identify the top 2-3 Awittivations services that match this lead's needs.",
    backstory="You know Awittivations' full service suite and map it precisely to NBFC and fintech buyer pain points.",
    tools=[map_services],
    verbose=True,
)

outreach_agent = Agent(
    role="Personalized Outreach Agent",
    goal="Write a 3-touch sequence: Touch 1 (LinkedIn DM now), Touch 2 (email day 3), Touch 3 (email + proposal day 7).",
    backstory="You write concise, human outreach that gets replies. No generic templates.",
    tools=[generate_outreach, book_meeting],
    verbose=True,
)

scheduler = Agent(
    role="Meeting Scheduler Agent",
    goal="Embed a pre-filled Calendly link in Touch 2 and Touch 3.",
    backstory="You reduce friction by pre-filling booking links with the lead's name and email.",
    tools=[book_meeting],
    verbose=True,
)

proposal_agent = Agent(
    role="Proposal Generator Agent",
    goal="Draft a concise custom scope document to attach to Touch 3.",
    backstory="You translate service matches into compelling, specific proposals that close deals.",
    tools=[generate_proposal],
    verbose=True,
)

delivery_agent = Agent(
    role="Delivery Agent",
    goal=(
        "Send Touch 1 via LinkedIn DM immediately. "
        "Send Touch 2 via email on day 3. "
        "Send Touch 3 via email with proposal on day 7. "
        "Schedule future touches in HubSpot."
    ),
    backstory="You handle multi-channel delivery across LinkedIn and email, and queue follow-ups in HubSpot.",
    tools=[send_linkedin_dm, send_email, schedule_touches],
    verbose=True,
)


# ── Tasks ────────────────────────────────────────────────────────────────────

research_task = Task(
    description=(
        "Research the lead from their LinkedIn URL and email. "
        "Return: name, email, linkedin_id, company, industry, role, company_size, pain_points."
    ),
    expected_output="A dict with the lead's full profile.",
    agent=lead_researcher,
)

value_task = Task(
    description="Map the lead's industry and role to the top 2-3 Awittivations services.",
    expected_output="List of recommended services with one-line rationale each.",
    agent=value_mapper,
    context=[research_task],
)

scheduling_task = Task(
    description="Generate a pre-filled Calendly booking link using the lead's name and email.",
    expected_output="A booking URL string.",
    agent=scheduler,
    context=[research_task],
)

outreach_task = Task(
    description=(
        "Write all 3 touches using the lead profile, matched services, and booking link. "
        "Touch 1: LinkedIn DM (send now). Touch 2: email (day 3). Touch 3: email + proposal (day 7)."
    ),
    expected_output="Dict with touch_1, touch_2, touch_3 — each with channel, send_at, subject, body.",
    agent=outreach_agent,
    context=[research_task, value_task, scheduling_task],
)

proposal_task = Task(
    description="Write a short custom scope document for the lead based on their profile and matched services.",
    expected_output="Plain-text proposal ready to paste into Touch 3.",
    agent=proposal_agent,
    context=[research_task, value_task],
)

delivery_task = Task(
    description=(
        "1. Send Touch 1 via LinkedIn DM immediately.\n"
        "2. Send Touch 2 via email (or schedule in HubSpot if not day 3 yet).\n"
        "3. Attach the proposal to Touch 3 and schedule it in HubSpot for day 7.\n"
        "Report delivery status for each touch."
    ),
    expected_output="Delivery status for touch_1, touch_2, touch_3.",
    agent=delivery_agent,
    context=[outreach_task, proposal_task],
)


# ── Crew ─────────────────────────────────────────────────────────────────────

sales_crew = Crew(
    agents=[lead_researcher, value_mapper, scheduler, outreach_agent, proposal_agent, delivery_agent],
    tasks=[research_task, value_task, scheduling_task, outreach_task, proposal_task, delivery_task],
    process=Process.sequential,
    verbose=True,
)

if __name__ == "__main__":
    result = sales_crew.kickoff(inputs={
        "linkedin_url": os.environ.get("LEAD_LINKEDIN_URL", ""),
        "email": os.environ.get("LEAD_EMAIL", ""),
    })
    print(result)
