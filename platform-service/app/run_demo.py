import requests
import time

URL = "http://localhost:8002/api/v1/upload"

docs = [
    {
        "title": "Threat Actor Profile: Emotet Botnet",
        "content": "Emotet is an advanced, self-propagating and modular Trojan that targets the financial sector. It often downloads and executes secondary payloads like TrickBot and Ryuk.",
        "source_name": "Security Blog",
        "published_at": "2024-01-01T00:00:00Z"
    },
    {
        "title": "Emotet Attribution Initial",
        "content": "Our researchers have confirmed that Emotet is attributed to TA542. The group has been active since at least 2014.",
        "source_name": "Intel Report",
        "published_at": "2024-01-15T00:00:00Z"
    },
    {
        "title": "Emotet Attribution Update",
        "content": "Emotet is now attributed to Mummy Spider. Additionally, they have recently started deploying Cobalt Strike beacons in their campaigns.",
        "source_name": "CISA Alert",
        "published_at": "2024-06-20T00:00:00Z"
    },
    {
        "title": "Emotet Conflicting Report",
        "content": "According to new telemetry from our sinkholes, Emotet is actually attributed to Lunar Spider, completely contradicting previous reports.",
        "source_name": "Contrarian Intel",
        "published_at": "2024-07-10T00:00:00Z"
    }
]

if __name__ == "__main__":
    for d in docs:
        d = {**d, 'title': '[DEMO] ' + d['title'], 'source_name': 'Synthetic demo / ' + d['source_name']}
        print(f"Uploading {d['title']}...")
        res = requests.post(URL, json=d, timeout=30)
        print(res.json())
        time.sleep(2)
