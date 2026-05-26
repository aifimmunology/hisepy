from pathlib import Path
from google import genai
import requests
import re
import os
import hisepy.common_utils as cu
from hisepy.auth import get_bearer_token_header

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))

def build_ray_transform_prompt(
    source_code: str,
    cpu_count: int = 1,
    gpu_count: int = 0,
    memory_size: int = 50,
    worker_count: int = 1,
) -> str:
    """
    Build a strong prompt for transforming Python code into a robust Ray implementation.

    Parameters
    ----------
    source_code : str
        Input Python source code to transform.
    cpu_count : int
        CPUs available per worker.
    gpu_count : int
        GPUs available per worker.
    memory_size : int
        Memory available per worker in GB.
    worker_count : int
        Number of workers in the cluster.
    """
    total_cpu = cpu_count * worker_count
    total_gpu = gpu_count * worker_count
    total_memory = memory_size * worker_count

    gpu_concurrency_hint = max(1, total_gpu) if total_gpu > 0 else 1
    cpu_concurrency_hint = max(1, total_cpu)

    prompt = CONFIG["AI_PROMPT"]["TRANSFORM"].format(source_code=source_code,
        total_cpu=total_cpu,
        total_gpu=total_gpu,
        cpu_count=cpu_count,
        gpu_count=gpu_count,
        memory_size=total_memory,
        worker_count=worker_count,
        gpu_concurrency_hint=gpu_concurrency_hint,
        cpu_concurrency_hint=cpu_concurrency_hint,
    )
    return prompt.strip()


def transform_to_ray(input_path : str,
                     output_path : str,
                     cpu_count: int = None,
                     gpu_count: int = None,
                     memory_size : int = 100,
                     worker_count : int = 1) -> None:


    client_secret_resp = cu.parse_hise_response(
            requests.get(
                cu.hise_url('job_orchestrate', 'genai_client_secret'),
                            headers=get_bearer_token_header()))
    os.environ["GOOGLE_API_KEY"] = client_secret_resp
    client = genai.Client()
    source = Path(input_path).read_text(encoding="utf-8")

    prompt = build_ray_transform_prompt(
        source_code=source,
        cpu_count=cpu_count,
        gpu_count=gpu_count,
        memory_size=memory_size,
        worker_count=worker_count,
    )
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    text = response.text.strip()

    match = re.search(r"```python\s*(.*?)```", text, flags=re.DOTALL)
    if match:
        text = match.group(1).strip()
    else:
        match = re.search(r"```(.*?)```", text, flags=re.DOTALL)
        if match:
            text = match.group(1).strip()

    Path(output_path).write_text(text + "\n", encoding="utf-8")
    print("Wrote output_ray.py")
    return 



