import requests
import json
from typing import Dict, Any


def query_fraud_agent(user_text: str, url: str = "https://upay-gyghhpcbekgqd3ge.eastus2-01.azurewebsites.net/api/app/process") -> Dict[str, Any]:
    if not user_text:
        return {"error": "Input text cannot be empty."}
    params = {"text": user_text}
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        error_details = ""
        try:
            error_details = response.json()
        except Exception:
            error_details = response.text
        return {"error": f"HTTP error occurred: {http_err}", "details": error_details}
    except requests.exceptions.RequestException as req_err:
        return {"error": f"A network error occurred: {req_err}"}


if __name__ == "__main__":
    fraud_message = "URGENT your upay account is suspended click here to verify your details http://bit.ly/secure-upay"
    print(f"Querying with message: '{fraud_message}'")

    response = query_fraud_agent(fraud_message)

    print("\nAgent Response:")
    print(json.dumps(response, indent=2))
    print("-" * 40)

    normal_message = "Hey, can you send me the $25 for dinner last night?"
    print(f"Querying with message: '{normal_message}'")

    response = query_fraud_agent(normal_message)

    print("\nAgent Response:")
    print(json.dumps(response, indent=2))
    print("-" * 40)