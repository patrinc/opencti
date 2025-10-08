# OpenCTI Docker Swarm Deployment Guide

This comprehensive guide provides step-by-step instructions for deploying OpenCTI in a Docker Swarm environment. The architecture uses a hybrid approach with stateful services running as standalone containers and application services running in Swarm.

## Architecture Overview

```
CTI-WEB (Manager Node - 172.16.21.74):
├── Docker Swarm Manager
├── Portainer
├── OpenCTI Platform
├── Redis
└── Connectors

CTI-DB (Worker Node - 172.16.21.75):
├── Docker Swarm Worker
├── Elasticsearch
├── MinIO
└── RabbitMQ

```

## Directory Structure

```
CTI-WEB (172.16.21.74):
/opt/
├── portainer/
│   └── portainer-agent-stack.yml
└── opencti/
    ├── docker-stack.yml
    └── .env

CTI-DB (172.16.21.75):
/opt/
├── elasticsearch/
│   ├── docker-compose.yml
│   └── .env
├── minio/
│   ├── docker-compose.yml
│   └── .env
├── rabbitmq/
│   ├── docker-compose.yml
│   └── .env
└── opencti-data/
    ├── elasticsearch/
    ├── minio/
    └── rabbitmq/

```

## Step-by-Step Deployment Instructions

### STEP 1: Initial Setup (Both Nodes)

### On both CTI-WEB (172.16.21.74) and CTI-DB (172.16.21.75):

```bash
# Uninstall old Docker and Portainer
sudo docker swarm leave --force
sudo docker stop portainer_agent
dpkg -l | grep -i docker
sudo apt-get purge -y docker-engine docker docker.io docker-ce docker-ce-cli docker-compose-plugin
dpkg -l | grep -i docker
sudo apt-get autoremove -y --purge docker-engine docker docker.io docker-ce docker-compose-plugin
sudo rm -rf /var/lib/docker /etc/docker
sudo rm -f /etc/apparmor.d/docker
sudo groupdel docker
sudo rm -rf /var/run/docker.sock
sudo find / -name '*portainer*'
sudo find / -name '*portainer*' -exec rm -rf {} \;

# Install latest Docker Engine & Compose Plugin
sudo apt-get update
sudo apt-get install -y apt-transport-https ca-certificates curl gnupg-agent software-properties-common
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo apt-key fingerprint 0EBFCD88
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add your user to the docker group
sudo usermod -aG docker $USER
newgrp docker

# Verify Docker and Compose
docker --version
docker compose version

# Set sysctl for Elasticsearch
sudo sysctl -w vm.max_map_count=1048575
echo "vm.max_map_count=1048575" | sudo tee -a /etc/sysctl.conf

```

### STEP 2: Initialize Docker Swarm

### On CTI-WEB (172.16.21.74) - Manager Node:

```bash
# Initialize Swarm
docker swarm init --advertise-addr 172.16.21.74

# Label the manager node
docker node update --label-add role=manager $(hostname)

# Label the worker node from here as well. Use "docker node ls" for worker node-id
docker node update --label-add role=storage <worker-node-id>
```

You'll see output like:

```
Swarm initialized: current node (abcdef123456) is now a manager.

To add a worker to this swarm, run the following command:
    docker swarm join --token SWMTKN-1-xxxxxxxxxxxxxxxxxxxxxxxxx-xxxxxxxxxxxxxxx 172.16.21.74:2377

```

Copy the join command for the next step.

### On CTI-DB (172.16.21.75) - Worker Node:

```bash
# Join the swarm using the token from manager output
docker swarm join --token SWMTKN-1-xxxxxxxxxxxxxxxxxxxxxxxxx-xxxxxxxxxxxxxxx 172.16.21.74:2377
```

To check the node label please use `docker node inspect <node-id> --format '{{.Spec.Labels }}'`

### STEP 3: Set Up Data Directories on CTI-DB

### On CTI-DB (172.16.21.75):

```bash
# Create data directories
sudo mkdir -p /opt/opencti-data/elasticsearch
sudo mkdir -p /opt/opencti-data/minio
sudo mkdir -p /opt/opencti-data/rabbitmq

# Set proper permissions
sudo chown -R 1000:1000 /opt/opencti-data/elasticsearch
sudo chown -R 1000:1000 /opt/opencti-data/minio

```

