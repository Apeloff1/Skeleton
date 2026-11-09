#!/usr/bin/env python3
"""
Quick Galaxy Studio Factory Backend Status Check
"""

import requests
import json

BACKEND_URL = "https://gemini-game-craft.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api/galaxy-studio"

def test_endpoints():
    """Test the two previously failing endpoints"""
    
    # Test vault listing
    try:
        response = requests.get(f"{API_BASE}/vault", timeout=30)
        if response.status_code == 200:
            data = response.json()
            print("✅ Vault Listing: WORKING")
            print(f"    Total entries: {data.get('total_entries', 0)}")
            print(f"    ZIPs: {len(data.get('zips', []))}")
            print(f"    APKs: {len(data.get('apks', []))}")
        else:
            print(f"❌ Vault Listing: HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ Vault Listing: {e}")
    
    # Test deploy (using existing build ID)
    try:
        response = requests.post(f"{API_BASE}/deploy/702bc5ff-d44", timeout=30)
        if response.status_code == 200:
            data = response.json()
            print("✅ Deploy EAS: WORKING")
            print(f"    Status: {data.get('status')}")
            print(f"    EAS Build ID: {data.get('eas_build_id', 'N/A')}")
        else:
            print(f"❌ Deploy EAS: HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ Deploy EAS: {e}")

if __name__ == "__main__":
    test_endpoints()