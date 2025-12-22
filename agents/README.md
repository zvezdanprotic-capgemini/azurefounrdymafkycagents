# MAF Agents - Modular Structure

This directory contains the refactored MAF agents, organized for better maintainability and clarity.

## Structure

```
agents/
├── __init__.py              # Agent registry and exports
├── utils.py                 # Shared utilities
├── intake_agent.py          # Intake agent
├── verification_agent.py    # Verification agent
├── eligibility_agent.py     # Eligibility agent
├── recommendation_agent.py  # Recommendation agent
├── compliance_agent.py      # Compliance agent
├── action_agent.py          # Action agent
└── prompts/                 # Agent prompts
    ├── intake_prompt.txt
    ├── verification_prompt.txt
    ├── eligibility_prompt.txt
    ├── recommendation_prompt.txt
    ├── compliance_prompt.txt
    └── action_prompt.txt
```

## Agents

### 1. Intake Agent
- **Purpose**: Collects initial customer information
- **Required Fields**: name, email, phone, address
- **Tools**: `get_customer_by_email`, `get_customer_history`
- **File**: [intake_agent.py](intake_agent.py)
- **Prompt**: [prompts/intake_prompt.txt](prompts/intake_prompt.txt)

### 2. Verification Agent
- **Purpose**: Verifies customer identity and documents
- **Required Fields**: document_type, document_number, document_expiry
- **Tools**: `list_customer_documents`, `get_document_url`
- **File**: [verification_agent.py](verification_agent.py)
- **Prompt**: [prompts/verification_prompt.txt](prompts/verification_prompt.txt)

### 3. Eligibility Agent
- **Purpose**: Determines customer eligibility for services
- **Requirements**: Age >= 18, valid location, completed intake/verification
- **Tools**: `get_customer_history`, `search_policies`
- **File**: [eligibility_agent.py](eligibility_agent.py)
- **Prompt**: [prompts/eligibility_prompt.txt](prompts/eligibility_prompt.txt)

### 4. Recommendation Agent
- **Purpose**: Provides product/service recommendations
- **Considers**: Customer profile, preferences, insurance needs
- **Tools**: `get_customer_history`, `search_policies`
- **File**: [recommendation_agent.py](recommendation_agent.py)
- **Prompt**: [prompts/recommendation_prompt.txt](prompts/recommendation_prompt.txt)

### 5. Compliance Agent
- **Purpose**: Performs final compliance checks
- **Required Fields**: source_of_funds, employment_status, pep_status
- **Checks**: Sanctions screening, AML verification
- **Tools**: `search_policies`, `check_compliance`, `get_policy_requirements`
- **File**: [compliance_agent.py](compliance_agent.py)
- **Prompt**: [prompts/compliance_prompt.txt](prompts/compliance_prompt.txt)

### 6. Action Agent
- **Purpose**: Takes final actions based on workflow results
- **Actions**: Account creation, confirmation emails, document archival
- **Tools**: `send_kyc_approved_email`, `send_kyc_pending_email`, `save_kyc_session_state`
- **File**: [action_agent.py](action_agent.py)
- **Prompt**: [prompts/action_prompt.txt](prompts/action_prompt.txt)

## Usage

Import agents from the package:

```python
from agents import AGENT_FACTORIES, WORKFLOW_STEPS

# Get agent factory
intake_factory = AGENT_FACTORIES["intake"]

# Create agent instance
intake_agent = intake_factory()
```

## Agent Factory Pattern

Each agent follows the same pattern:

```python
class AgentName:
    @staticmethod
    def create() -> ChatAgent:
        chat_client = create_azure_chat_client()
        instructions = load_prompt("agent_name")
        
        return chat_client.create_agent(
            name="agent_name",
            description="Agent description",
            instructions=instructions,
        )
```

## Workflow Integration

The workflow uses the AGENT_FACTORIES registry:

```python
from agents import AGENT_FACTORIES, WORKFLOW_STEPS

# In maf_workflow_hitl.py
for step_name in WORKFLOW_STEPS:
    factory = AGENT_FACTORIES[step_name]
    agent = factory()
    # ... use agent in workflow
```

## Benefits of Modular Structure

1. **Separation of Concerns**: Each agent in its own file
2. **Easy Maintenance**: Changes to one agent don't affect others
3. **Clear Organization**: Prompts separated from code logic
4. **Better Testing**: Individual agents can be unit tested
5. **Reduced Complexity**: Smaller, focused files vs monolithic file
6. **Prompt Management**: Easy to update agent instructions without touching code

## Migration from maf_agents_simple.py

The old monolithic `maf_agents_simple.py` has been moved to `backup_workflows/`. The new structure maintains the same API:

- `AGENT_FACTORIES` dictionary with agent factory functions
- `WORKFLOW_STEPS` list defining agent execution order
- Each factory returns a `ChatAgent` instance

No changes required to `maf_workflow_hitl.py` except updating the import from:
```python
from maf_agents_simple import AGENT_FACTORIES, WORKFLOW_STEPS
```
to:
```python
from agents import AGENT_FACTORIES, WORKFLOW_STEPS
```
