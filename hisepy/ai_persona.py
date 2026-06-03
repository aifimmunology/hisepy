import json
import os
import shutil
import yaml
import hisepy.common_utils as cu

# directory of hisepy package
_here = os.path.abspath(os.path.dirname(__file__))

def read_yaml(file_path):
    with open(file_path, "r") as f:
        return yaml.safe_load(f)


CONFIG = read_yaml('{}/config.yaml'.format(_here))

def initialize_ai_persona(
    name: str,
    api_key: str,
    sys_prompt: str,
    description: str,
    image: str,
):
    """
    Initialize an AI persona from a template.

    Parameters
    name : str
        Persona display name.

    api_key : str
        Gemini API key.

    sys_prompt : str
        System prompt for the persona.

    description : str
        Persona description.

    image : str
        Path to avatar image.
    """

    # Make API key available to Gemini
    os.environ["GEMINI_API_KEY"] = api_key

    # Create persona directory
    personas_dir = "/home/workspace/.jupyter/personas"
    os.makedirs(personas_dir, exist_ok=True)

    # Locate template
    hisepy_version = cu.get_sdk_version()

    persona_template_file = (
        f"{CONFIG['STORES']['SDK_STORE']}"
        f"/hisepy_{hisepy_version}/scripts/persona_template.py"
    )

    destination_file = (
        f"{personas_dir}/{name.lower().replace(' ', '_')}_persona.py"
    )

    # Copy template
    shutil.copy2(persona_template_file, destination_file)

    # Read copied template
    with open(destination_file, "r", encoding="utf-8") as f:
        content = f.read()

    avatar_path = image if image else None

    replacements = {
        "{{PERSONA_NAME}}": name,
        "{{PERSONA_DESCRIPTION}}": description,
        "{{SYSTEM_PROMPT_JSON}}": json.dumps(sys_prompt),
        "{{AVATAR_PATH_JSON}}": json.dumps(avatar_path),
    }

    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)

    # Write populated persona
    with open(destination_file, "w", encoding="utf-8") as f:
        f.write(content)

    return destination_file