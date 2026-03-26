import os
import json
import hashlib
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from crewai import Agent, Task, Crew, Process
from langchain_anthropic import ChatAnthropic
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

# Database connection
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "awittivations"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        port=os.getenv("DB_PORT", "5432")
    )

# HubSpot Integration
def log_to_hubspot(contact_email, action_taken, fairness_score):
    hubspot_token = os.getenv("HUBSPOT_ACCESS_TOKEN")
    if not hubspot_token:
        print("Warning: HUBSPOT_ACCESS_TOKEN not set. Skipping HubSpot logging.")
        return

    url = "https://api.hubapi.com/crm/v3/objects/contacts"
    headers = {
        "Authorization": f"Bearer {hubspot_token}",
        "Content-Type": "application/json"
    }
    
    # Simple example: Create or update a contact with the action taken
    data = {
        "properties": {
            "email": contact_email,
            "last_agent_action": action_taken,
            "fairness_score": str(fairness_score)
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code in (200, 201):
            print(f"Successfully logged to HubSpot for {contact_email}")
        else:
            print(f"HubSpot API Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Failed to connect to HubSpot: {e}")

# Database Logging
def log_audit(agent_name, action_taken, fairness_score, model_version="Bankit-v9.0"):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 1. Get or create Agent ID
        # Calculate a dummy logic hash for demonstration
        logic_hash = hashlib.sha256(open(__file__, "rb").read()).hexdigest()
        
        cur.execute(
            "SELECT id FROM agentic_identities WHERE agent_name = %s", 
            (agent_name,)
        )
        agent_record = cur.fetchone()
        
        if not agent_record:
            cur.execute(
                """
                INSERT INTO agentic_identities (agent_name, visa_agent_token, logic_hash)
                VALUES (%s, %s, %s) RETURNING id
                """,
                (agent_name, "visa_token_placeholder", logic_hash)
            )
            agent_id = cur.fetchone()['id']
        else:
            agent_id = agent_record['id']
            
        # 2. Insert Audit Record
        validation_hash = hashlib.sha256(action_taken.encode()).hexdigest()
        
        cur.execute(
            """
            INSERT INTO ais_program_audit 
            (agent_id, action_taken, fairness_score, validation_hash, model_version)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (agent_id, action_taken, fairness_score, validation_hash, model_version)
        )
        
        conn.commit()
        cur.close()
        conn.close()
        print("Successfully logged audit to database.")
    except Exception as e:
        print(f"Database logging failed: {e}")

# CrewAI Setup
def run_bankit_crew(user_query: str, user_email: str = "user@example.com"):
    # Initialize the LLM
    llm = ChatAnthropic(
        model_name=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY")
    )

    # Define the Bankit Agent
    bankit_agent = Agent(
        role='Bankit Financial Agent',
        goal='Provide compliant, clear, and actionable financial guidance regarding crypto, RWA, and stablecoins.',
        backstory='You are Bankit, an AI agent operating under Awittivations LLC. You strictly adhere to the GENIUS Act and ensure all advice is fair and unbiased.',
        verbose=True,
        allow_delegation=False,
        llm=llm
    )

    # Define the Task
    financial_task = Task(
        description=f'Analyze the following user query and provide a compliant response: "{user_query}"',
        expected_output='A clear, jargon-free financial response suitable for underserved entrepreneurs.',
        agent=bankit_agent
    )

    # Create the Crew
    bankit_crew = Crew(
        agents=[bankit_agent],
        tasks=[financial_task],
        process=Process.sequential
    )

    # Execute the Crew
    print("Starting Bankit Crew execution...")
    result = bankit_crew.kickoff()
    
    # Post-processing: Calculate a dummy fairness score (in reality, this would be an ML model)
    fairness_score = 0.95 
    
    # Log to Database
    log_audit(
        agent_name="Bankit-Alpha-01",
        action_taken=f"Processed query: {user_query[:50]}...",
        fairness_score=fairness_score
    )
    
    # Log to HubSpot
    log_to_hubspot(
        contact_email=user_email,
        action_taken=f"Bankit Query: {user_query[:50]}...",
        fairness_score=fairness_score
    )
    
    return result

if __name__ == "__main__":
    # Example usage
    sample_query = "How do I bridge USDC to Polygon for my small business?"
    print(f"Running query: {sample_query}")
    response = run_bankit_crew(sample_query)
    print("\nFinal Response:")
    print(response)
