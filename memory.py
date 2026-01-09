from __future__ import annotations
from typing import Dict

Message = Dict[str, str] # {"role": "user"|"assistant"|"system", "content": "..."}

class ChannelMemory:
    def __init__(self, system_message: Message, keep_turns: int = 15):
        if system_message.get("role") != "system":
            raise ValueError("system_message must have role 'system'")
        if "content" not in system_message:
            raise ValueError("system_message must have 'content' field")
        
        self._system_message = dict(system_message)
        self._keep_turns = keep_turns
        self._histories: Dict[int, list[Message]] = {}

    def get(self, channel_id: int) -> list[Message]:
        if channel_id not in self._histories:
            self._histories[channel_id] = [dict(self._system_message)]
        return self._histories[channel_id]
    
    def reset(self, channel_id: int):
        self._histories[channel_id] = [dict(self._system_message)]

    def _trim_turns(self, channel_id: int):
        history = self.get(channel_id)
        max_messages = self._keep_turns * 2 + 1
        if len(history) > max_messages:
            self._histories[channel_id] = [history[0]] + history[-(max_messages - 1):]

    def _append(self, channel_id: int, role: str, content: str):
        self.get(channel_id).append({"role": role, "content": content})

    def append_user(self, channel_id: int, content: str):
        self._append(channel_id, "user", content)

    def append_assistant(self, channel_id: int, content: str):
        self._append(channel_id, "assistant", content)
        self._trim_turns(channel_id)

    
