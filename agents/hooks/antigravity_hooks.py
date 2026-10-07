#!/usr/bin/env python3
"""Adapt Antigravity events to shared policies; run stop checks in order."""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import tool_gate
import turn_end


def normalize(raw: dict, event_name: str = '') -> dict:
  event = dict(raw)
  name = event_name
  if not name:
    if 'terminationReason' in raw or 'fullyIdle' in raw:
      name = 'Stop'
    elif 'toolCall' in raw:
      name = 'PreToolUse'
    elif 'stepIdx' in raw:
      name = 'PostToolUse'
    else:
      name = str(raw.get('hook_event_name') or raw.get('hookEventName') or '')

  session = 'antigravity-' + str(raw.get('conversationId') or raw.get('sessionId') or '')
  turn = str(raw.get('stepIdx') or raw.get('promptId') or '')

  state = tool_gate.state_path(session, 'session', 'continuation.json')
  try:
    pending = json.loads(state.read_text(encoding='utf-8'))
  except (OSError, ValueError):
    pending = {}

  if pending and pending.get('turn') == turn:
    turn = pending.get('origin', turn)

  event['sessionId'] = session
  event['promptId'] = turn
  event['client'] = 'antigravity'
  event['hook_event_name'] = name

  workspace_paths = raw.get('workspacePaths')
  if isinstance(workspace_paths, list) and workspace_paths:
    event['cwd'] = str(workspace_paths[0])
  elif isinstance(raw.get('cwd'), str):
    event['cwd'] = raw['cwd']
  else:
    event['cwd'] = os.getcwd()

  tool_call = raw.get('toolCall') or {}
  tool = str(tool_call.get('name') or raw.get('toolName') or raw.get('tool_name') or '')
  args = tool_call.get('args') or raw.get('toolInput') or raw.get('tool_input') or {}
  if not isinstance(args, dict):
    args = {}

  if tool.startswith('mcp__'):
    tool = tool[5:]
  tool = {'fff__ffgrep': 'fff__grep', 'fff__fff-multi-grep': 'fff__multi_grep'}.get(tool, tool)

  if tool == 'run_command':
    event['toolName'] = 'run_terminal_command'
    cmd = str(args.get('CommandLine') or args.get('command') or args.get('cmd') or '')
    event['tool_input'] = {'command': cmd}
  elif tool in ('replace_file_content', 'write_to_file'):
    event['toolName'] = 'write'
    target = str(args.get('TargetFile') or args.get('target_file') or args.get('file_path') or '')
    event['tool_input'] = {'file_path': target}
  elif tool == 'view_file':
    event['toolName'] = 'read_file'
    target = str(args.get('AbsolutePath') or args.get('file_path') or '')
    event['tool_input'] = {'file_path': target}
  else:
    event['toolName'] = tool
    event['tool_input'] = args

  return event


def remember_block(event: dict, result: dict) -> dict:
  if result.get('decision') == 'continue':
    state = tool_gate.state_path(event['sessionId'], 'session', 'continuation.json')
    try:
      previous = json.loads(state.read_text(encoding='utf-8'))
    except (OSError, ValueError):
      previous = {}
    reason = str(result.get('reason') or '')
    repeats = previous.get('repeats', 0) + 1 if previous.get('reason') == reason else 1
    state.write_text(json.dumps({
      'origin': event['promptId'],
      'turn': event.get('stepIdx', event.get('promptId', '')),
      'reason': reason,
      'repeats': repeats,
    }), encoding='utf-8')
    if repeats >= 3:
      return {}
  return result


def secret_paths(event: dict) -> bool:
  data = tool_gate.input_of(event)
  paths = []
  for key in ('file_path', 'path', 'target_file', 'relative_path', 'file', 'paths', 'TargetFile', 'AbsolutePath'):
    value = data.get(key)
    paths.extend(value if isinstance(value, list) else [value])
  if event.get('toolName') == 'run_terminal_command':
    paths.extend(tool_gate.tokenize(tool_gate.command_of(event)))
  for path in paths:
    if not isinstance(path, str):
      continue
    if turn_end.protected_path(path):
      return True
  return False