### STEP 4: Deploy Elasticsearch on CTI-DB

### On CTI-DB (172.16.21.75):

```bash
# Create Elasticsearch directory
sudo mkdir -p /opt/elasticsearch && cd /opt/elasticsearch
```

Create `docker-compose.yml` using `sudo nano docker-compose.yml`:

```yaml
version: '3.8'

services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:${ELASTIC_VERSION}
    container_name: elasticsearch
    restart: always
    ports:
      - "9200:9200"
      - "9300:9300"
    environment:
      - discovery.type=single-node
      - "ES_JAVA_OPTS=-Xms${ELASTIC_MEMORY_SIZE} -Xmx${ELASTIC_MEMORY_SIZE}"
      - xpack.security.enabled=false
      - xpack.security.enrollment.enabled=false
    ulimits:
      memlock:
        soft: -1
        hard: -1
      nofile:
        soft: 65536
        hard: 65536
    volumes:
      - esdata:/usr/share/elasticsearch/data

  kibana:
    image: docker.elastic.co/kibana/kibana:${ELASTIC_VERSION}
    container_name: kibana
    restart: always
    depends_on:
      - elasticsearch
    ports:
      - "5601:5601"
    environment:
      - ELASTICSEARCH_HOSTS=http://elasticsearch:9200

volumes:
  esdata:
```

Create `.env` using `sudo nano .env`:

```bash
ELASTIC_VERSION=8.14.0
ELASTIC_MEMORY_SIZE=4G

```

Create the `load_env.sh` script to load environment variables and start Elasticsearch using `sudo nano /opt/elasticsearch/load_env.sh`:

```bash
#!/bin/bash
# Export environment variables for Elasticsearch
export \$(cat /opt/elasticsearch/.env | grep -v "^\#" | xargs)

# Start Elasticsearch service
docker compose -f /opt/elasticsearch/docker-compose.yml up -d
```

Make the script executable:

```bash
sudo chmod +x /opt/elasticsearch/load_env.sh
```

**Set up cron job to execute at boot:**

```bash
# Add cron job to execute the script at boot
(sudo crontab -l 2>/dev/null; echo "@reboot /opt/elasticsearch/load_env.sh") | sudo crontab -

```

Start Elasticsearch:

```bash
# Load environment variables from .env file
export $(cat .env | grep -v '^#' | xargs)

# Deploy the stack
docker compose up -d

```

### STEP 5: Deploy MinIO on CTI-DB

### On CTI-DB (172.16.21.75):

```bash
# Create MinIO directory
sudo mkdir -p /opt/minio && cd /opt/minio

```

Create `docker-compose.yml` using `sudo nano docker-compose.yml`:

```yaml
version: '3.8'

services:
  minio:
    image: minio/minio:RELEASE.2024-05-28T17-19-04Z
    container_name: minio
    restart: always
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      - MINIO_ROOT_USER=${MINIO_ROOT_USER}
      - MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}
    command: server --console-address ":9001" /data
    volumes:
      - s3data:/data

volumes:
  s3data:

```

Create `.env` using `sudo nano .env`:

```bash
MINIO_ROOT_USER=opencti
MINIO_ROOT_PASSWORD=ChangeMe123!

```

Create the `load_env.sh` script to load environment variables and start Minio using `sudo nano /opt/minio/load_env.sh`:

```bash
#!/bin/bash
# Export environment variables for Minio
export \$(cat /opt/minio/.env | grep -v "^\#" | xargs)

# Start Minio service
docker compose -f /opt/minio/docker-compose.yml up -d
```

Make the script executable:

```bash
sudo chmod +x /opt/minio/load_env.sh
```

**Set up cron job to execute at boot:**

```bash
# Add cron job to execute the script at boot
(sudo crontab -l 2>/dev/null; echo "@reboot /opt/minio/load_env.sh") | sudo crontab -

```

Start MinIO:

```bash
# Load environment variables from .env file
export $(cat .env | grep -v '^#' | xargs)

# Deploy the stack
docker compose up -d

```

### STEP 6: Deploy RabbitMQ on CTI-DB

