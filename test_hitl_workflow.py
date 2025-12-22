#!/usr/bin/env python3
"""
Test script to demonstrate human-in-the-loop KYC workflow.

This script simulates the flow where:
1. User starts KYC process
2. Intake agent checks for required data (name, email, phone, address)
3. If missing, agent asks user for it
4. User provides the data
5. Agent proceeds to next step
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_hitl_workflow():
    """Test the human-in-the-loop workflow."""
    print("=" * 80)
    print("Testing Human-in-the-Loop KYC Workflow")
    print("=" * 80)
    
    # Step 1: Start with minimal information
    print("\n1. Starting KYC process with minimal info...")
    response = requests.post(
        f"{BASE_URL}/chat",
        json={"message": "Hi, I want to open an account"},
        headers={"Content-Type": "application/json"}
    )
    
    result = response.json()
    print(f"   Response: {result['response'][:200]}...")
    print(f"   Is data request: {result.get('is_data_request')}")
    print(f"   Current step: {result['current_step']}")
    session_id = result['session_id']
    
    if not result.get('is_data_request'):
        print("   ❌ Expected data request but got normal response")
        return
    
    print("   ✓ Agent asked for missing data")
    
    # Step 2: Provide partial information (only name and email)
    print("\n2. Providing partial information (name and email only)...")
    response = requests.post(
        f"{BASE_URL}/chat",
        json={
            "message": "My name is John Doe and email is john@example.com",
            "session_id": session_id
        },
        headers={"Content-Type": "application/json"}
    )
    
    result = response.json()
    print(f"   Response: {result['response'][:200]}...")
    print(f"   Is data request: {result.get('is_data_request')}")
    print(f"   Current step: {result['current_step']}")
    
    if not result.get('is_data_request'):
        print("   ❌ Expected data request for phone and address")
        return
    
    print("   ✓ Agent asked for remaining data (phone, address)")
    
    # Step 3: Provide remaining information
    print("\n3. Providing remaining information (phone and address)...")
    response = requests.post(
        f"{BASE_URL}/chat",
        json={
            "message": "My phone is 555-1234 and address is 123 Main St, New York, NY",
            "session_id": session_id
        },
        headers={"Content-Type": "application/json"}
    )
    
    result = response.json()
    print(f"   Response: {result['response'][:200]}...")
    print(f"   Is data request: {result.get('is_data_request')}")
    print(f"   Current step: {result['current_step']}")
    print(f"   Customer data: {json.dumps(result.get('customer', {}), indent=2)}")
    
    if result.get('is_data_request'):
        print("   ⚠️  Agent still asking for more data")
    else:
        print("   ✓ Agent has all required data and moved forward")
    
    # Step 4: Check if we moved to verification step
    if result['current_step'] == 'verification':
        print("\n4. Moved to verification step...")
        print("   ✓ Intake complete, verification agent will now ask for documents")
    else:
        print(f"\n4. Still at {result['current_step']} step")
    
    print("\n" + "=" * 80)
    print("Test completed!")
    print("=" * 80)
    
    # Summary
    print("\nSummary:")
    print(f"- Session ID: {session_id}")
    print(f"- Final step: {result['current_step']}")
    print(f"- Customer data collected: {list(result.get('customer', {}).keys())}")


if __name__ == "__main__":
    try:
        test_hitl_workflow()
    except requests.exceptions.ConnectionError:
        print("❌ Error: Could not connect to server. Make sure the server is running on port 8000")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
