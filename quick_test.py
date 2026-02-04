import requests
import time

def wait_for_server(url, max_attempts=10):
    """Wait for server to start"""
    for i in range(max_attempts):
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                print(f" Server is running at {url}")
                return True
        except:
            print(f" Waiting for server... ({i+1}/{max_attempts})")
            time.sleep(1)
    return False

def test_api():
    base_url = "http://localhost:8000"
    api_key = "hackathon-submission-2026"
    
    print("🧪 Testing Agentic Honey-Pot API")
    print("="*60)
    
    # Wait for server
    if not wait_for_server(f"{base_url}/health"):
        print("Server not starting. Please check:")
        print("  1. Run: python simple_honeypot.py")
        print("  2. Check if port 8000 is free")
        return
    
    # Test 1: Health check
    print("\n1. Testing health check...")
    try:
        response = requests.get(f"{base_url}/health")
        print(f"  Health: {response.json()}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 2: Home page
    print("\n2. Testing home page...")
    try:
        response = requests.get(base_url)
        print(f"   Home: Status {response.status_code}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 3: Process message
    print("\n3. Processing scam message...")
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    
    test_messages = [
        "URGENT: Send ₹1000 to claimprize@ybl to claim lottery",
        "Your bank account is locked. Click http://fake-bank.com",
        "Hi, how are you?"
    ]
    
    for i, message in enumerate(test_messages):
        data = {
            "message_text": message,
            "conversation_id": f"test_{i}"
        }
        
        try:
            response = requests.post(
                f"{base_url}/api/v1/process",
                headers=headers,
                json=data
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"\n   Message: {message[:30]}...")
                print(f"   Scam detected: {result['scam_detected']}")
                print(f"   Confidence: {result['confidence']:.2f}")
                print(f"   Response: {result['response_text']}")
            else:
                print(f"   Error: Status {response.status_code}")
                print(f"   Response: {response.text}")
                
        except Exception as e:
            print(f"   Exception: {e}")
    
    print("\n" + "="*60)
    print(" Tests completed!")
    print(f"\n Open in browser: {base_url}/docs")

if __name__ == "__main__":
    test_api()