### On CTI-DB (172.16.21.75):

```bash
# Create RabbitMQ directory
sudo mkdir -p /opt/rabbitmq && cd /opt/rabbitmq

```

Create `docker-compose.yml` using `sudo nano docker-compose.yml`:

```yaml
version: '3.8'

services:
  rabbitmq:
    image: rabbitmq:4.1-management
    container_name: rabbitmq
    restart: always
    ports:
      - "5672:5672"
      - "15672:15672"
    environment:
      - RABBITMQ_DEFAULT_USER=${RABBITMQ_DEFAULT_USER}
      - RABBITMQ_DEFAULT_PASS=${RABBITMQ_DEFAULT_PASS}
    volumes:
      - amqpdata:/var/lib/rabbitmq

volumes:
  amqpdata:

```

Create `.env` using `sudo nano .env`:

```bash
RABBITMQ_DEFAULT_USER=opencti
RABBITMQ_DEFAULT_PASS=ChangeMe123!
```

Create the `load_env.sh` script to load environment variables and start RabbitMQ using `sudo nano /opt/rabbitmq/load_env.sh`:

```bash
#!/bin/bash
# Export environment variables for RabbitMQ
export \$(cat /opt/rabbitmq/.env | grep -v "^\#" | xargs)

# Start RabbitMQ service
docker compose -f /opt/rabbitmq/docker-compose.yml up -d
```

Make the script executable:

```bash
sudo chmod +x /opt/rabbitmq/load_env.sh
```

**Set up cron job to execute at boot:**

```bash
# Add cron job to execute the script at boot
(sudo crontab -l 2>/dev/null; echo "@reboot /opt/rabbitmq/load_env.sh") | sudo crontab -

```

Start RabbitMQ:

```bash
# Load environment variables from .env file
export $(cat .env | grep -v '^#' | xargs)

# Deploy the stack
docker compose up -d

```

### STEP 7: Deploy Portainer on CTI-WEB

### On CTI-WEB (172.16.21.74):

```bash
# Create Portainer directory
sudo mkdir -p /opt/portainer && cd /opt/portainer
sudo curl -L https://downloads.portainer.io/portainer-agent-stack.yml -o portainer-agent-stack.yml
```

Create `portainer-agent-stack.yml` using `sudo nano portainer-agent-stack.yml`:

```yaml
version: '3.2'

services:
  agent:
    image: portainer/agent:latest
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - /var/lib/docker/volumes:/var/lib/docker/volumes
    networks:
      - agent_network
    deploy:
      mode: global
      placement:
        constraints: [node.platform.os == linux]

  portainer:
    image: portainer/portainer-ee:latest
    command: -H tcp://tasks.agent:9001 --tlsskipverify
    ports:
      - "19000:9000"
      - "18000:8000"
    volumes:
      - portainer_data:/data
    networks:
      - agent_network
    deploy:
      mode: replicated
      replicas: 1
      placement:
        constraints: [node.role == manager]

networks:
  agent_network:
    driver: overlay
    attachable: true

volumes:
  portainer_data:

```

Deploy Portainer:

```bash
docker stack deploy --compose-file portainer-agent-stack.yml portainer

```

Access Portainer UI at `http://172.16.21.74:19000`

### STEP 8: Deploy OpenCTI on CTI-WEB

### On CTI-WEB (172.16.21.74):

```bash
# Create OpenCTI directory
sudo mkdir -p /opt/opencti && cd /opt/opencti

```

Create `docker-stack.yml` using `sudo nano docker-stack.yml`:

