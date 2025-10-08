import requests
import uuid

# Define the base URLs for the repositories
base_urls = {
    "external-import": "https://raw.githubusercontent.com/OpenCTI-Platform/connectors/master/external-import",
    "internal-enrichment": "https://raw.githubusercontent.com/OpenCTI-Platform/connectors/master/internal-enrichment"
}

# List of connectors to fetch (order matters)
connectors_to_fetch = ["abuseipdb", "abuseipdb-ipblacklist", "abuse-ssl", "alienvault", "cisa-known-exploited-vulnerabilities", "cve", "cyber-campaign-collection", "disarm-framework", "google-dns", "hygiene", "ipinfo", "mitre", "opencti", "threatfox", "urlhaus", "urlhaus-recent-payloads", "virustotal", "yara"]

# Function to fetch docker-compose.yml content for a given connector
def fetch_docker_compose_content(connector):
    for repo, base_url in base_urls.items():
        url = f"{base_url}/{connector}/docker-compose.yml"
        response = requests.get(url)
        if response.status_code == 200:
            return repo, response.text
    return None, None

# Function to clean and modify the content while preserving indentation
def clean_and_modify_content(content, connector_id):
    lines = content.split('\n')
    cleaned_lines = []
    for line in lines:
        if line.strip().startswith("version:") or line.strip().startswith("services:"):
            continue
        if "image:" in line:
            line = line.replace("6.5.9", "${OPENCTI_VERSION}")
        if "- OPENCTI_URL" in line:
            indent = line[:line.index("- OPENCTI_URL")]
            line = f"{indent}- OPENCTI_URL=http://opencti:8080"
        if "- OPENCTI_TOKEN" in line:
            indent = line[:line.index("- OPENCTI_TOKEN")]
            line = f"{indent}- OPENCTI_TOKEN=${{OPENCTI_ADMIN_TOKEN}}"
        if "- CONNECTOR_ID" in line:
            indent = line[:line.index("- CONNECTOR_ID")]
            line = f"{indent}- CONNECTOR_ID={connector_id}"
        if "restart: always" in line:
            indent = line[:line.index("restart: always")]
            cleaned_lines.append(line)
            cleaned_lines.append(f"{indent}depends_on:")
            cleaned_lines.append(f"{indent}  opencti:")
            cleaned_lines.append(f"{indent}    condition: service_healthy")
        else:
            cleaned_lines.append(line)
    return '\n'.join(cleaned_lines)

# Function to increment UUID
def increment_uuid(uuid_str):
    uuid_int = int(uuid.UUID(uuid_str))
    incremented_uuid_int = uuid_int + 1
    incremented_uuid_str = str(uuid.UUID(int=incremented_uuid_int))
    return incremented_uuid_str

# Initial CONNECTOR_ID value
connector_id = "aaa00000-0000-4aa0-8000-000000000000"

# Combine docker-compose.yml content
combined_content = ""
for connector in connectors_to_fetch:
    repo, content = fetch_docker_compose_content(connector)
    if content:
        cleaned_content = clean_and_modify_content(content, connector_id)
        combined_content += f"# Connector: {connector} (Repo: {repo})\n{cleaned_content}"
        connector_id = increment_uuid(connector_id)

# Write combined content to a file
with open('new_docker-compose.yml', 'w') as file:
    file.write(combined_content)
    