#!/usr/bin/env python3
"""Shared event, command parsing, and security-state helpers."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path


def protected_path(path: str) -> bool:
  base = path.replace('\\', '/').rsplit('/', 1)[-1].lower().strip('"\'(),;')
  return (
    base in {'.env', '.env.seed', '.env.local', '.env.development', '.env.production', '.env.test'}
    or bool(re.fullmatch(r'\.env\..+\.local', base))
    or base.endswith('.pem')
  )


def input_of(event: dict) -> dict:
  tool_input = event.get('toolInput') or event.get('tool_input') or {}
  return tool_input if isinstance(tool_input, dict) else {}


def command_of(event: dict) -> str:
  value = input_of(event).get('command')
  return value if isinstance(value, str) else ''


def ids_of(event: dict) -> tuple[str, str]:
  session = str(event.get('sessionId') or event.get('session_id') or '')
  prompt = str(event.get('promptId') or event.get('prompt_id') or '')
  return session, prompt


def split_segments(command: str) -> list[str]:
  parts: list[str] = []
  buf: list[str] = []
  quote = ''
  i = 0
  while i < len(command):
    ch = command[i]
    if quote:
      buf.append(ch)
      if ch == quote:
        quote = ''
      i += 1
      continue
    if ch in ('"', "'"):
      quote = ch
      buf.append(ch)
      i += 1
      continue
    if ch in ('\n', ';'):
      parts.append(''.join(buf))
      buf = []
      i += 1
      continue
    if ch == '&' and i + 1 < len(command) and command[i + 1] == '&':
      parts.append(''.join(buf))
      buf = []
      i += 2
      continue
    if ch == '|' and i + 1 < len(command) and command[i + 1] == '|':
      parts.append(''.join(buf))
      buf = []
      i += 2
      continue
    if ch == '|':
      parts.append(''.join(buf))
      buf = []
      i += 1
      continue
    buf.append(ch)
    i += 1
  parts.append(''.join(buf))
  return [part.strip() for part in parts if part.strip()]


def tokenize(segment: str) -> list[str]:
  tokens: list[str] = []
  buf: list[str] = []
  quote = ''
  for ch in segment:
    if quote:
      if ch == quote:
        quote = ''
      else:
        buf.append(ch)
      continue
    if ch in ('"', "'"):
      quote = ch
      continue
    if ch.isspace():
      if buf:
        tokens.append(''.join(buf))
        buf = []
      continue
    buf.append(ch)
  if buf:
    tokens.append(''.join(buf))
  return tokens


def state_root() -> Path:
  override = os.environ.get('GROK_TOOL_GATE_STATE')
  if override:
    return Path(override)
  return Path(tempfile.gettempdir()) / 'grok-tool-gate'


def state_path(session: str, prompt: str, name: str) -> Path:
  directory = state_root() / safe_key(session or 'no-session') / safe_key(prompt)
  directory.mkdir(parents=True, exist_ok=True)
  return directory / name


def safe_key(value: str) -> str:
  cleaned = re.sub(r'[^A-Za-z0-9_.-]', '_', value)
  cleaned = cleaned[:80]
  return cleaned if cleaned and cleaned not in ('.', '..') else 'empty'