```yaml
version: '3.8'

services:
  redis:
    image: redis:7.4.3
    deploy:
      placement:
        constraints: [node.role == manager]
    restart: always
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  opencti:
    image: opencti/platform:${OPENCTI_VERSION}
    environment:
      - NODE_OPTIONS=--max-old-space-size=8096
      - APP__PORT=8080
      - APP__BASE_URL=${OPENCTI_BASE_URL}
      - APP__ADMIN__EMAIL=${OPENCTI_ADMIN_EMAIL}
      - APP__ADMIN__PASSWORD=${OPENCTI_ADMIN_PASSWORD}
      - APP__ADMIN__TOKEN=${OPENCTI_ADMIN_TOKEN}
      - APP__APP_LOGS__LOGS_LEVEL=info
      - REDIS__HOSTNAME=redis
      - REDIS__PORT=6379
      - ELASTICSEARCH__URL=http://${CTI_DB_IP}:9200
      - ELASTICSEARCH__NUMBER_OF_REPLICAS=0
      - MINIO__ENDPOINT=${CTI_DB_IP}
      - MINIO__PORT=9000
      - MINIO__USE_SSL=false
      - MINIO__ACCESS_KEY=${MINIO_ROOT_USER}
      - MINIO__SECRET_KEY=${MINIO_ROOT_PASSWORD}
      - RABBITMQ__HOSTNAME=${CTI_DB_IP}
      - RABBITMQ__PORT=5672
      - RABBITMQ__USERNAME=${RABBITMQ_DEFAULT_USER}
      - RABBITMQ__PASSWORD=${RABBITMQ_DEFAULT_PASS}
      - SMTP__HOSTNAME=${SMTP_HOSTNAME}
      - SMTP__PORT=25
      - PROVIDERS__LOCAL__STRATEGY=LocalStrategy
      - APP__HEALTH_ACCESS_KEY=${OPENCTI_HEALTHCHECK_ACCESS_KEY}
    ports:
      - "8080:8080"
    deploy:
      placement:
        constraints: [node.role == manager]
      resources:
        limits:
          memory: 8g
    depends_on:
      - redis
    restart: always
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://opencti:8080/health?health_access_key=${OPENCTI_HEALTHCHECK_ACCESS_KEY}"]
      interval: 10s
      timeout: 5s
      retries: 20

  worker:
    image: opencti/worker:${OPENCTI_VERSION}
    environment:
      - OPENCTI_URL=http://opencti:8080
      - OPENCTI_TOKEN=${OPENCTI_ADMIN_TOKEN}
      - WORKER_LOG_LEVEL=info
    depends_on:
      - opencti
    deploy:
      mode: replicated
      replicas: 3
      placement:
        constraints: [node.role == manager]
    restart: always

  connector-export-file-stix:
    image: opencti/connector-export-file-stix:${OPENCTI_VERSION}
    environment:
      - OPENCTI_URL=http://opencti:8080
      - OPENCTI_TOKEN=${OPENCTI_ADMIN_TOKEN}
      - CONNECTOR_ID=${CONNECTOR_EXPORT_FILE_STIX_ID} # Valid UUIDv4
      - CONNECTOR_TYPE=INTERNAL_EXPORT_FILE
      - CONNECTOR_NAME=ExportFileStix2
      - CONNECTOR_SCOPE=application/json
      - CONNECTOR_LOG_LEVEL=info
    deploy:
      placement:
        constraints: [node.role == manager]
    restart: always
    depends_on:
      - opencti

  connector-export-file-csv:
    image: opencti/connector-export-file-csv:${OPENCTI_VERSION}
    environment:
      - OPENCTI_URL=http://opencti:8080
      - OPENCTI_TOKEN=${OPENCTI_ADMIN_TOKEN}
      - CONNECTOR_ID=${CONNECTOR_EXPORT_FILE_CSV_ID} # Valid UUIDv4
      - CONNECTOR_TYPE=INTERNAL_EXPORT_FILE
      - CONNECTOR_NAME=ExportFileCsv
      - CONNECTOR_SCOPE=text/csv
      - CONNECTOR_LOG_LEVEL=info
    deploy:
      placement:
        constraints: [node.role == manager]
    restart: always
    depends_on:
      - opencti

  connector-export-file-txt:
    image: opencti/connector-export-file-txt:${OPENCTI_VERSION}
    environment:
      - OPENCTI_URL=http://opencti:8080
      - OPENCTI_TOKEN=${OPENCTI_ADMIN_TOKEN}
      - CONNECTOR_ID=${CONNECTOR_EXPORT_FILE_TXT_ID} # Valid UUIDv4
      - CONNECTOR_TYPE=INTERNAL_EXPORT_FILE
      - CONNECTOR_NAME=ExportFileTxt
      - CONNECTOR_SCOPE=text/plain
      - CONNECTOR_LOG_LEVEL=info
    deploy:
      placement:
        constraints: [node.role == manager]
    restart: always
    depends_on:
      - opencti

  connector-import-file-stix:
    image: opencti/connector-import-file-stix:${OPENCTI_VERSION}
    environment:
      - OPENCTI_URL=http://opencti:8080
      - OPENCTI_TOKEN=${OPENCTI_ADMIN_TOKEN}
      - CONNECTOR_ID=${CONNECTOR_IMPORT_FILE_STIX_ID} # Valid UUIDv4
      - CONNECTOR_TYPE=INTERNAL_IMPORT_FILE
      - CONNECTOR_NAME=ImportFileStix
      - CONNECTOR_VALIDATE_BEFORE_IMPORT=true # Validate any bundle before import
      - CONNECTOR_SCOPE=application/json,text/xml
      - CONNECTOR_AUTO=true # Enable/disable auto-import of file
      - CONNECTOR_LOG_LEVEL=info
    deploy:
      placement:
        constraints: [node.role == manager]
    restart: always
    depends_on:
      - opencti

  connector-import-document:
    image: opencti/connector-import-document:${OPENCTI_VERSION}
    environment:
      - OPENCTI_URL=http://opencti:8080
      - OPENCTI_TOKEN=${OPENCTI_ADMIN_TOKEN}
      - CONNECTOR_ID=${CONNECTOR_IMPORT_DOCUMENT_ID} # Valid UUIDv4
      - CONNECTOR_TYPE=INTERNAL_IMPORT_FILE
      - CONNECTOR_NAME=ImportDocument
      - CONNECTOR_VALIDATE_BEFORE_IMPORT=true # Validate any bundle before import
      - CONNECTOR_SCOPE=application/pdf,text/plain,text/html
      - CONNECTOR_AUTO=true # Enable/disable auto-import of file
      - CONNECTOR_ONLY_CONTEXTUAL=false # Only extract data related to an entity (a report, a threat actor, etc.)
      - CONNECTOR_CONFIDENCE_LEVEL=15 # From 0 (Unknown) to 100 (Fully trusted)
      - CONNECTOR_LOG_LEVEL=info
      - IMPORT_DOCUMENT_CREATE_INDICATOR=true
    deploy:
      placement:
        constraints: [node.role == manager]
    restart: always
    depends_on:
      - opencti

  connector-analysis:
    image: opencti/connector-import-document:${OPENCTI_VERSION}
    environment:
      - OPENCTI_URL=http://opencti:8080
      - OPENCTI_TOKEN=${OPENCTI_ADMIN_TOKEN}
      - CONNECTOR_ID=${CONNECTOR_ANALYSIS_ID} # Valid UUIDv4
      - CONNECTOR_TYPE=INTERNAL_ANALYSIS
      - CONNECTOR_NAME=ImportDocumentAnalysis
      - CONNECTOR_VALIDATE_BEFORE_IMPORT=false # Validate any bundle before import
      - CONNECTOR_SCOPE=application/pdf,text/plain,text/html
      - CONNECTOR_AUTO=true # Enable/disable auto-import of file
      - CONNECTOR_ONLY_CONTEXTUAL=false # Only extract data related to an entity (a report, a threat actor, etc.)
      - CONNECTOR_CONFIDENCE_LEVEL=15 # From 0 (Unknown) to 100 (Fully trusted)
      - CONNECTOR_LOG_LEVEL=info
    deploy:
      placement:
        constraints: [node.role == manager]
    restart: always
    depends_on:
      - opencti

volumes:
  esdata:
  s3data:
  redisdata:
  amqpdata:

```

