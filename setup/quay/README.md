# Ansible Execution Environment Build

This directory contains the configuration and scripts for building a custom Ansible Execution Environment (EE) container image for the NetBox Proxmox Automation project.

## Overview

An Ansible Execution Environment is a containerized image that contains:
- Ansible Core and Ansible Runner
- Ansible collections (from `requirements.yml`)
- Python dependencies (from `requirements.txt`)
- System-level dependencies (from `bindep.txt`)
- Custom CA certificates for internal network communication

This custom EE is optimized to run the NetBox-Proxmox automation playbooks within Ansible AWX.

## Directory Structure

```
setup/quay/
├── README.md                           # This documentation file
├── execution-environment.yml           # EE configuration and build steps
├── requirements.yml                    # Ansible collection dependencies
├── requirements.txt                    # Python package dependencies
├── bindep.txt                          # System package dependencies
├── root-ca.pem                         # Custom CA certificate for HTTPS
└── context/                            # Build context for Docker
    ├── Dockerfile                      # Multi-stage Docker build
    └── _build/
        └── scripts/
            ├── introspect.py          # Dependency introspection script
            └── entrypoint             # Container entrypoint
```

## File Descriptions

### execution-environment.yml
Configuration file that defines:
- **Base image**: Uses `ghcr.io/ansible-community/community-ee-minimal:latest`
- **Dependencies sources**: Points to requirements files
- **Ansible packages**: Specifies `ansible-core` and `ansible-runner` versions
- **Build steps**: Includes CA certificate setup and build validation

### requirements.yml
Lists Ansible collections required for the automation:
- `community.proxmox`: For Proxmox API interactions
- `community.general`: For general Ansible tasks

### requirements.txt
Python package dependencies needed by:
- Collections' Python modules
- AWX runtime
- API clients and network libraries

### bindep.txt
System-level package dependencies installed via the package manager (dnf/yum):
- Required for Python package compilation
- System libraries needed by collections

### root-ca.pem
Custom CA certificate used for:
- HTTPS connections to internal services
- NetBox API calls through corporate proxies
- Proxmox API connections with self-signed certificates

## Build Process

The build uses a multi-stage Docker approach:

### Stage 1: Base
- Starts from the minimal Ansible EE image
- Installs pip and Ansible dependencies
- Sets up build environment variables

### Stage 2: Galaxy
- Installs Ansible collections from `requirements.yml`
- Places collections in standard Ansible paths

### Stage 3: Builder
- Runs `introspect.py` to analyze collection dependencies
- Extracts Python and system requirements from collections
- Combines with user-specified requirements
- Generates final dependency lists

### Stage 4: Final
- Installs all resolved dependencies
- Sets up CA certificates
- Configures runner environment
- Cleans up build artifacts
- Sets entrypoint for AWX execution

## Key Scripts

### introspect.py
The dependency introspection script that:
1. Scans installed Ansible collections
2. Reads `meta/execution-environment.yml` from each collection
3. Extracts Python (`requirements.txt`) and system (`bindep.txt`) dependencies
4. Filters out test-only packages and already-satisfied dependencies
5. Combines all dependencies into comprehensive requirement lists
6. Outputs annotated requirements showing their source collection

**Excluded dependencies** (filtered out):
- Test frameworks (pytest, tox, molecule, etc.)
- Ansible testing tools (ansible-lint, galaxy-importer, etc.)
- Already-provided packages (ansible, python, yaml, json, etc.)

### Dockerfile
The multi-stage build configuration that:
1. Uses build arguments for flexibility
2. Creates separate stages for dependency resolution
3. Includes CA certificate injection
4. Validates the final Ansible installation
5. Sets proper permissions for AWX execution

## Building the Image

### Prerequisites
Before building, ensure the CA certificate is in the build context:
```bash
# Copy root-ca.pem to the context directory (required for the Dockerfile)
cp root-ca.pem context/root-ca.pem
```

### Using Ansible Builder
```bash
# Copy root-ca.pem to context first
cp root-ca.pem context/root-ca.pem

# Build the image
ansible-builder build -f execution-environment.yml -c context/ -t netbox-proxmox-ee:latest
```

### Using Docker Directly
```bash
# Copy root-ca.pem to context first
cp root-ca.pem context/root-ca.pem

# Build the image
docker build -f context/Dockerfile -t netbox-proxmox-ee:latest context/
```

### Example with Version Tag
```bash
cp root-ca.pem context/root-ca.pem
ansible-builder build -f execution-environment.yml -c context/ -t quay.io/gutleber/netbox-proxmox-ee:1.0.3
```

### Push to Registry
```bash
docker push quay.io/your-org/netbox-proxmox-ee:latest
```

## Updating Dependencies

### Adding a Collection
1. Add to `setup/quay/requirements.yml`
2. Run the build
3. Commit the updated files

### Adding Python Dependencies
1. Add to `setup/quay/requirements.txt`
2. Run the build

### Adding System Dependencies
1. Add to `setup/quay/bindep.txt`
2. Run the build

## CA Certificate Configuration

The custom CA certificate is injected during the build to support:
- Internal HTTPS connections
- Proxmox API with self-signed certificates
- NetBox API through corporate proxies

To update the certificate:
1. Replace `root-ca.pem` with your custom certificate
2. Rebuild the image

## Environment Variables

The built image supports these key variables:
- `REQUESTS_CA_BUNDLE`: Points to injected CA certificate
- `PIP_BREAK_SYSTEM_PACKAGES`: Allows pip to install into system Python
- `ANSIBLE_GALAXY_DISABLE_GPG_VERIFY`: Used during collection installation (can be overridden)

## Troubleshooting

### Build Fails with Missing Dependencies
Check that all required packages are listed in `requirements.txt` and `bindep.txt`. Run `introspect.py` to see what's detected.

### Collection Import Errors
Ensure the collection is properly listed in `requirements.yml` and was successfully installed in the build.

### Certificate Errors
Verify `root-ca.pem` contains the correct CA certificate chain and is in PEM format.

## Related Documentation

- [Ansible Execution Environments](https://ansible.readthedocs.io/projects/builder/en/stable/)
- [Ansible Collections](https://docs.ansible.com/ansible/latest/collections/index.html)
- [Bindep Format](https://opendev.org/opendev/bindep)
