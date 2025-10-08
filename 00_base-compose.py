import requests
from ruamel.yaml import YAML

# URL of the yml file
url = "https://raw.githubusercontent.com/OpenCTI-Platform/docker/refs/heads/master/docker-compose.yml"

# Send a GET request to the URL
response = requests.get(url)

# Check if the request was successful
if response.status_code == 200:
    # Save the content to a file named 'base-compose.yml'
    with open("base-compose.yml", "w") as file:
        file.write(response.text)
    print("YML file has been successfully downloaded and saved as base-compose.yml")

    # Load the YAML content
    yaml = YAML()
    yaml.preserve_quotes = True  # Preserve quotes in the YAML output
    yaml.indent(mapping=2, sequence=4, offset=2)  # Set indentation for better readability
    with open("base-compose.yml", "r") as file:
        compose_data = yaml.load(file)

    # Update the depends_on sections
    for service in compose_data['services']:
        if 'depends_on' in compose_data['services'][service]:
            depends_on = compose_data['services'][service]['depends_on']
            if isinstance(depends_on, dict):
                compose_data['services'][service]['depends_on'] = list(depends_on.keys())

    # Save the updated YAML content
    with open("00_updated-compose.yml", "w") as file:
        yaml.dump(compose_data, file)
    print("YML file has been successfully updated and saved as updated-compose.yml")
else:
    print(f"Failed to download the YML file. Status code: {response.status_code}")
