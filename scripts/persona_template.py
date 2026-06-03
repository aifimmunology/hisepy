from __future__ import annotations

import os

from google import genai
from jupyter_ai_persona_manager import (
    BasePersona,
    PersonaDefaults,
)

from jupyterlab_chat.models import Message


AVATAR_PATH = {{AVATAR_PATH_JSON}}


class HISEIDEAI(BasePersona):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = genai.Client()

    # =====================================================
    # Persona metadata
    # =====================================================

    @property
    def defaults(self):
        return PersonaDefaults(
            name="{{PERSONA_NAME}}",
            description="{{PERSONA_DESCRIPTION}}",
            avatar_path=AVATAR_PATH,
            system_prompt={{SYSTEM_PROMPT_JSON}},
        )

    # =====================================================
    # Chat handler
    # =====================================================

    async def process_message(self, message: Message):
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            config={
                "system_instruction": self.defaults.system_prompt,
            },
            contents=message.body,
        )

        self.send_message(response.text)