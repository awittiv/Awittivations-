import os
from crewai import Agent, Task, Crew, Process
from crewai_tools import tool
import httpx

HUBSPOT_TOKEN = os.environ["HUBSPOT_API_TOKEN"]
BANKIT_API_URL = os.environ.get("BANKIT_API_URL", "http://localhost:8000")

HUBSPOT_HEADERS = {
    "Authorization": f"Bearer {HUBSPOT_TOKEN}",
    "Content-Type": "application/json",
}


@tool("Fetch pending loan applications")
def fetch_pending_loans() -> list[dict]:
    """Fetches all pending loan applications from the Bankit API."""
    resp = httpx.get(f"{BANKIT_API_URL}/loans", params={"status": "pending"})
    resp.raise_for_status()
    return resp.json()


@tool("Fetch merchant details")
def fetch_merchant(merchant_id: str) -> dict:
    """Fetches merchant profile by ID from the Bankit API."""
    resp = httpx.get(f"{BANKIT_API_URL}/merchants/{merchant_id}")
    resp.raise_for_status()
    return resp.json()


@tool("Create or update HubSpot contact")
def upsert_hubspot_contact(email: str, phone: str, business_name: str, trust_score: int) -> str:
    """Creates or updates a HubSpot contact for a bankit merchant."""
    payload = {
        "properties": {
            "email": email,
            "phone": phone,
            "company": business_name,
            "bankit_trust_score": str(trust_score),
        }
    }
    resp = httpx.post(
        "https://api.hubapi.com/crm/v3/objects/contacts",
        headers=HUBSPOT_HEADERS,
        json=payload,
    )
    if resp.status_code == 409:
        contact_id = resp.json()["message"].split(":")[1].strip()
        httpx.patch(
            f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}",
            headers=HUBSPOT_HEADERS,
            json=payload,
        )
        return f"Updated contact {contact_id}"
    resp.raise_for_status()
    return f"Created contact {resp.json()['id']}"


@tool("Create HubSpot deal for loan")
def create_hubspot_deal(contact_id: str, loan_id: str, amount_inr: float, purpose: str) -> str:
    """Creates a HubSpot deal linked to a bankit loan application."""
    payload = {
        "properties": {
            "dealname": f"Loan #{loan_id} — {purpose}",
            "amount": str(amount_inr),
            "pipeline": "default",
            "dealstage": "appointmentscheduled",
            "bankit_loan_id": loan_id,
        },
        "associations": [
            {
                "to": {"id": contact_id},
                "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}],
            }
        ],
    }
    resp = httpx.post(
        "https://api.hubapi.com/crm/v3/objects/deals",
        headers=HUBSPOT_HEADERS,
        json=payload,
    )
    resp.raise_for_status()
    return f"Created deal {resp.json()['id']}"


# --- Agents ---

loan_syncer = Agent(
    role="Loan Sync Specialist",
    goal="Fetch pending bankit loan applications and sync merchants to HubSpot as contacts.",
    backstory="You connect bankit's lending pipeline to HubSpot CRM so the sales team has full visibility.",
    tools=[fetch_pending_loans, fetch_merchant, upsert_hubspot_contact],
    verbose=True,
)

deal_creator = Agent(
    role="Deal Pipeline Manager",
    goal="Create HubSpot deals for every synced loan application.",
    backstory="You turn bankit loan requests into trackable HubSpot deals with accurate amounts and stages.",
    tools=[create_hubspot_deal],
    verbose=True,
)

# --- Tasks ---

sync_contacts_task = Task(
    description=(
        "Fetch all pending loan applications from Bankit. For each loan, fetch the merchant profile "
        "and upsert them as a HubSpot contact including their trust score."
    ),
    expected_output="A list of HubSpot contact IDs created or updated, one per merchant.",
    agent=loan_syncer,
)

create_deals_task = Task(
    description=(
        "For each contact synced in the previous task, create a HubSpot deal linked to their loan "
        "application with the correct amount (INR) and purpose."
    ),
    expected_output="A list of HubSpot deal IDs created, one per loan application.",
    agent=deal_creator,
    context=[sync_contacts_task],
)

# --- Crew ---

bankit_crew = Crew(
    agents=[loan_syncer, deal_creator],
    tasks=[sync_contacts_task, create_deals_task],
    process=Process.sequential,
    verbose=True,
)

if __name__ == "__main__":
    result = bankit_crew.kickoff()
    print(result)