Create `.env` using `sudo nano .env`:

```bash
# OpenCTI Configuration
OPENCTI_VERSION=6.6.8
OPENCTI_ADMIN_EMAIL=first.last@domain.com
OPENCTI_ADMIN_PASSWORD=36!KYsQFVDxME
OPENCTI_ADMIN_TOKEN=aaa00000-0000-2aa0-8000-000000000000
OPENCTI_BASE_URL=http://172.16.21.74:8080
OPENCTI_HEALTHCHECK_ACCESS_KEY=aaa00000-0000-2aa0-8000-000000000001

# Node IPs
CTI_WEB_IP=172.16.21.74
CTI_DB_IP=172.16.21.75

# Service Credentials (must match CTI-DB settings)
MINIO_ROOT_USER=opencti
MINIO_ROOT_PASSWORD=36!KYsQFVDxME
RABBITMQ_DEFAULT_USER=opencti
RABBITMQ_DEFAULT_PASS=36!KYsQFVDxME

# Connector IDs
CONNECTOR_EXPORT_FILE_STIX_ID=aaa00000-0000-2aa0-8000-000000000003
CONNECTOR_EXPORT_FILE_CSV_ID=aaa00000-0000-2aa0-8000-000000000004
CONNECTOR_EXPORT_FILE_TXT_ID=aaa00000-0000-2aa0-8000-000000000005
CONNECTOR_IMPORT_FILE_STIX_ID=aaa00000-0000-2aa0-8000-000000000006
CONNECTOR_IMPORT_DOCUMENT_ID=aaa00000-0000-2aa0-8000-000000000007
CONNECTOR_ANALYSIS_ID=aaa00000-0000-2aa0-8000-000000000008

# API Keys for Connectors
ABUSEIPDB_API_KEY=70b9bbe6800ebe94a5387ddb7bd4624d630e7a48f4fbb63830ca7eb06a6b658b5a1383b51bd47825
ALIENVAULT_API_KEY=30942ade311cc2db3e640df7633a6083ad7a92ea8eadd88f00bcf90436844043
CVE_API_KEY=758ef74a-95c6-4048-8a68-3561da81e83e
IPINFO_TOKEN=47e53373ab3944
VIRUSTOTAL_TOKEN=8e08743c71d3b12e218b807ad016878dfd3e51893d383319f7d3f1ba0704396f

# Other Settings
SMTP_HOSTNAME=localhost
ELASTIC_MEMORY_SIZE=4G
```

