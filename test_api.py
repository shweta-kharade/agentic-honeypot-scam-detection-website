import requests
import json

BASE_URL = "http://localhost:8000"
API_KEY = "hackathon-submission-2026"

def test_api():
    print(" Testing Agentic Honey-Pot API")
    print("="*50)
    
    # Test 1: Health check (no API key needed)
    print("\n1. Testing Health Check...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f" Health: {response.json()}")
    except:
        print(" Cannot connect to API")
        return
    
    # Test 2: Home page
    print("\n2. Testing Home Page...")
    response = requests.get(f"{BASE_URL}/")
    print(f" Home: {response.json()}")
    
    # Test 3: Process message WITHOUT API key (should fail)
    print("\n3. Testing WITHOUT API Key (should fail)...")
    response = requests.post(
        f"{BASE_URL}/api/v1/process",
        json={
            "message_text": "Test scam message",
            "conversation_id": "test1"
        }
    )
    if response.status_code == 403:
        print(" Correctly rejected without API key")
    else:
        print(f" Unexpected: {response.status_code}")
    
    # Test 4: Process message WITH API key (should work)
    print("\n4. Testing WITH API Key...")
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    test_messages = [
        "URGENT: Send ₹1000 to claimprize@ybl to claim ₹50,00,000 lottery",
        "Your bank account is locked. Click http://fake-bank.com/login",
        "Hi, how are you doing today?",
        "Call 9876543210 to claim your prize money",
    ]
    
    for i, message in enumerate(test_messages):
        print(f"\n   Message {i+1}: {message[:50]}...")
        response = requests.post(
            f"{BASE_URL}/api/v1/process",
            headers=headers,
            json={
                "message_text": message,
                "conversation_id": f"conv_{i}"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"    Scam detected: {data['scam_detected']}")
            print(f"    Intelligence extracted: {len(data['extracted_data']['upi_ids'])} UPI IDs, {len(data['extracted_data']['urls'])} URLs")
        else:
            print(f"    Error: {response.status_code}")
    
    # Test 5: Get statistics
    print("\n5. Getting Statistics...")
    response = requests.get(
        f"{BASE_URL}/api/v1/stats",
        headers=headers
    )
    if response.status_code == 200:
        print(f" Stats: {json.dumps(response.json(), indent=2)}")
    else:
        print(f" Error: {response.status_code}")
    
    print("\n" + "="*50)
    print(" All tests completed!")
    print(f"\n Open in browser: {BASE_URL}/docs")
    print(f" API Key: {API_KEY}")

if __name__ == "__main__":
    test_api()