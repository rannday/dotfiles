#!/usr/bin/env python3
"""Deny shell git, built-in grep, local-tree GitHub reads, gk branch create, Serena .go rename, and a .go edit with no prior gopls refs.

Stop blocks when that edit has no gopls diagnostics after it.
Exit 0. A non-zero exit keeps a deny and drops additionalContext.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DENY_VERBS = {
  'status': 'gk__git_status',
  'diff': 'gk__git_log_or_diff',
  'log': 'gk__git_log_or_diff',
  'show': 'gk__git_log_or_diff',
  'branch': 'gk__git_branch',
  'blame': 'gk__git_blame',
  'add': 'gk__git_add',
  'commit': 'gk__git_commit',
  'push': 'gk__git_push',
  'fetch': 'gk__git_fetch',
  'pull': 'gk__git_pull',
  'stash': 'gk__git_stash',
  'checkout': 'gk__git_checkout',
  'switch': 'gk__git_checkout',
  'restore': 'gk__git_checkout',
}
NO_GK = ('merge', 'rebase')
TAKES_ARG = {
  '-C',
  '-c',
  '--git-dir',
  '--work-tree',
  '--namespace',
  '--super-prefix',
  '--config-env',
  '--exec-path',
}
GIT_NAMES = {'git', 'git.exe'}
FFF_GREP = {'fff__grep', 'fff__multi_grep'}
GITHUB_TREE = {'github__get_file_contents', 'github__search_code'}
GOPLS_REFS = 'gopls__go_symbol_references'
GOPLS_DIAG = 'gopls__go_diagnostics'
GOPLS_RECORD = {GOPLS_REFS, GOPLS_DIAG}
EDIT_TOOLS = {'search_replace', 'write'}
SERENA_EDIT = {
  'serena__replace_symbol_body',
  'serena__insert_before_symbol',
  'serena__insert_after_symbol',
  'serena__rename_symbol',
  'serena__safe_delete_symbol',
  'serena__replace_content',
  'serena__replace_in_files',
}
GO_EDIT_TOOLS = EDIT_TOOLS | SERENA_EDIT
GREP_REASON = (
  'Use fff__grep or fff__multi_grep, one bare identifier. '
  'If fff errors, say fff is down. Do not use the built-in grep tool.'
)
FFF_NUDGE = (
  'Stop searching. Spawn cavecrew-investigator. '
  'Do not call fff__grep or fff__multi_grep again this turn.'
)
GO_REFS_DENY = (
  'No gopls__go_symbol_references before this .go edit. '
  'Call it before changing a definition.'
)
GO_RENAME_DENY = (
  'serena__rename_symbol is denied for a .go path. '
  'Use gopls__go_rename_symbol.'
)
GO_DIAG_BLOCK = (
  'No gopls__go_diagnostics after this .go edit. '
  'Call it on the edited paths before finish.'
)
GITHUB_LOCAL_DENY = (
  'Do not read the local tree through github. '
  'Use fff and gk for this checkout.'
)
GK_BRANCH = 'gk__git_branch'
BRANCH_CREATE_DENY = (
  'gk__git_branch action create is denied. '
  'Confirm in chat before creating a branch.'
)
REMOTE_URL = re.compile(
  r'(?:git@[^:\s]+:|ssh://(?:git@)?[^/\s]+/|https?://[^/\s]+/|git://[^/\s]+/)'
  r'([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?=\s|$)',
  re.IGNORECASE,
)
REPO_QUALIFIER = re.compile(
  r'(?:^|[\s"\'])repo:([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)',
  re.IGNORECASE,
)


def main() -> int:
  raw = sys.stdin.read()
  try:
    event = json.loads(raw) if raw.strip() else {}
  except json.JSONDecodeError:
    event = {}
  if not isinstance(event, dict):
    event = {}
  result = handle(event)
  if result:
    json.dump(result, sys.stdout)
    sys.stdout.write('\n')
  return 0


def handle(event: dict) -> dict:
  name = str(event.get('hook_event_name') or event.get('hookEventName') or '')
  tool = str(event.get('toolName') or event.get('tool_name') or '')
  session, prompt = ids_of(event)
  if name in ('PreToolUse', 'pre_tool_use'):
    if tool == 'run_terminal_command':
      return gate_git(command_of(event))
    if tool in ('grep', 'Grep'):
      return {'decision': 'deny', 'reason': GREP_REASON}
    if tool in GO_EDIT_TOOLS:
      return gate_go_pre(session, prompt, tool, event)
    if tool in GITHUB_TREE:
      return gate_github(tool, event)
    if tool == GK_BRANCH:
      return gate_branch(event)
    return {'decision': 'allow'}
  if name in ('PostToolUse', 'post_tool_use'):
    if tool in FFF_GREP:
      return gate_fff(session, prompt)
    if tool in GOPLS_RECORD:
      return record_gopls(session, prompt, tool)
    if tool in GO_EDIT_TOOLS:
      return gate_go(session, prompt, tool, event)
  if name in ('Stop', 'stop', 'SubagentStop', 'subagent_stop'):
    return gate_go_stop(event)
  return {}


def gate_git(command: str) -> dict:
  if not command.strip():
    return {'decision': 'allow'}
  for segment in split_segments(command):
    tokens = tokenize(segment)
    while tokens and tokens[0] == '&':
      tokens = tokens[1:]
    for index, token in enumerate(tokens):
      if not is_git(token):
        continue
      parsed = verb_after(tokens, index)
      if parsed is None:
        break
      verb, _rest = parsed
      if verb == 'remote':
        break
      if verb in DENY_VERBS:
        return {'decision': 'deny', 'reason': f'Shell git {verb} is denied. Use {DENY_VERBS[verb]}.'}
      if verb in NO_GK:
        return {
          'decision': 'deny',
          'reason': f'Shell git {verb} is denied. gk has no {verb} tool.',
        }
      break
  return {'decision': 'allow'}


def gate_branch(event: dict) -> dict:
  action = input_of(event).get('action')
  if isinstance(action, str) and action.strip().lower() == 'create':
    return {'decision': 'deny', 'reason': BRANCH_CREATE_DENY}
  return {'decision': 'allow'}


def gate_github(tool: str, event: dict) -> dict:
  pairs = github_pairs(tool, event)
  if not pairs:
    return {'decision': 'allow'}
  # Unknown checkout stays allowed. A static deny would block other remotes.
  if pairs & local_remotes(workspace_of(event)):
    return {'decision': 'deny', 'reason': GITHUB_LOCAL_DENY}
  return {'decision': 'allow'}


def github_pairs(tool: str, event: dict) -> set[tuple[str, str]]:
  tool_input = input_of(event)
  if tool == 'github__search_code':
    query = tool_input.get('query')
    if not isinstance(query, str):
      return set()
    return pairs_of_query(query)
  owner = tool_input.get('owner')
  repo = tool_input.get('repo')
  if not isinstance(owner, str) or not isinstance(repo, str):
    return set()
  pair = repo_pair(owner, repo)
  return {pair} if pair else set()


def pairs_of_query(query: str) -> set[tuple[str, str]]:
  found: set[tuple[str, str]] = set()
  for match in REPO_QUALIFIER.finditer(query):
    pair = repo_pair(match.group(1), match.group(2))
    if pair:
      found.add(pair)
  return found


def repo_pair(owner: str, repo: str) -> tuple[str, str] | None:
  owner = owner.strip().lower()
  repo = repo.strip().lower()
  repo = repo.removesuffix('.git')
  if not owner or not repo or '/' in owner or '/' in repo:
    return None
  return owner, repo


def remotes_of(text: str) -> set[tuple[str, str]]:
  found: set[tuple[str, str]] = set()
  for match in REMOTE_URL.finditer(text):
    pair = repo_pair(match.group(1), match.group(2))
    if pair:
      found.add(pair)
  return found


def local_remotes(cwd: str) -> set[tuple[str, str]]:
  if not cwd.strip():
    return set()
  try:
    result = subprocess.run(
      ['git', 'remote', '-v'],
      cwd=cwd,
      capture_output=True,
      text=True,
      timeout=5,
      check=False,
    )
  except (OSError, subprocess.TimeoutExpired):
    return set()
  if result.returncode != 0:
    return set()
  return remotes_of(result.stdout)


def workspace_of(event: dict) -> str:
  for key in ('cwd', 'workspaceRoot', 'workspace_root'):
    value = event.get(key)
    if isinstance(value, str) and value.strip():
      return value.strip()
  for value in (
    os.environ.get('GROK_WORKSPACE_ROOT', ''),
    os.environ.get('CLAUDE_PROJECT_DIR', ''),
  ):
    if value.strip():
      return value.strip()
  return os.getcwd()


def gate_fff(session: str, prompt: str) -> dict:
  if not prompt:
    return {}
  if bump(session, prompt) >= 3:
    return note(FFF_NUDGE)
  return {}


def record_gopls(session: str, prompt: str, tool: str) -> dict:
  if not prompt:
    return {}
  if tool == GOPLS_REFS:
    state_path(session, prompt, 'gopls-refs').write_text('1', encoding='utf-8')
  elif tool == GOPLS_DIAG and state_path(session, prompt, 'gopls-edited').exists():
    # A diagnostics call before the edit does not count as after.
    state_path(session, prompt, 'gopls-diag').write_text('1', encoding='utf-8')
  return {}


def gate_go_pre(session: str, prompt: str, tool: str, event: dict) -> dict:
  # Go rename stays on gopls even after refs. Non-go rename stays allowed.
  if tool == 'serena__rename_symbol' and is_go_path(file_path_of(event)):
    return {'decision': 'deny', 'reason': GO_RENAME_DENY}
  if not prompt or not touches_go(tool, event):
    return {'decision': 'allow'}
  if state_path(session, prompt, 'gopls-refs').exists():
    return {'decision': 'allow'}
  return {'decision': 'deny', 'reason': GO_REFS_DENY}


def gate_go(session: str, prompt: str, tool: str, event: dict) -> dict:
  if not prompt or not touches_go(tool, event):
    return {}
  state_path(session, prompt, 'gopls-edited').write_text('1', encoding='utf-8')
  diag = state_path(session, prompt, 'gopls-diag')
  if diag.exists():
    diag.unlink()
  return {}


def touches_go(tool: str, event: dict) -> bool:
  tool_input = input_of(event)
  if tool == 'serena__replace_in_files':
    if tool_input.get('dry_run') is True:
      return False
    path = file_path_of(event)
    if is_go_path(path):
      return True
    exclude = text_of(tool_input.get('paths_exclude_glob'))
    if exclude_blocks_go(exclude):
      return False
    if is_single_non_go_file(path):
      return False
    include = text_of(tool_input.get('paths_include_glob'))
    return not (include and not glob_matches_go(include))
  return is_go_path(file_path_of(event))


def is_go_path(path: str) -> bool:
  return path.replace('\\', '/').rstrip('/').lower().endswith('.go')


def is_single_non_go_file(path: str) -> bool:
  if not path:
    return False
  normalized = path.replace('\\', '/').rstrip('/')
  base = normalized.rsplit('/', 1)[-1]
  if not base or '.' not in base:
    return False
  return not base.lower().endswith('.go')


def exclude_blocks_go(glob: str) -> bool:
  return glob.replace('\\', '/').strip().lower() in {'*.go', '**/*.go'}


def glob_matches_go(glob: str) -> bool:
  text = glob.replace('\\', '/').strip().lower()
  if not text or '.go' in text:
    return True
  last = text.rstrip('/').rsplit('/', 1)[-1]
  pinned = re.fullmatch(r'\*\.([a-z0-9]+)', last)
  if pinned:
    return pinned.group(1) == 'go'
  braced = re.fullmatch(r'\*\.\{([a-z0-9,]+)\}', last)
  if braced:
    return 'go' in braced.group(1).split(',')
  return True


def text_of(value: object) -> str:
  return value if isinstance(value, str) else ''


def gate_go_stop(event: dict) -> dict:
  name = str(event.get('hook_event_name') or event.get('hookEventName') or '')
  reason = str(event.get('reason') or '')
  # Session-end Stop is not a finish. SubagentStop still gates.
  if name in ('Stop', 'stop') and reason and reason != 'end_turn':
    return {}
  session, prompt = ids_of(event)
  if not prompt or not state_path(session, prompt, 'gopls-edited').exists():
    return {}
  missing = []
  if not state_path(session, prompt, 'gopls-refs').exists():
    missing.append(GO_REFS_DENY)
  if not state_path(session, prompt, 'gopls-diag').exists():
    missing.append(GO_DIAG_BLOCK)
  if not missing:
    return {}
  return {'decision': 'block', 'reason': ' '.join(missing)}


def note(text: str) -> dict:
  return {
    'hookSpecificOutput': {
      'hookEventName': 'PostToolUse',
      'additionalContext': text,
    }
  }


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


def file_path_of(event: dict) -> str:
  tool_input = input_of(event)
  for key in ('file_path', 'path', 'target_file', 'relative_path'):
    value = tool_input.get(key)
    if isinstance(value, str) and value:
      return value
  return ''


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


def is_git(token: str) -> bool:
  name = token.replace('\\', '/').rstrip('/').rsplit('/', 1)[-1].lower()
  return name in GIT_NAMES


def verb_after(tokens: list[str], start: int) -> tuple[str, list[str]] | None:
  i = start + 1
  while i < len(tokens):
    tok = tokens[i]
    if tok == '--':
      i += 1
      break
    if tok.startswith('-'):
      body = tok.split('=', 1)[0]
      if '=' not in tok and body in TAKES_ARG:
        i += 2
        continue
      i += 1
      continue
    return tok.lower(), tokens[i + 1:]
  if i < len(tokens) and not tokens[i].startswith('-'):
    return tokens[i].lower(), tokens[i + 1:]
  return None


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
  return cleaned[:80] or 'empty'


def bump(session: str, prompt: str) -> int:
  path = state_path(session, prompt, 'fff-grep.count')
  lock = path.with_name('fff-grep.lock')
  locked = False
  for _ in range(50):
    try:
      fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
      time.sleep(0.01)
      continue
    os.close(fd)
    locked = True
    break
  try:
    count = 0
    if path.exists():
      text = path.read_text(encoding='utf-8').strip()
      count = int(text) if text.isdigit() else 0
    count += 1
    path.write_text(str(count), encoding='utf-8')
    return count
  finally:
    if locked:
      try:
        lock.unlink()
      except OSError:
        pass


if __name__ == '__main__':
  sys.exit(main())
