#!/usr/bin/env python3
"""Standalone Grok review support.

TODO: integrate with Grok's review lifecycle once its hook protocol is settled.
This module is not registered as a turn-end hook.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from turn_end import (
  CHILD_ENV, Change, Event, NoSnapshot, block, change_diff, load_changes,
  skip_gate, trim_out, write_text,
)

REVIEW_PASS = 'No issues.'
REVIEW_TIMEOUT = 240
REVIEW_CAP = 12000
REVIEW_FILE_CAP = 3000


def gate_review(root: str, event: Event, stdout, stderr) -> int:
  if skip_gate('review', event) or os.environ.get('GROK_HOOK_EVENT', '') == 'subagent_stop':
    return 0
  try:
    changes = load_changes(root, event)
  except NoSnapshot:
    return 0
  except OSError as err:
    write_text(stderr, f'{err}\n')
    return 1
  if not changes:
    return 0
  env = review_env()
  out, err = run_review(review_prompt(changes), env, root)
  secret = env.get('XAI_API_KEY', '')
  if isinstance(err, TimeoutError):
    return block(stdout, 'review timed out')
  if err is not None:
    detail = trim_out(out or str(err))
    return block(stdout, 'review failed:\n' + redact(detail, secret))
  text = out.strip()
  if text == '' or text == REVIEW_PASS:
    return 0
  return block(stdout, redact(trim_out(text), secret))


def review_prompt(changes: list[Change], *, complete: bool = False) -> str:
  parts = [
    'Review this turn diff. Output only finding lines, or exactly `No issues.`',
    'Format: `path:L<line>: problem. fix.`',
    'Do not edit files. Do not run tools.',
    'A missing diff is an omitted path, not a clean file.',
    '',
    'Files: ' + ', '.join(change.path for change in changes),
  ]
  if complete:
    parts.extend(['', ''.join(change_diff(change) for change in changes)])
    return '\n'.join(parts)
  rendered: list[tuple[str, str, bool]] = []
  for change in changes:
    diff, cut = cap_hunks(change.path, change_diff(change), REVIEW_FILE_CAP)
    rendered.append((change.path, diff, cut))
  truncated: list[str] = []
  included: list[str] = []
  omitted: list[str] = []
  budget = REVIEW_CAP
  for path, diff, cut in rendered:
    if len(diff) > budget:
      omitted.append(path)
      continue
    included.append(diff)
    budget -= len(diff)
    if cut:
      truncated.append(path)
  if truncated:
    parts.append('Truncated: ' + ', '.join(truncated))
  if omitted:
    parts.append('Omitted: ' + ', '.join(omitted))
  parts.append('')
  parts.append(''.join(included))
  return '\n'.join(parts)


def cap_hunks(path: str, diff: str, cap: int) -> tuple[str, bool]:
  if len(diff) <= cap:
    return diff, False
  header, hunks = split_hunks(diff)
  kept = header
  included = 0
  for hunk in hunks:
    if len(kept) + len(hunk) > cap:
      break
    kept += hunk
    included += 1
  note = f'... {path} hunks omitted\n'
  if included == 0 and hunks:
    room = max(cap - len(note), 0)
    return header + hunks[0][:room] + note, True
  if included < len(hunks) or not hunks:
    return kept + note, True
  return kept, False


def split_hunks(diff: str) -> tuple[str, list[str]]:
  header: list[str] = []
  hunks: list[str] = []
  current: list[str] = []
  for line in diff.splitlines(keepends=True):
    if line.startswith('@@'):
      if current:
        hunks.append(''.join(current))
      current = [line]
      continue
    if current:
      current.append(line)
    else:
      header.append(line)
  if current:
    hunks.append(''.join(current))
  return ''.join(header), hunks


def review_env() -> dict[str, str]:
  env = dict(os.environ)
  env[CHILD_ENV] = '1'
  if not env.get('XAI_API_KEY'):
    key = user_api_key()
    if key:
      env['XAI_API_KEY'] = key
  return env


def user_api_key() -> str:
  if os.name != 'nt':
    return ''
  try:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
      value, _ = winreg.QueryValueEx(key, 'XAI_API_KEY')
  except OSError:
    return ''
  if not isinstance(value, str):
    return ''
  return value


def run_review(prompt: str, env: dict[str, str], root: str) -> tuple[str, Exception | None]:
  if shutil.which('grok') is None:
    return '', OSError('grok is not on PATH')
  if not env.get('XAI_API_KEY'):
    return '', OSError('XAI_API_KEY is not set')
  try:
    out = subprocess.run(
      [
        'grok', '-p', prompt,
        '--max-turns', '1',
        '--output-format', 'plain',
        '--verbatim',
        '--disallowed-tools', 'Agent,search_replace,write,run_terminal_command',
      ],
      cwd=root,
      env=env,
      timeout=REVIEW_TIMEOUT,
      check=False,
      capture_output=True,
    )
  except subprocess.TimeoutExpired:
    return '', TimeoutError('review timed out')
  except OSError as err:
    return '', err
  text = (out.stdout + out.stderr).decode('utf-8', errors='replace')
  if out.returncode != 0:
    return text, OSError(f'exit {out.returncode}')
  return out.stdout.decode('utf-8', errors='replace'), None


def redact(text: str, secret: str) -> str:
  if secret:
    return text.replace(secret, '[redacted]')
  return text
