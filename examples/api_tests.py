import requests
import json

# Configuration
BASE_URL = 'http://localhost:5000/api/v1'
API_KEY = 'YOUR_API_KEY'  # Replace with your actual API key

def test_api_endpoint(method, endpoint, data=None):
    """Helper function to make API requests"""
    headers = {'X-API-Key': API_KEY}
    url = f"{BASE_URL}/{endpoint}"
    
    if method == 'GET':
        response = requests.get(url, headers=headers)
    elif method == 'POST':
        response = requests.post(url, headers=headers, json=data)
    
    print(f"\n=== Testing {method} {endpoint} ===")
    print(f"Status Code: {response.status_code}")
    print("Response:")
    print(json.dumps(response.json(), indent=2))
    return response

def test_profile():
    """Test fetching user profile"""
    return test_api_endpoint('GET', 'profile')

def test_create_referral():
    """Test creating a new referral"""
    data = {
        "name": "John",
        "surname": "Doe",
        "email": "john.doe@example.com",
        "phone": "1234567890",
        "treatment_id": 1  # Replace with an actual treatment ID
    }
    return test_api_endpoint('POST', 'referrals', data)

def test_get_referrals():
    """Test fetching referral list"""
    return test_api_endpoint('GET', 'referrals')

def test_get_treatments():
    """Test fetching available treatments"""
    return test_api_endpoint('GET', 'treatments')

def test_get_stats():
    """Test fetching affiliate statistics"""
    return test_api_endpoint('GET', 'stats')

def run_all_tests():
    """Run all API tests"""
    print("Running API Tests...")
    print("\nNote: Make sure to replace 'YOUR_API_KEY' with an actual API key")
    print("and ensure the server is running at", BASE_URL)
    
    try:
        # Test profile endpoint
        test_profile()
        
        # Test treatments endpoint
        test_get_treatments()
        
        # Test referral creation and listing
        test_create_referral()
        test_get_referrals()
        
        # Test statistics
        test_get_stats()
        
    except requests.exceptions.ConnectionError:
        print("\nError: Could not connect to the server.")
        print("Make sure the server is running and the BASE_URL is correct.")
    except Exception as e:
        print("\nError occurred during testing:", str(e))

if __name__ == '__main__':
    run_all_tests()
