#!/usr/bin/env python3
"""
Simple interactive test to demonstrate the working human-in-the-loop pattern.
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def chat(message, session_id=None):
    """Send a chat message and return the response."""
    payload = {"message": message}
    if session_id:
        payload["session_id"] = session_id
    
    response = requests.post(
        f"{BASE_URL}/chat",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    return response.json()

print("=" * 80)
print("KYC Workflow - Human-in-the-Loop Demonstration")
print("=" * 80)

# Step 1: Start workflow
print("\n📋 STEP 1: Starting KYC application")
print("User: 'Hi, I want to open an account'")
result = chat("Hi, I want to open an account")

print(f"\n🤖 Agent ({result['current_step']}): {result['response']}")
print(f"   ℹ️  Is data request: {result['is_data_request']}")
session_id = result['session_id']

# Step 2: Provide name and email
print("\n" + "-" * 80)
print("\n📋 STEP 2: Providing partial information")
print("User: 'My name is John Doe and email is john.doe@example.com'")
result = chat("My name is John Doe and email is john.doe@example.com", session_id)

print(f"\n🤖 Agent ({result['current_step']}): {result['response']}")
print(f"   ℹ️  Is data request: {result['is_data_request']}")

# Step 3: Provide phone and address
print("\n" + "-" * 80)
print("\n📋 STEP 3: Providing remaining information")
print("User: 'Phone: +1-555-1234, Address: 123 Main St, New York, NY 10001, USA'")
result = chat("Phone: +1-555-1234, Address: 123 Main St, New York, NY 10001, USA", session_id)

print(f"\n🤖 Agent ({result['current_step']}): {result['response']}")
print(f"   ℹ️  Is data request: {result['is_data_request']}")

# Step 4: Provide documents
if result['current_step'] == 'verification':
    print("\n" + "-" * 80)
    print("\n📋 STEP 4: Providing identity documents")
    print("User: 'Passport number: P123456789, expires 2030-12-31'")
    result = chat("Passport number: P123456789, expires 2030-12-31", session_id)
    
    print(f"\n🤖 Agent ({result['current_step']}): {result['response']}")
    print(f"   ℹ️  Is data request: {result['is_data_request']}")

print("\n" + "=" * 80)
print("✅ Demo Complete!")
print("=" * 80)
print(f"\nFinal state:")
print(f"  - Session ID: {session_id}")
print(f"  - Current step: {result['current_step']}")
print(f"  - Status: {result['status']}")
print(f"\n💡 Key observations:")
print("  1. Agents check for required data before proceeding")
print("  2. When data is missing, agents ask specific questions")
print("  3. When data is complete, agents advance to the next step")
print("  4. The workflow maintains state across multiple requests")
print("\n✨ This is true human-in-the-loop - agents pause and wait for user input!")
