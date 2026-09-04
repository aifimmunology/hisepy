# hisepy

Python interface to the Allen Institute for Immunology's Human Immune System Explorer (HISE).

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Requirements](#requirements)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Working with Files](#working-with-files)
  - [Querying Files](#querying-files)
  - [Uploading Files](#uploading-files)
  - [Training Jobs](#training-jobs)
  - [Project Stores and Folders](#project-stores-and-folders)
  - [Visualizations](#visualizations)
  - [Private Folders](#private-folders)
- [Development](#development)
- [Contributing](#contributing)

## Overview

`hisepy` is the Python SDK for interacting with HISE (Human Immune System Explorer), the Allen Institute for Immunology's data platform. It provides tools to read, query, upload, and manage immunology datasets and analysis results stored in HISE.

## Installation

Install from PyPI:

```bash
pip install hisepy
```

Or install from source:

```bash
git clone https://github.com/aifimmunology/hisepy.git
cd hisepy
pip install .
```

**Python 3.9 or higher is required.**

## Requirements

Key dependencies (pinned versions in `requirements.txt`):

- `pandas >= 2.2.3`
- `numpy >= 1.26.4`
- `ray[default] >= 2.44.1`
- `google-cloud-storage >= 2.16.0`
- `plotly >= 5.23.0`
- `dash >= 2.17.0`
- `h5py >= 3.12.1`

See [`requirements.txt`](requirements.txt) for the full pinned dependency list.

## Configuration

### Environment Variables

The following environment variables configure HISE API access:

| Variable | Description | Required |
|---|---|---|
| `TOKEN_GENERATOR` | Path to the hisecli auth command, e.g. `/path/to/hisecli auth` | Yes |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to the GCP service account credentials JSON file | Yes |
| `TEST_TOOLCHAIN_SERVER` | Override toolchain server (e.g. `localhost:2082` for local dev) | No |
| `TEST_HYDRATION_SERVER` | Override hydration server (e.g. `localhost:6080`) | No |
| `TEST_TRACER_SERVER` | Override tracer server (e.g. `localhost:8081`) | No |
| `TEST_SCHEDULER_NOTEBOOK` | Fake notebook name for local scheduler testing | No |
| `TEST_INSTANCE_NAME` | Override instance name (defaults to `local-testing-instance`) | No |

Set the required variables before using the SDK:

```bash
export TOKEN_GENERATOR="/path/to/hisecli auth"
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/credentials.json"
```

### Local Development Setup

To point the SDK at locally running services:

```bash
export TEST_TOOLCHAIN_SERVER=localhost:2082
export TEST_HYDRATION_SERVER=localhost:6080
export TEST_TRACER_SERVER=localhost:8081
```

## Usage

```python
import hisepy as hp
```

### Working with Files

Read a single file by its HISE file ID:

```python
# Object-oriented interface
my_file = hp.hise_file("9f6d7ab5-1c7b-4709-9455-3d8ff3fbb6c8")
my_file.status        # True/False: whether the file is downloaded locally
my_file.load()        # download the file
my_file.path          # local path where the file was saved
my_file.descriptors   # metadata descriptors for the file
```

Read multiple files at once:

```python
files = hp.read_files([
    "246528ce-593d-4106-80d6-735bdb8ee35d",
    "f7081d4a-8e9e-42a2-a899-335384e37d78",
    "c53e8d62-141c-413b-94e4-9e9b55510ce8",
])
```

Get file descriptors without downloading:

```python
descriptors = hp.get_file_descriptors(["246528ce-593d-4106-80d6-735bdb8ee35d"])
```

### Querying Files

Look up queryable fields and filter files:

```python
# See what fields you can query on
hp.lookup_queryable_fields("file")

# Find unique values for a field
hp.lookup_unique_entries("file", "fileType")

# Query files matching criteria
files = hp.get_files_for_query({"fileType": "scRNA-seq-labeled"})

# Object-oriented query interface
results = hp.query_files({"fileType": "scRNA-seq-labeled"})
```

### Uploading Files

```python
# Upload one or more files to HISE
hp.upload_files(["results/output.h5ad", "results/summary.csv"])

# Upload using a map of file paths to metadata
hp.upload_file_map({
    "results/output.h5ad": {"description": "Processed scRNA-seq data"},
})

# Set a default project/store for uploads
hp.set_default_store("my-store-id")
hp.set_default_project("my-project-id")
```

### Training Jobs

Submit a Python script or notebook to run on a remote Ray or Beaker cluster:

```python
# Minimal example — Ray is the default provider
response = hp.start_training_run(
    training_job_file_path="/home/workspace/my_jobs/train.py",
    title="My Training Job",
    description="Runs heavy analysis on the input file set",
    file_set_id="fileset-id",
)
# response keys: workflowName, executionId, status, message,
#                providerDashboard, executionDetails

# Scale up with more resources and helper files
response = hp.start_training_run(
    training_job_file_path="/home/workspace/my_jobs/train.py",
    title="Large Training Job",
    description="Multi-worker GPU run",
    file_set_id="fileset-id",
    head_cpu_count=4,
    head_memory_size=32,
    worker_count=2,
    worker_cpu_count=8,
    worker_gpu_count=1,
    worker_memory_size=64,
    additional_dirs=["/home/workspace/my_jobs/helpers"],
    additional_files=["/home/workspace/configs/config.json"],
)

# Use the Beaker provider instead of Ray
response = hp.start_training_run(
    training_job_file_path="/home/workspace/my_jobs/train.py",
    title="Beaker Job",
    description="Run on Beaker cluster",
    file_set_id="fileset-id",
    provider="beaker",
)
```

**Key parameters for `start_training_run`:**

| Parameter | Default | Description |
|---|---|---|
| `training_job_file_path` | — | Path to `.py` or `.ipynb` script |
| `title` | — | Human-readable job title |
| `description` | — | Job description |
| `file_set_id` | — | Input file set ID |
| `provider` | `"ray"` | `"ray"` or `"beaker"` |
| `head_cpu_count` | `1` | CPUs on the Ray head node |
| `head_gpu_count` | `0` | GPUs on the Ray head node |
| `head_memory_size` | `10` | Head node memory (GB) |
| `worker_count` | `0` | Number of Ray worker nodes |
| `worker_cpu_count` | `1` | CPUs per worker |
| `worker_gpu_count` | `0` | GPUs per worker |
| `worker_memory_size` | `10` | Memory per worker (GB) |
| `additional_dirs` | `[]` | Extra directories to bundle |
| `additional_files` | `[]` | Extra files to bundle |
| `requirements_file_path` | `None` | Path to `requirements.in` |
| `image_id` | `None` | Custom container image ID |
| `use_conda` | `False` | Use conda env instead of pip |
| `output_file_size` | `5` | Estimated output size (GB) |

Once a job completes, review and approve or reject its output:

```python
hp.review_training_job_run(
    job_id="execution-id",
    study_space_id="study-space-id",
    review_notes="Results look correct, approving.",
)
# Returns: dict with keys: job, approved, message
```

### Project Stores and Folders

```python
# List available project stores
stores = hp.list_project_stores()

# List files in a store
files = hp.list_files_in_project_store("store-id")

# Download from a store
hp.download_from_project_store("file-id", "store-id")

# Manage project folders
folders = hp.list_project_folders()
hp.list_files_in_project_folder("folder-id")
hp.download_from_project_folder("file-id", "folder-id")
```

### Visualizations

```python
# Save a static image
hp.save_static_image(fig, "my_plot.png")

# Save an interactive Plotly visualization
hp.save_visualization(fig, "my_viz")

# Load a previously saved visualization
fig = hp.load_visualization("viz-id")

# Save a Dash app
hp.save_dash_app(app, "my-app")
```

### Private Folders

```python
# List all files across private folders
hp.list_files_in_all_private_folders()

# Upload to a private folder
hp.upload_file_to_private_folder("file.csv", "folder-id")

# Download from a private folder
hp.download_from_private_folder("file-id", "folder-id")

# Move or rename files
hp.move_file_in_private_folder("file-id", "source-folder", "dest-folder")
hp.rename_file_in_private_folder("file-id", "folder-id", "new-name.csv")
```

## Development

### Setup

```bash
git clone https://github.com/aifimmunology/hisepy.git
cd hisepy
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
pre-commit install
```

### Running Tests

```bash
pytest tests/
```

### Building

```bash
python3 setup.py build
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development environment setup, coding conventions, and the pull request process.
