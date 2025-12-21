#!/usr/bin/env python3
"""
Generate a secure API key for the audio echo server.
"""

import secrets
import string

def generate_api_key(length: int = 32) -> str:
    """Generate a secure random API key."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

if __name__ == "__main__":
    api_key = generate_api_key()
    print("=" * 60)
    print("Generated API Key:")
    print("=" * 60)
    print(api_key)
    print("=" * 60)
    print("\nTo use this API key:")
    print("1. Set it as an environment variable:")
    print(f"   export API_KEY={api_key}")
    print("\n2. For Cloud Run deployment, set it as a secret:")
    print(f"   echo -n '{api_key}' | gcloud secrets create api-key --data-file=-")
    print("\n3. Or pass it directly when running the client:")
    print(f"   API_KEY={api_key} python client.py")
    print("=" * 60)

