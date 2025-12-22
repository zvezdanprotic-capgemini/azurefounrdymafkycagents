#!/usr/bin/env python3
"""
Verify customer data extraction works correctly.
"""
import requests
import json

BASE_URL = "http://localhost:8000"

print("=" * 80)
print("Testing Customer Data Extraction")
print("=" * 80)

# Start workflow
print("\n1. Starting workflow...")
r1 = requests.post(f"{BASE_URL}/chat", json={"message": "I want to open an account"})
result = r1.json()
session_id = result['session_id']
print(f"   Session ID: {session_id}")
print(f"   Customer data: {result['customer']}")
assert result['customer'] == {}, "Initial customer data should be empty"
print("   ✓ Initial state correct")

# Provide full data at once
print("\n2. Providing all required data...")
r2 = requests.post(
    f"{BASE_URL}/chat", 
    json={
        "message": "Name: Alice Smith, Email: alice@example.com, Phone: +1-555-9876, Address: 456 Oak Ave, Boston, MA",
        "session_id": session_id
    }
)
result = r2.json()
print(f"   Response: {result['response'][:100]}...")
print(f"   Current step: {result['current_step']}")
print(f"   Customer data: {json.dumps(result['customer'], indent=2)}")

# Verify customer data was extracted
if result['customer']:
    print("   ✓ Customer data extracted!")
    expected_fields = ['name', 'email', 'phone', 'address']
    found_fields = [f for f in expected_fields if f in result['customer']]
    print(f"   ✓ Found fields: {found_fields}")
    
    if len(found_fields) == len(expected_fields):
        print("   ✅ All fields collected successfully!")
    else:
        print(f"   ⚠️  Missing fields: {set(expected_fields) - set(found_fields)}")
else:
    print("   ❌ No customer data found")

print("\n" + "=" * 80)
print("Test Complete!")
print("=" * 80)
