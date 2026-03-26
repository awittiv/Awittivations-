# Bankit CrewAI & HubSpot Integration

This directory contains the integration of the **Bankit** agent with **CrewAI**, **HubSpot**, and a **PostgreSQL** database for auditing and compliance (Visa Agentic Ready Spec & Michigan 2026-03-BT "Safe Harbor" Edition).

## Components

1. **`schema.sql`**: The PostgreSQL schema definitions for `agentic_identities` and `ais_program_audit`. This includes the mandatory `fairness_score` and `validation_hash` fields.
2. **`bankit_crew.py`**: The main Python script that:
   - Initializes a CrewAI agent for Bankit using Anthropic's Claude model.
   - Executes financial queries while adhering to the GENIUS Act.
   - Logs the interaction to the PostgreSQL database (`ais_program_audit`).
   - Syncs the interaction to HubSpot CRM as a contact property update.

## Setup Instructions

### 1. Database Setup
Ensure you have a PostgreSQL database running. Run the schema file to create the necessary tables:
```bash
psql -U postgres -d awittivations -f schema.sql
```

### 2. Environment Variables
Update your `.env` file in the root of the `Awittivations` project with the following variables:
```env
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=awittivations
DB_USER=postgres
DB_PASSWORD=postgres

# HubSpot
HUBSPOT_ACCESS_TOKEN=your_hubspot_pat

# Anthropic (already required by orchestrator)
ANTHROPIC_API_KEY=your_anthropic_key
```

### 3. Dependencies
Ensure you have the required Python packages installed:
```bash
pip install crewai langchain-anthropic psycopg2-binary python-dotenv requests
```

### 4. Running the Agent
You can test the standalone CrewAI agent by running:
```bash
python bankit_crew.py
```

## Integration with Orchestrator
To fully integrate this into the `orchestrater` FastAPI app, you would import `run_bankit_crew` from `bankit_crew.py` and call it within the `/orchestrate` endpoint when the `AgentType` is `BANKIT`.
