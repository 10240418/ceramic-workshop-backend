import requests
import datetime
import urllib.parse

BASE_URL = "http://localhost:8080"
DEVICE_ID = "short_hopper_1"

def test_delete_api():
    print(f"Testing DELETE API on {BASE_URL}...")
    
    # 1. 构造一个测试时间 (昨天这个时候)
    # 注意：这个时间点不一定有数据，但我们只是测 API 是否存在 (405 vs 200/404)
    test_time = datetime.datetime.now() - datetime.timedelta(days=1)
    time_str = test_time.astimezone().isoformat()
    
    encoded_time = urllib.parse.quote(time_str)
    
    url = f"{BASE_URL}/api/hopper/{DEVICE_ID}/feeding-history?time={encoded_time}"
    print(f"Request URL: {url}")
    
    try:
        response = requests.delete(url)
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
        
        if response.status_code == 405:
            print("\n❌ FAILED: 405 Method Not Allowed")
            print("Reason: The backend server running on port 8080 does NOT support DELETE method for this path.")
            print("Solution: Please restart the backend container with the latest code.")
        elif response.status_code == 200:
            print("\n✅ SUCCESS: API call succeeded.")
        else:
            print(f"\n⚠️ Result: {response.status_code}. (At least it's not 405)")
            
    except Exception as e:
        print(f"❌ Connection Failed: {e}")

if __name__ == "__main__":
    test_delete_api()