Create the `load_env.sh` script to load environment variables and start OpenCTI using `sudo nano oad_env.sh` :

```bash
#!/bin/bash
# Export environment variables for OpenCTI
export \$(cat /opt/opencti/.env | grep -v "^\#" | xargs)

# Start OpenCTI service
docker compose -f /opt/opencti/docker-stack.yml up -d
```

Make the script executable:

```bash
sudo chmod +x /opt/opencti/load_env.sh
```

Set up cron job to execute at boot:

```bash
# Add cron job to execute the script at boot
(sudo crontab -l 2>/dev/null; echo "@reboot /opt/opencti/load_env.sh") | sudo crontab -

```

Deploy OpenCTI:

```bash
# Load environment variables from .env file
export $(cat .env | grep -v '^#' | xargs)

# Then deploy the stack
docker stack deploy --compose-file docker-stack.yml opencti

```

### STEP 9: Adding More Connectors

To add more connectors to your deployment, you'll need to:

1. Add each connector service to the `docker-stack.yml` file
2. Add any required API keys to the `.env` file

Here's an example for adding the VirusTotal connector:

```yaml
# Add this to docker-stack.yml under services
connector-virustotal:
  image: opencti/connector-virustotal:${OPENCTI_VERSION}
  environment:
    - OPENCTI_URL=http://opencti:8080
    - OPENCTI_TOKEN=${OPENCTI_ADMIN_TOKEN}
    - CONNECTOR_ID=aaa00000-0000-4aa0-8000-000000000001
    - CONNECTOR_TYPE=EXTERNAL_IMPORT
    - CONNECTOR_NAME=VirusTotal
    - CONNECTOR_SCOPE=virustotal
    - CONNECTOR_CONFIDENCE_LEVEL=100
    - CONNECTOR_UPDATE_EXISTING_DATA=false
    - CONNECTOR_LOG_LEVEL=info
    - VIRUSTOTAL_TOKEN=${VIRUSTOTAL_TOKEN}
    - VIRUSTOTAL_MAX_TLP=TLP:AMBER
  deploy:
    placement:
      constraints: [node.role == manager]
  restart: always
  depends_on:
    - opencti

```

After updating the file, redeploy the stack:

```bash
docker stack deploy --compose-file docker-stack.yml opencti

```

### STEP 10: Verifying Deployment

Check the status of your swarm services:

```bash
# On CTI-WEB (Manager Node)
docker stack ps opencti
docker service ls

```

