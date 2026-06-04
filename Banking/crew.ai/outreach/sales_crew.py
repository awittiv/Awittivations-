import os
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
CALENDLY_TOKEN = os.environ.get("CALENDLY_API_TOKEN", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "hello@awittivations.com")
CALENDLY_LINK = os.environ.get("CALENDLY_LINK", "https://calendly.com/awittivations/intro")


# ── Tools ────────────────────────────────────────────────────────────────────

@tool("Research lead profile")
def research_lead(linkedin_url: str) -> dict:
    """Fetches public profile and company data for a LinkedIn lead."""
    resp = httpx.get(
        "https://api.linkedin.com/v2/people/(url={linkedin_url})",
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
        "finance": ["AI Credit Scoring", "Bankit Lending Platform", "Harmonic Financial Protocol"],
        "retail": ["Merchant Cash Advance Automation", "Bankit POS Integration"],
        "tech": ["AI Agent Workforce", "Custom CrewAI Pipelines"],
    }
    matched = mapping.get(industry.lower(), ["AI-Powered SME Financial Intelligence"])
    return {"recommended_services": matched, "industry": industry, "role": role}


@tool("Generate 3-touch outreach sequence")
def generate_outreach(name: str, company: str, services: list[str], pain_points: str) -> dict:
    """Produces a personalized 3-touch outreach sequence (connect, follow-up, close)."""
    return {
        "touch_1": (
            f"Hi {name}, loved what {company} is doing in your space. "
            f"We help businesses like yours with {services[0]} — would love to connect."
        ),
        "touch_2": (
            f"Hey {name}, following up — we recently helped a similar company cut loan processing "
            f"time by 60% using {services[0]}. Happy to share how. Worth a quick call?"
        ),
        "touch_3": (
            f"{name}, last note — I put together a short custom scope for {company} around "
            f"{', '.join(services[:2])}. Can I send it over? Takes 10 min to review."
        ),
    }


@tool("Check Calendly availability and book meeting")
def book_meeting(name: str, email: str) -> dict:
    """Returns a personalised Calendly booking link for the lead."""
    return {
        "booking_link": f"{CALENDLY_LINK}?name={name}&email={email}",
        "message": f"Book a 30-min intro call: {CALENDLY_LINK}?name={name}&email={email}",
    }


@tool("Generate custom proposal")
def generate_proposal(company: str, services: list[str], pain_points: str) -> str:
    """Drafts a short custom scope/proposal for the lead."""
    services_list = "\n".join(f"  - {s}" for s in services)
    return f"""
CUSTOM SCOPE — {company}
========================
Prepared by Awittivations LLC

Recommended Services:
{services_list}

Approach:
We will conduct a 2-week discovery sprint to map {company}'s current workflows,
then deploy targeted AI agents to address: {pain_points}.

Timeline: 4–6 weeks | Engagement: Retainer or project-based
Next Step: 30-min intro call → {CALENDLY_LINK}
""".strip()


@tool("Send outreach via email")
def send_email(to_email: str, subject: str, body: str) -> str:
    """Sends an outreach email via SendGrid."""
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


# ── Agents ───────────────────────────────────────────────────────────────────

lead_researcher = Agent(
    role="Lead Research Agent",
    goal="Gather full profile and company data for a newly connected LinkedIn lead.",
    backstory="You are a B2B intelligence specialist who builds rich lead profiles from public data.",
    tools=[research_lead, get_hubspot_contact],
    verbose=True,
)

value_mapper = Agent(
    role="Value Mapping Agent",
    goal="Match Awittivations services to the lead's industry, role, and pain points.",
    backstory="You understand Awittivations' full service suite and know which solutions resonate with which buyers.",
    tools=[map_services],
    verbose=True,
)

outreach_agent = Agent(
    role="Personalized Outreach Agent",
    goal="Create a tailored 3-touch outreach sequence for the lead.",
    backstory="You write concise, human-sounding outreach that gets replies — no generic templates.",
    tools=[generate_outreach],
    verbose=True,
)

scheduler = Agent(
    role="Meeting Scheduler Agent",
    goal="Embed a personalised Calendly link into the outreach to book an intro call.",
    backstory="You make it frictionless for leads to get on a call by pre-filling their details.",
    tools=[book_meeting],
    verbose=True,
)

proposal_agent = Agent(
    role="Proposal Generator Agent",
    goal="Create a concise custom scope document tailored to the lead's company and needs.",
    backstory="You translate discovery insights into compelling, specific proposals.",
    tools=[generate_proposal],
    verbose=True,
)

delivery_agent = Agent(
    role="Delivery Agent",
    goal="Send the first outreach touch and proposal via email.",
    backstory="You handle final delivery across channels, ensuring messages land in the right inbox.",
    tools=[send_email],
    verbose=True,
)


# ── Tasks ────────────────────────────────────────────────────────────────────

research_task = Task(
    description=(
        "Given a LinkedIn URL and email from a newly accepted connection, research the lead's "
        "role, company, industry, company size, and any visible pain points."
    ),
    expected_output="A dict with: name, email, company, industry, role, company_size, pain_points.",
    agent=lead_researcher,
)

value_task = Task(
    description="Using the lead profile, identify the top 2-3 Awittivations services that fit their needs.",
    expected_output="A list of recommended services with a one-line rationale each.",
    agent=value_mapper,
    context=[research_task],
)

outreach_task = Task(
    description="Write a personalized 3-touch outreach sequence (connect note, follow-up, close) for the lead.",
    expected_output="Three distinct message drafts labelled touch_1, touch_2, touch_3.",
    agent=outreach_agent,
    context=[research_task, value_task],
)

scheduling_task = Task(
    description="Generate a personalised Calendly booking link to embed in touch_2 of the outreach sequence.",
    expected_output="A booking URL pre-filled with the lead's name and email.",
    agent=scheduler,
    context=[research_task],
)

proposal_task = Task(
    description="Draft a short custom scope document for the lead based on their profile and matched services.",
    expected_output="A plain-text proposal document ready to attach or paste.",
    agent=proposal_agent,
    context=[research_task, value_task],
)

delivery_task = Task(
    description=(
        "Send touch_1 of the outreach sequence to the lead's email. "
        "Attach or reference the proposal in touch_3 when the time comes."
    ),
    expected_output="Confirmation that touch_1 email was delivered successfully.",
    agent=delivery_agent,
    context=[outreach_task, scheduling_task, proposal_task],
)


# ── Crew ─────────────────────────────────────────────────────────────────────

sales_crew = Crew(
    agents=[lead_researcher, value_mapper, outreach_agent, scheduler, proposal_agent, delivery_agent],
    tasks=[research_task, value_task, outreach_task, scheduling_task, proposal_task, delivery_task],
    process=Process.sequential,
    verbose=True,
)

if __name__ == "__main__":
    result = sales_crew.kickoff(inputs={
        "linkedin_url": os.environ.get("LEAD_LINKEDIN_URL", ""),
        "email": os.environ.get("LEAD_EMAIL", ""),
    })
    print(result)