def tool_policy(event: dict) -> dict:
  name = event.get('hook_event_name')
  tool = event.get('toolName')
  if name == 'PreToolUse' and secret_paths(event):
    return {'decision': 'deny', 'reason': 'Protected .env or PEM path. Use a redacted example file.'}
  if name == 'PostToolUse' and event.get('raw', {}).get('error'):
    return {}
  if tool == tool_gate.GK_BRANCH:
    return {}
  result = tool_gate.handle(event)
  if tool in tool_gate.FFF_GREP and result:
    session, prompt = tool_gate.ids_of(event)
    try:
      count = tool_gate.state_path(session, prompt, 'fff-grep.count').read_text(encoding='utf-8')
    except (OSError, ValueError):
      count = '0'
    if count == '3':
      return tool_gate.note('Three text searches. Read the owning file or delegate broad localization to cavecrew-investigator.')
    return {}
  return result


def snapshot_event(event: dict) -> turn_end.Event:
  return turn_end.parse_event(event)


def ensure_snapshot(event: dict, force: bool = False) -> dict:
  parsed = snapshot_event(event)
  root = turn_end.workspace(parsed)
  if not event['promptId']:
    return {}
  cursor = tool_gate.state_path(event['sessionId'], 'session', 'latest.json')
  cursor.write_text(json.dumps({'prompt': event['promptId'], 'cwd': root}), encoding='utf-8')
  path = turn_end.snapshot_path(root, parsed)
  if not force and os.path.isfile(path):
    return {}
  try:
    turn_end.ensure_git(root)
    errors = io.StringIO()
    if turn_end.write_snapshot(root, parsed, errors):
      return {'decision': 'continue', 'reason': errors.getvalue().strip()}
  except Exception:
    return {}
  return {}


def run_stage(mode: str, event: dict) -> dict:
  output, errors = io.StringIO(), io.StringIO()
  status = turn_end.run([mode], io.StringIO(json.dumps(event)), output, errors)
  if status:
    return {'decision': 'continue', 'reason': errors.getvalue().strip() or f'{mode} hook failed'}
  res = json.loads(output.getvalue()) if output.getvalue().strip() else {}
  if res.get('decision') == 'block':
    return {'decision': 'continue', 'reason': res.get('reason', '')}
  return res


def changes_key(changes: list[turn_end.Change]) -> str:
  return hashlib.sha256(turn_end.encode_json({
    change.path: [change.before, change.after, change.before_deleted, change.after_deleted]
    for change in changes
  })).hexdigest()


def stop(event: dict) -> dict:
  session, prompt = tool_gate.ids_of(event)
  if prompt and tool_gate.state_path(session, prompt, 'gopls-edited').exists():
    if not tool_gate.state_path(session, prompt, 'gopls-diag').exists():
      return {'decision': 'continue', 'reason': tool_gate.GO_DIAG_BLOCK}
  result = run_stage('format', event)
  if result:
    return result
  parsed = snapshot_event(event)
  root = turn_end.workspace(parsed)
  try:
    turn_end.ensure_git(root)
    changes = turn_end.load_changes(root, parsed)
  except (turn_end.NotGit, turn_end.NoSnapshot):
    return {}
  if not changes:
    return {}
  changes = [change for change in changes if not turn_end.protected_path(change.path)]
  if not changes:
    return {}
  digest = changes_key(changes)
  for mode in ('test', 'review'):
    cache = tool_gate.state_path(session, prompt, mode + '.passed')
    if cache.exists() and cache.read_text(encoding='utf-8') == digest:
      continue
    result = run_stage(mode, event)
    if result:
      return result
    cache.write_text(digest, encoding='utf-8')
  return {}


def dispatch(raw: dict, event_name: str = '') -> dict:
  if os.environ.get(turn_end.CHILD_ENV) == '1':
    return {}
  event = normalize(raw, event_name)
  name = event.get('hook_event_name')

  if name == 'PreToolUse':
    ensure_snapshot(event)
    result = tool_policy(event)
    if result.get('decision') == 'deny':
      return {
        'decision': 'deny',
        'reason': result.get('reason', 'Operation denied by policy.'),
      }
    if result.get('decision') == 'ask':
      return {
        'decision': 'ask',
        'reason': result.get('reason', ''),
      }
    return {'decision': 'allow'}

  if name == 'PostToolUse':
    tool_policy(event)
    return {}

  if name == 'Stop':
    return remember_block(event, stop(event))

  return {}


def main() -> int:
  event_name = sys.argv[1] if len(sys.argv) > 1 else ''
  raw_text = sys.stdin.read()
  try:
    raw = json.loads(raw_text) if raw_text.strip() else {}
  except json.JSONDecodeError:
    raw = {}
  result = dispatch(raw, event_name)
  if result:
    json.dump(result, sys.stdout)
    sys.stdout.write('\n')
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