Check standalone service status:

```bash
# On CTI-DB (Worker Node)
docker ps

```

Verify you can access:

- OpenCTI UI: http://172.16.21.74:8080
- Portainer: http://172.16.21.74:9000
- Kibana (optional): http://172.16.21.75:5601
- MinIO Console: http://172.16.21.75:9001
- RabbitMQ Management: http://172.16.21.75:15672

## Troubleshooting

### Verify Node Communication

Make sure the nodes can communicate with each other:

```bash
# From CTI-WEB
ping 172.16.21.75

# From CTI-DB
ping 172.16.21.74

```

### Check Service Logs

```bash
# For swarm services (on CTI-WEB)
docker service logs opencti_opencti
docker service logs opencti_connector-abuseipdb

# For standalone services (on CTI-DB)
docker logs elasticsearch
docker logs minio
docker logs rabbitmq

```

### Common Issues & Solutions

1. **OpenCTI can't connect to Elasticsearch**:
   - Verify Elasticsearch is running: `curl http://172.16.21.75:9200`
   - Check firewall rules between nodes
2. **MinIO connection issues**:
   - Verify MinIO is accessible: `curl http://172.16.21.75:9000`
   - Check MinIO credentials in both .env files match
3. **Connectors not working**:
   - Verify RabbitMQ: `curl -u opencti:ChangeMe123! http://172.16.21.75:15672/api/overview`
   - Check connector logs for API key issues

## Backup Strategy

### Data Directories to Back Up

- `/opt/opencti-data/elasticsearch`
- `/opt/opencti-data/minio`
- `/opt/opencti-data/rabbitmq`

### Basic Backup Script

Create `/opt/backup-opencti.sh` on CTI-DB:

```bash
#!/bin/bash
BACKUP_DIR="/backup/opencti-$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# Stop services
cd /opt/elasticsearch && docker compose stop
cd /opt/minio && docker compose stop
cd /opt/rabbitmq && docker compose stop

# Backup data
tar -czf $BACKUP_DIR/elasticsearch-data.tar.gz /opt/opencti-data/elasticsearch
tar -czf $BACKUP_DIR/minio-data.tar.gz /opt/opencti-data/minio
tar -czf $BACKUP_DIR/rabbitmq-data.tar.gz /opt/opencti-data/rabbitmq

# Restart services
cd /opt/elasticsearch && docker compose start
cd /opt/minio && docker compose start
cd /opt/rabbitmq && docker compose start

echo "Backup completed to $BACKUP_DIR"

```

Make it executable:

```bash
chmod +x /opt/backup-opencti.sh

```

## Maintenance Commands

### Update OpenCTI

To update OpenCTI version:

1. Update the OPENCTI_VERSION in `/opt/opencti/.env`
2. Redeploy the stack:

   ```bash
   cd /opt/openctidocker stack deploy --compose-file docker-stack.yml opencti

   ```

### Scale Connectors

To add more instances of a connector:

```bash
docker service scale opencti_connector-abuseipdb=2

```

### Reset Deployment

To completely reset the deployment:

```bash
# On CTI-WEB
docker stack rm portainer opencti

# On CTI-DB
cd /opt/elasticsearch && docker compose down
cd /opt/minio && docker compose down
cd /opt/rabbitmq && docker compose down

# Remove data if needed
sudo rm -rf /opt/opencti-data/*

```

### Monitor Resources

```bash
# Check resource usage
docker stats

# Monitor disk space
df -h

```

---

---

## Updating Services on CTI-DB Node

Here's how to update each service while minimizing downtime and ensuring data safety:

### 1. Updating Elasticsearch

```bash

bash
# On CTI-DB (172.16.21.75)
cd /opt/elasticsearch

# Backup your current .env file
cp .env .env.backup

# Update the Elasticsearch version in .env# Change this line: ELASTIC_VERSION=8.10.0# To the version you want, e.g.: ELASTIC_VERSION=8.11.3# Stop the current containers
docker compose down

# Pull the new images
docker compose pull

# Start with updated images
docker compose up -d

# Verify the new version
curl http://localhost:9200

```

**Important notes for Elasticsearch updates:**

- Check compatibility between versions (especially for major version upgrades)
- For major version upgrades (e.g., 7.x to 8.x), you might need migration steps
- Consider backing up data before upgrading `tar -czf elasticsearch-backup.tar.gz /opt/opencti-data/elasticsearch`

### 2. Updating MinIO

```bash

bash
# On CTI-DB (172.16.21.75)
cd /opt/minio

# Stop the current MinIO container
docker compose down

# Update the docker-compose.yml to specify version# Change: image: minio/minio:latest# To something like: image: minio/minio:RELEASE.2023-05-18T00-05-36Z# Pull the new image
docker compose pull

# Start with updated image
docker compose up -d

# Verify the new version
curl http://localhost:9000/minio/health/live

```

**MinIO update notes:**

- MinIO is generally backward compatible
- Using a specific version tag instead of `latest` gives better control
- Consider backing up before upgrading `tar -czf minio-backup.tar.gz /opt/opencti-data/minio`

### 3. Updating RabbitMQ

```bash

bash
# On CTI-DB (172.16.21.75)
cd /opt/rabbitmq

# Backup the current configuration
tar -czf rabbitmq-backup.tar.gz /opt/opencti-data/rabbitmq

# Update the image version in docker-compose.yml# Change: image: rabbitmq:3.12-management# To something like: image: rabbitmq:3.13-management# Stop the current containers
docker compose down

# Pull the new images
docker compose pull

# Start with updated images
docker compose up -d

# Verify the new version in the management UI# http://172.16.21.75:15672/

```

**RabbitMQ update notes:**

- Minor version updates are generally safe
- For major version updates, check the RabbitMQ changelog for breaking changes
- RabbitMQ stores messages in memory with persistence to disk, so expect a brief service interruption

### 4. Coordinated Update Process

For a full system update, I recommend this order:

1. Create a full backup first
2. Update RabbitMQ
3. Update MinIO
4. Update Elasticsearch
5. Update OpenCTI on the CTI-WEB node

This sequence minimizes the chance of compatibility issues between services.

### 5. Rolling Back Updates

If an update causes problems, you can roll back using your backups:

```bash

bash
# Example rollback for Elasticsearch
cd /opt/elasticsearch
docker compose down
sudo rm -rf /opt/opencti-data/elasticsearch/*
sudo tar -xzf elasticsearch-backup.tar.gz -C /
# Restore your original .env file if changed
cp .env.backup .env
docker compose up -d

```

### 6. Update Script Example

Here's a simple script you could create at `/opt/update-services.sh` on the CTI-DB node to help with updates:

```bash
#!/bin/bash
# Update script for OpenCTI backend services# Define backup directory
BACKUP_DIR="/opt/backups/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

echo "Creating backups in $BACKUP_DIR"
tar -czf $BACKUP_DIR/elasticsearch-data.tar.gz /opt/opencti-data/elasticsearch
tar -czf $BACKUP_DIR/minio-data.tar.gz /opt/opencti-data/minio
tar -czf $BACKUP_DIR/rabbitmq-data.tar.gz /opt/opencti-data/rabbitmq

# Update each service
echo "Updating RabbitMQ..."
cd /opt/rabbitmq
docker compose down
docker compose pull
docker compose up -d

echo "Updating MinIO..."
cd /opt/minio
docker compose down
docker compose pull
docker compose up -d

echo "Updating Elasticsearch..."
cd /opt/elasticsearch
docker compose down
docker compose pull
docker compose up -d

echo "All services updated. Please check logs to verify proper operation."
echo "If issues occur, restore from backups in $BACKUP_DIR"

```

Make it executable:

```bash

chmod +x /opt/update-services.sh
```

### 7. Best Practices for Updates

1. **Always backup before updating:** This ensures you have a restore point
2. **Check version compatibility:** Review release notes for breaking changes
3. **Update during maintenance windows:** Schedule updates when usage is low
4. **Test in staging first:** If possible, test on a staging environment
5. **Monitor after updates:** Watch logs and performance after updating
6. **Pin versions:** Use specific version tags rather than "latest" for better control

These update procedures should fit well with the deployment guide I provided earlier. By following these steps, you can keep your OpenCTI environment up to date while minimizing the risk of data loss or extended downtime.
