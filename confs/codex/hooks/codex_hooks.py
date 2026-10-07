#!/usr/bin/env python3
"""Adapt Codex events to shared policies; run stop checks in order."""

from __future__ import annotations

import fnmatch
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if Path(__file__).parent.name == 'bin':
  sys.path.insert(0, str(Path(__file__).resolve().parents[3] / '.agents/hooks/bin'))
else:
  sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'agents/hooks'))

import tool_gate
import turn_end


def normalize(raw: dict) -> dict:
  event = dict(raw)
  identity = raw.get('agent_id') if raw.get('hook_event_name') == 'SubagentStop' else None
  session = 'codex-' + str(identity or raw.get('session_id') or '')
  turn = str(raw.get('turn_id') or '')
  state = tool_gate.state_path(session, 'session', 'continuation.json')
  try:
    pending = json.loads(state.read_text(encoding='utf-8'))
  except (OSError, ValueError):
    pending = {}
  name = raw.get('hook_event_name', '')
  if name == 'UserPromptSubmit':
    submitted = raw.get('prompt', '')
    wrapped = re.fullmatch(r'<hook_prompt(?:\s[^>]*)?>\s*(.*?)\s*</hook_prompt>', submitted, re.DOTALL)
    if wrapped:
      submitted = wrapped.group(1)
    if submitted != pending.get('reason'):
      pending = {}
      state.unlink(missing_ok=True)
    elif pending:
      pending['turn'] = turn
      state.write_text(json.dumps(pending), encoding='utf-8')
  if pending and (pending.get('turn') == turn or raw.get('stop_hook_active')):
    turn = pending['origin']
  event['sessionId'] = session
  event['promptId'] = turn
  event['client'] = 'codex'
  if name == 'SubagentStop':
    cursor = tool_gate.state_path(session, 'session', 'latest.json')
    try:
      latest = json.loads(cursor.read_text(encoding='utf-8'))
    except (OSError, ValueError):
      latest = {}
    if latest:
      event['promptId'] = latest['prompt']
      event['cwd'] = latest['cwd']
  tool = str(raw.get('tool_name') or '').removeprefix('mcp__')
  tool = {'fff__ffgrep': 'fff__grep', 'fff__fff-multi-grep': 'fff__multi_grep'}.get(tool, tool)
  terminal = tool in ('Bash', 'exec_command',
    'desktop_commander__start_process', 'desktop-commander__start_process',
    'desktop_commander__interact_with_process', 'desktop-commander__interact_with_process')
  event['toolName'] = 'run_terminal_command' if terminal else tool
  if event['toolName'] == 'run_terminal_command':
    data = dict(tool_gate.input_of(event))
    if 'command' not in data and isinstance(data.get('cmd'), str):
      data['command'] = data['cmd']
    if tool.endswith('__interact_with_process') and isinstance(data.get('input'), str):
      data['command'] = data['input']
    event['tool_input'] = data
  return event


def continuation_key(event: dict) -> str:
  parsed = snapshot_event(event)
  root = turn_end.workspace(parsed)
  try:
    return changes_key(turn_end.load_changes(root, parsed))
  except (OSError, turn_end.NotGit, turn_end.NoSnapshot):
    # A missing baseline still needs a bounded retry budget.
    return event['promptId']


def remember_block(event: dict, result: dict) -> dict:
  result = dict(result)
  stage = result.pop('_failure_stage', 'hook')
  if result.get('decision') == 'block':
    state = tool_gate.state_path(event['sessionId'], 'session', 'continuation.json')
    try:
      previous = json.loads(state.read_text(encoding='utf-8'))
    except (OSError, ValueError):
      previous = {}
    key = continuation_key(event)
    locations = re.findall(r'^([^:\n]+:L\d+):', result['reason'], re.MULTILINE) if stage == 'review' else []
    failure = [stage, sorted(set(locations)) or result['reason']]
    unchanged = (previous.get('origin') == event['promptId']
      and previous.get('key') == key and previous.get('failure') == failure)
    repeats = previous.get('repeats', 0) + 1 if unchanged else 1
    state.write_text(json.dumps({
      'origin': event['promptId'],
      'turn': event.get('turn_id', ''),
      'reason': result['reason'],
      'repeats': repeats,
      'key': key,
      'failure': failure,
    }), encoding='utf-8')
    if repeats >= 3:
      return {
        'continue': False,
        'stopReason': result['reason'],
        'systemMessage': 'Validation incomplete: the same hook failure blocked the same diff three times. ' + result['reason'],
      }
  return result


def patch_paths(command: str, include_added: bool = True) -> list[str]:
  verbs = 'Update|Delete' + ('|Add' if include_added else '')
  return re.findall(r'^\*\*\* (?:' + verbs + r') File: (.+)$', command, re.MULTILINE) + re.findall(
    r'^\*\*\* Move to: (.+)$', command, re.MULTILINE,
  )


def successful(event: dict) -> bool:
  response = event.get('tool_response')
  if isinstance(response, dict):
    return not (response.get('isError') or response.get('error'))
  return True


def desktop_interactive_shell(command: str) -> str:
  invocation = re.fullmatch(r'[\'"]?([^\s\'"]+)[\'"]?(?:\s+(-[\w-]+))*', command.strip())
  if invocation:
    executable = invocation[1].replace('\\', '/').rsplit('/', 1)[-1].lower().removesuffix('.exe')
    options = command.lower().split()[1:]
    if executable in ('bash', 'sh', 'zsh', 'pwsh', 'powershell', 'cmd') and all(
        option in ('-i', '-l', '--login', '--noprofile', '--norc', '-noprofile', '-nologo', '-noexit')
        for option in options):
      return executable
  return ''


def desktop_process_shells(event: dict, update: bool = False) -> dict:
  # Session-scoped process identity is security metadata, not reader routing.
  path = tool_gate.state_path(event['sessionId'], 'session', 'desktop-process-shells.json')
  try:
    shells = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(shells, dict):
      shells = {}
  except (OSError, ValueError):
    shells = {}
  if not update:
    return shells
  tool = str(event.get('tool_name') or '')
  data = tool_gate.input_of(event)
  if tool.endswith('__kill_process'):
    shells.pop(str(data.get('pid')), None)
  elif tool.endswith('__interact_with_process'):
    shell = desktop_interactive_shell(str(data.get('input') or ''))
    if not shell:
      return shells
    shells[str(data.get('pid'))] = shell
  elif tool.endswith('__start_process'):
    response = event.get('tool_response')
    content = response.get('content', []) if isinstance(response, dict) else []
    first = content[0] if content else {}
    header = first.get('text', '') if isinstance(first, dict) else ''
    started = re.match(r'\AProcess started with PID ([0-9]+) \(shell: [^\r\n]+\)(?:\r?\n|$)', header)
    if not started:
      return shells
    # The launcher's shell can differ from the interactive process it starts.
    shells[started[1]] = desktop_interactive_shell(str(data.get('command') or ''))
  else:
    return shells
  path.write_text(json.dumps(shells), encoding='utf-8')
  return shells


def tool_policy(event: dict) -> dict:
  name = event.get('hook_event_name')
  tool = event.get('toolName')
  if name == 'PreToolUse' and secret_paths(event):
    return {'decision': 'deny', 'reason': 'Protected .env or PEM path. Use a redacted example file.'}
  if name == 'PreToolUse' and tool == 'run_terminal_command':
    if recursive_windows_delete(tool_gate.command_of(event)):
      return {'decision': 'deny', 'reason': 'Recursive Windows deletion is denied by the permission policy.'}
  if name == 'PostToolUse' and not successful(event):
    return {}
  if name == 'PostToolUse' and re.match(r'^mcp__desktop[-_]commander__', str(event.get('tool_name') or '')):
    desktop_process_shells(event, update=True)
  if tool == 'apply_patch':
    command = tool_gate.command_of(event)
    for path in patch_paths(command, include_added=name != 'PreToolUse'):
      changed = dict(event, toolName='write', tool_input={'file_path': path})
      result = tool_gate.handle(changed)
      if result.get('decision') == 'deny':
        return result
    return {}
  # Tool routing belongs in developer instructions; hooks retain safety/checks.
  # Host approvals also own branch creation, which chat may already authorize.
  if tool in ({'run_terminal_command', 'grep', 'Grep', tool_gate.GK_BRANCH}
      | tool_gate.GITHUB_TREE | tool_gate.FFF_GREP):
    return {}
  if name == 'PreToolUse' and tool == 'serena__rename_symbol':
    # Keep Go references required without the shared policy's rename routing.
    session, prompt = tool_gate.ids_of(event)
    return tool_gate.gate_go_pre(session, prompt, 'serena__replace_content', event)
  return tool_gate.handle(event)


def wsl_payload(args: list[str]) -> tuple[list[str], bool] | None:
  """Extract supported WSL execution forms, excluding management operations."""
  index = 0
  value_options = {'--distribution', '-d', '--cd', '--user', '-u'}
  while index < len(args):
    option, separator, _ = args[index].lower().partition('=')
    if option in value_options:
      index += 1 if separator else 2
      continue
    if option in ('--exec', '-e'):
      return args[index + 1:], True
    if args[index].startswith('-'):
      return None
    return args[index:], False
  return None


def recursive_windows_delete(command: str, depth: int = 0) -> bool:
  # Inspect command heads and wrapper payloads, never unrelated text arguments.
  if depth > 8:
    return False
  stripped = command.strip()
  if stripped.startswith(('&', '.')):
    block = stripped[1:].strip()
    if block.startswith('{') and block.endswith('}'):
      return recursive_windows_delete(block[1:-1], depth + 1)
  for segment in tool_gate.split_segments(command):
    tokens = tool_gate.tokenize(segment)
    invoked = bool(tokens and tokens[0] == '&')
    if invoked:
      tokens = tokens[1:]
    if not tokens or (segment.startswith(('"', "'")) and not invoked):
      continue
    executable = tokens[0].replace('\\', '/').rsplit('/', 1)[-1].lower()
    executable = executable.removesuffix('.exe')
    args = tokens[1:]
    lowered = [arg.lower() for arg in args]
    if executable == 'wsl':
      payload = wsl_payload(args)
      if payload:
        nested_args, direct = payload
        # --exec preserves argv; default-shell text is interpreted by POSIX.
        nested = ' '.join(shlex.quote(arg) if direct else arg for arg in nested_args)
        if recursive_windows_delete(nested, depth + 1):
          return True
      continue
    if executable == 'remove-item':
      value_next = False
      for arg in lowered:
        if value_next:
          value_next = False
          continue
        if arg in ('-path', '-literalpath', '-filter', '-include', '-exclude'):
          value_next = True
        else:
          switch, _, value = arg.partition(':')
          # Recognize unambiguous recurse prefixes from -re onward.
          if len(switch) >= 3 and '-recurse'.startswith(switch):
            if value not in ('$false', 'false'):
              return True
    if executable in ('del', 'rmdir', 'rd') and any(
      arg == '/s' or arg.startswith('/s/') for arg in lowered
    ):
      return True
    if executable in ('foreach-object', '%'):
      block = segment[segment.find(tokens[0]) + len(tokens[0]):].strip()
      if block.startswith('{') and block.endswith('}'):
        if recursive_windows_delete(block[1:-1], depth + 1):
          return True
    switches = {
      'powershell': ('-command', '-c'), 'pwsh': ('-command', '-c'),
      'cmd': ('/c', '/k'), 'bash': ('-c', '-lc'),
      'sh': ('-c', '-lc'), 'zsh': ('-c', '-lc'),
    }.get(executable, ())
    for index, arg in enumerate(lowered):
      if arg in switches and index + 1 < len(args):
        payload = args[index + 1:]
        # Quoted shell payloads remain one token; unquoted cmd payloads span tokens.
        nested = payload[0] if len(payload) == 1 else ' '.join(payload)
        if executable == 'cmd':
          # cmd separates commands with a single &, unlike PowerShell's call operator.
          chars = []
          quote = ''
          escaped = False
          for char in nested:
            if escaped:
              chars.append(char)
              escaped = False
            elif char == '^':
              chars.append(char)
              escaped = True
            elif char in ('"', "'"):
              quote = '' if quote == char else (quote or char)
              chars.append(char)
            else:
              chars.append(';' if char == '&' and not quote else char)
          nested = ''.join(chars)
        if recursive_windows_delete(nested, depth + 1):
          return True
        break
  return False


def substitution_end(command: str, start: int) -> tuple[int, bool]:
  """Find a $() boundary while retaining nested and quoted parentheses."""
  end, balance, quote = start + 2, 1, ''
  while end < len(command) and balance:
    char = command[end]
    if char in ('\\', '`', '^') and quote != "'" and end + 1 < len(command):
      end += 2
      continue
    if char in ('"', "'") and (not quote or quote == char):
      quote = '' if quote else char
    elif not quote:
      balance += (char == '(') - (char == ')')
    end += 1
  return end, not balance


def ansi_c_text(text: str) -> str:
  """Decode Bash's quoted filename escapes without evaluating shell text."""
  common = {'a': '\a', 'b': '\b', 'e': '\x1b', 'E': '\x1b', 'f': '\f',
    'n': '\n', 'r': '\r', 't': '\t', 'v': '\v', '\\': '\\', "'": "'", '"': '"', '?': '?'}
  def decode(match: re.Match) -> str:
    escape = match[0][1:]
    if escape[0] in '01234567':
      return chr(int(escape, 8) % 256)
    if escape[0] in 'xuU' and len(escape) > 1:
      value = int(escape[1:], 16)
      return chr(value) if value <= 0x10ffff else match[0]
    if escape.startswith('c') and len(escape) == 2:
      return chr(127 if escape[1] == '?' else ord(escape[1]) & 31)
    return common.get(escape, match[0])
  return re.sub(r'\\(?:[0-7]{1,3}|x[0-9a-fA-F]{1,2}|u[0-9a-fA-F]{1,4}|U[0-9a-fA-F]{1,8}|c.|.)',
    decode, text, flags=re.DOTALL).split('\0', 1)[0]


def secret_shell_words(command: str, substitutions: list[str], starts: list[tuple[int, str]], shell: str) -> list[tuple[str, str]]:
  """Join adjacent quoted fragments without discarding Windows path separators."""
  words, word, literal_word, quote = [], [], [], ''
  script_depth = 0
  # Keep raw payloads for nested shells; the parallel spelling preserves
  # literal metacharacters for the independent protected-glob check.
  literal_marks = str.maketrans({'*': '\ue000', '?': '\ue001', '[': '\ue002', '{': '\ue003'})
  def append(fragment: str, escaped: bool = False) -> None:
    marks = str.maketrans({'*': '\ue006', '?': '\ue007', '[': '\ue008'}) if escaped else literal_marks
    spelling = fragment.translate(marks) if quote or escaped else fragment
    if shell in ('pwsh', 'powershell'):
      # PowerShell passes wildcard text literally unless a provider consumes it.
      spelling = spelling.translate(str.maketrans({'*': '\ue000', '?': '\ue001', '[': '\ue002'}))
    if quote == "'" or escaped:
      spelling = spelling.replace('$', '\ue004').replace('`', '\ue005')
    if quote == '"' and not escaped:
      spelling = spelling.replace('$\ue003', '${')
      if fragment.startswith('{') and word and word[-1].endswith('$'):
        spelling = '{' + spelling[1:]
    word.append(fragment)
    literal_word.append(spelling)
  index = 0
  while index < len(command):
    char = command[index]
    if shell in ('pwsh', 'powershell') and not quote and char == '[' and (
        not word or word[-1].endswith('=')):
      cast = re.match(r'\[[a-zA-Z_][\w.,\[\]]*\](?=\s*(?:\$|::|[\"\'(]|\[))', command[index:])
      if cast:
        # Retain type syntax separately from literal/provider wildcard brackets.
        word.append(cast[0])
        literal_word.append('\ue009' + cast[0][1:])
        index += cast.end()
        continue
    if shell in ('bash', 'sh', 'zsh') and not quote and command[index:index + 2] == "$'":
      end = index + 2
      while end < len(command) and command[end] != "'":
        end += 2 if command[end] == '\\' and end + 1 < len(command) else 1
      quote = "'"
      append(ansi_c_text(command[index + 2:end]))
      quote = ''
      index = min(end + 1, len(command))
      continue
    if char in ('\\', '`') and quote != "'":
      newline = 2 if command[index + 1:index + 3] == '\r\n' else int(command[index + 1:index + 2] == '\n')
      if newline:
        index += 1 + newline
        continue
    if char == '\\' and quote != "'" and shell in ('bash', 'sh', 'zsh') and command[index + 1:index + 2] in ('$', '`', '\\', '"'):
      # Bash consumes escaped expansion markers before considering substitution.
      append(command[index + 1], escaped=True)
      index += 2
      continue
    if char == '`' and quote != "'" and shell not in ('pwsh', 'powershell'):
      end = index + 1
      while end < len(command):
        if command[end] == '\\' and end + 1 < len(command):
          end += 2
        elif command[end] == '`':
          break
        else:
          end += 1
      if end < len(command):
        # Bash permits nested backticks escaped inside the enclosing body.
        substitutions.append(command[index + 1:end].replace('\\`', '`'))
        append(command[index:end + 1])
        index = end + 1
        continue
      # Preserve a possible unfinished body; ordinary single-character
      # PowerShell filename escapes without whitespace still join below.
      if any(char.isspace() for char in command[index + 1:]):
        substitutions.append(command[index + 1:])
        append(command[index:])
        index = len(command)
        continue
    if char == '`' and quote != "'" and shell in ('pwsh', 'powershell') and command[index + 1:index + 2] in ('$', '`'):
      # PowerShell's escape consumes the next character before expansion.
      append(command[index + 1], escaped=True)
      index += 2
      continue
    if char == '$' and quote != "'" and command[index:index + 2] == '$(':
      # Keep an unresolved expansion attached to its literal filename fragments.
      end, complete = substitution_end(command, index)
      substitutions.append(command[index + 2:end - 1 if complete else end])
      append(command[index:end])
      index = end
      continue
    if shell in ('pwsh', 'powershell') and quote != "'" and command[index:index + 2] == '${':
      # Parameter braces are part of the word, not script-block boundaries.
      end = command.find('}', index + 2)
      end = len(command) if end < 0 else end + 1
      append(command[index:end])
      index = end
      continue
    if shell in ('pwsh', 'powershell') and not quote and (
        char == '{' and (not word or word[-1].endswith('=') or word == ['@'])
        or char == '}' and script_depth):
      if word:
        words.append((''.join(word), ''.join(literal_word)))
        word, literal_word = [], []
      script_depth += 1 if char == '{' else -1
      starts.append((len(words), char))
      index += 1
      continue
    if char in ('"', "'") and (not quote or quote == char):
      quote = '' if quote else char
    elif char in ('\\', '`', '^') and quote != "'" and index + 1 < len(command):
      following = command[index + 1]
      # Keep backslashes in paths; a second spelling below covers shell escapes.
      # Escape rules differ by shell. Without a known dialect, never use an
      # escape marker to hide a potentially executed substitution.
      if (following in ('$', '`') or (shell in ('pwsh', 'powershell') and char in ('\\', '^') and following in '*?[')
          or (char == '^' and word and word[-1].endswith('['))
          or (char == '\\' and following not in ('"', "'", ' ', '\\', '(', ')', '<', '>', '*', '?', '[', '{'))):
        append(char)
      else:
        index += 1
        append(following, escaped=True)
    elif char == ',' and ''.join(word).count('{') > ''.join(word).count('}'):
      append(char)
    elif not quote and (char.isspace() or char in '();,|&<>'):
      if word:
        words.append((''.join(word), ''.join(literal_word)))
        word, literal_word = [], []
      if char in ';|&()<>\n\r':
        starts.append((len(words), char))
    else:
      append(char)
    index += 1
  if word:
    words.append((''.join(word), ''.join(literal_word)))
  return words


def shell_patterns_overlap(left: str, right: str) -> bool:
  """Intersect shell expansion wildcards with the complete protected language."""
  classes = {
    'alpha': 'a-zA-Z', 'alnum': 'a-zA-Z0-9', 'lower': 'a-z', 'upper': 'A-Z',
    'digit': '0-9', 'xdigit': 'a-fA-F0-9', 'blank': ' \t',
    'space': ' \t\r\n\v\f', 'cntrl': '\x00-\x1f\x7f',
    'graph': '!-~', 'print': ' -~', 'punct': '!-/:-@[-`{-~',
  }
  def posix_class(match: re.Match) -> str:
    token = match[0]
    names = re.findall(r'\[:([a-z]+):\]', token)
    if any(name not in classes for name in names):
      return '?'  # Unknown locale classes cannot prove a secret unreachable.
    return re.sub(r'\[:([a-z]+):\]', lambda part: classes[part[1]], token)
  left = re.sub(r'\[(?:[!^])?(?:\[:[a-z]+:\]|[^\]])+\]', posix_class, left)
  left = re.findall(r'\[(?:[!^])?\]?[^\]]*\]|.', left)
  left = ['[!' + token[2:] if token.startswith('[^') else token for token in left]
  pending, seen = [(0, 0)], set()
  while pending:
    first, second = pending.pop()
    if (first, second) in seen:
      continue
    seen.add((first, second))
    if first == len(left) and second == len(right):
      return True
    a = left[first] if first < len(left) else ''
    b = right[second] if second < len(right) else ''
    if a == '*':
      pending.append((first + 1, second))
    if b == '*':
      pending.append((first, second + 1))
    # Keep both filename cases reachable, including through negated classes;
    # protected_path is case-insensitive and Windows is the active target.
    if a and b and (b in '*?' or fnmatch.fnmatchcase(b, a) or fnmatch.fnmatchcase(b.upper(), a)):
      pending.append((first + (a != '*'), second + (b != '*')))
  return False


def protected_shell_word(word: str) -> bool:
  word = re.sub(r'\ue009[a-zA-Z_][\w.,\[\]]*\]', '', word)
  alternatives = re.search(r'(?<!\$)\{([^{}]*,[^{}]*)\}', word)
  if alternatives:
    return any(protected_shell_word(word[:alternatives.start()] + branch + word[alternatives.end():])
      for branch in alternatives[1].split(','))
  if (word.startswith('$(') or word.lstrip('\\\ue005').startswith('\ue004(')) and word.endswith(')'):
    # Executed bodies are inspected separately; literal/escaped bodies stay text.
    return False
  if turn_end.protected_path(word):
    return True
  # Shell escapes may concatenate a secret basename, e.g. .en\v. Inspect
  # suffixes as well so a Windows-style directory does not hide that basename.
  parts = word.split('\\')
  if any(turn_end.protected_path(''.join(parts[index:])) for index in range(len(parts))):
    return True
  if re.fullmatch(r'-[a-z][a-z-]*:\$(?:true|false)', word, re.IGNORECASE):
    return False  # PowerShell boolean switch values are not path arguments.
  base = word
  expansion = r'\$\{[^}]*\}?|\$[a-zA-Z_][a-zA-Z_0-9:]*|%[^%]+%|`[^`]*`?'
  fragments, index = [''], 0
  while index < len(base):
    match = re.match(expansion, base[index:])
    if base[index:index + 2] == '$(':
      index, _ = substitution_end(base, index)
      fragments.append('')
    elif match:
      index += match.end()
      fragments.append('')
    else:
      fragments[-1] += base[index]
      index += 1
  # Select the basename only after masking expansions: separators inside
  # command bodies are not separators in the resulting literal path.
  literal_base = '\0'.join(fragments).replace('\\', '/').rsplit('/', 1)[-1]
  literal_glob = bool(re.search(r'[*?\[]', literal_base))
  pattern = '*'.join(fragments).replace('\\', '/').rsplit('/', 1)[-1]
  fragments = pattern.split('*')
  if not literal_glob and (len(fragments) == 1 or not ''.join(fragments)):
    return False  # A wholly dynamic path remains an ordinary shell operation.
  # These patterns exactly cover turn_end.protected_path, including its
  # unbounded .env.*.local language; they are not sampled expansion values.
  protected = ('.env', '.env.seed', '.env.local', '.env.development',
    '.env.production', '.env.test', '.env.?*.local', '*.pem')
  for mark, literal in (('\ue000', '[*]'), ('\ue001', '[?]'), ('\ue002', '[[]'),
      ('\ue003', '{'), ('\ue004', '$'), ('\ue005', '`'),
      ('\ue006', '[*]'), ('\ue007', '[?]'), ('\ue008', '[[]')):
    pattern = pattern.replace(mark, literal)
  return any(shell_patterns_overlap(pattern, secret) for secret in protected)


def shell_secret_paths(command: str, shell: str = '') -> bool:
  shell = shell.replace('\\', '/').rsplit('/', 1)[-1].lower().removesuffix('.exe')
  shell = shell or ('powershell' if os.name == 'nt' else 'sh')
  substitutions = []
  starts = [(0, '')]
  parsed = secret_shell_words(command, substitutions, starts, shell)
  words = [word for word, _ in parsed]
  if any(shell_secret_paths(body, shell) for body in substitutions):
    return True
  if shell in ('pwsh', 'powershell'):
    redirections = {index for index, boundary in starts if boundary in ('<', '>')}
    # PowerShell's filesystem providers expand -Path wildcards even in quotes.
    # Keep this scoped to path-taking commands, not output text or shell payloads.
    path_commands = {'get-content', 'gc', 'cat', 'type', 'remove-item', 'rm', 'del',
      'erase', 'ri', 'set-content', 'sc', 'add-content', 'ac', 'clear-content', 'clc',
      'copy-item', 'copy', 'cp', 'cpi', 'move-item', 'move', 'mv', 'mi',
      'get-item', 'gi', 'get-childitem', 'gci', 'dir', 'ls', 'select-string', 'sls',
      'import-csv', 'ipcsv', 'import-clixml', 'export-csv', 'epcsv', 'export-clixml'}
    value_parameters = {'-value', '-pattern', '-totalcount', '-tail', '-encoding',
      '-readcount', '-delimiter', '-filter', '-include', '-exclude', '-credential', '-stream'}
    active, literal, skip_value, selection = False, False, False, ''
    groups = []
    for (begin, boundary), (end, _) in zip(starts, starts[1:] + [(len(words), '')]):
      if boundary in ('(', '{'):
        outer = (active, literal, False, '')
        if boundary == '{':
          active, literal, skip_value, selection = False, False, False, ''
        else:
          active = active and not skip_value
          skip_value = False
        groups.append((outer, (active, literal, False, selection)))
      elif boundary in (')', '}'):
        active, literal, skip_value, selection = groups.pop()[0] if groups else (False, False, False, '')
      elif boundary:
        active, literal, skip_value, selection = groups[-1][1] if groups and boundary in ';\n\r' else (False, False, False, '')
      segment = words[begin:end]
      if not segment:
        continue
      # A simple assignment may attach to either side of the '=' token.
      first, invocation = 0, segment[0]
      assignment = re.fullmatch(r'(?:\[[a-zA-Z_][\w.,\[\]]*\])?\$[a-zA-Z_][\w:]*(?:=(.*))?', invocation)
      if assignment and (assignment[1] is not None or len(segment) > 1 and segment[1].startswith('=')):
        if assignment[1] is None:
          first, invocation = 1, segment[1][1:]
        else:
          invocation = assignment[1]
        if not invocation and first + 1 < len(segment):
          first += 1
          invocation = segment[first]
        # A typed variable declaration is syntax, not a wildcard path.
        parsed[begin] = (segment[0], parsed[begin][1].partition('=')[2] if first == 0 else '')
      cmdlet = invocation.rsplit('\\', 1)[-1].lower()
      invoked = cmdlet in path_commands
      parameters = value_parameters | {'-path', '-literalpath'}
      if invoked:
        # Only Select-String has -Pattern among these path-taking commands.
        if cmdlet not in ('select-string', 'sls'):
          parameters = parameters - {'-pattern'}
        if cmdlet not in ('set-content', 'sc', 'add-content', 'ac'):
          parameters = parameters - {'-value'}
      if invoked:
        active, literal, skip_value, selection = True, False, False, ''
      for index in range(begin + first + 1 if invoked else begin, end):
        raw, pattern = parsed[index]
        redirection = index in redirections
        if skip_value:
          skip_value = raw == '@'
          continue
        if raw.startswith('-') and not redirection:
          parameter, separator, _ = raw.partition(':')
          parameter_length = len(parameter)
          parameter = parameter.lower()
          if parameter not in parameters and len(parameter) > 1:
            matches = {candidate for candidate in parameters if candidate.startswith(parameter)}
            if len(matches) == 1:
              parameter = matches.pop()
            elif '-path' in matches:
              # An ambiguous prefix must not hide a possible provider path.
              parameter = '-path'
          # Explicit provider paths need checking even on unfamiliar commands.
          if parameter in ('-path', '-literalpath'):
            active = True
            literal = parameter == '-literalpath'
          # Selection patterns expand independently of the path's literal mode.
          selection = parameter if active and parameter in ('-filter', '-include', '-exclude') else ''
          skip_value = parameter in value_parameters and not selection and not separator
          if parameter not in ('-path', '-literalpath') and not selection or not separator:
            continue
          raw, pattern = raw[parameter_length + 1:], pattern[parameter_length + 1:]
        if selection == '-exclude':
          parsed[index] = (raw, '')  # Exclusions cannot select a protected path.
          selection = selection if raw == '@' or groups and groups[-1][1][3] else ''
          continue
        if not active and not redirection:
          continue
        if literal and not selection and not redirection:
          pattern = pattern.replace('\ue009', '[').translate(str.maketrans({'*': '\ue000', '?': '\ue001', '[': '\ue002'}))
        else:
          for mark, wildcard in (('\ue000', '*'), ('\ue001', '?'), ('\ue002', '['),
              ('\ue006', '*'), ('\ue007', '?'), ('\ue008', '['), ('\ue009', '[')):
            pattern = pattern.replace(mark, wildcard)
        parsed[index] = (raw, pattern)
        selection = selection if raw == '@' or groups and groups[-1][1][3] else ''
  if any(protected_shell_word(pattern) for _, pattern in parsed):
    return True
  switches = {
    'bash': ('-c', '-lc'), 'sh': ('-c', '-lc'), 'zsh': ('-c', '-lc'),
    'pwsh': ('-c', '-command'), 'powershell': ('-c', '-command'),
    'cmd': ('/c', '/k'),
  }
  for index, word in enumerate(words):
    executable = word.replace('\\', '/').rsplit('/', 1)[-1].lower().removesuffix('.exe')
    if executable == 'wsl':
      payload = wsl_payload(words[index + 1:])
      if payload and not payload[1]:
        nested = ' '.join(payload[0])
        if nested != command and shell_secret_paths(nested, 'sh'):
          return True
      continue
    if executable not in switches:
      continue
    for offset in range(index + 1, len(words) - 1):
      if words[offset].lower() in switches[executable]:
        payload = words[offset + 1:]
        nested = payload[0] if len(payload) == 1 else ' '.join(payload)
        if nested != command and shell_secret_paths(nested, executable):
          return True
        break
  return False


def secret_paths(event: dict) -> bool:
  data = tool_gate.input_of(event)
  paths = []
  for key in ('file_path', 'path', 'target_file', 'relative_path', 'file', 'paths', 'source', 'destination'):
    value = data.get(key)
    paths.extend(value if isinstance(value, list) else [value])
  if event.get('toolName') == 'apply_patch':
    paths.extend(patch_paths(tool_gate.command_of(event)))
  elif event.get('toolName') == 'run_terminal_command':
    # Inspect literal secret paths, including quoted shell payloads. This is
    # independent of reader choice, bounds, project roots, and fallback state.
    # Codex also labels native Windows PowerShell exec events as Bash and drops
    # the shell field. Use the host dialect there; Linux Bash stays Bash.
    shell = str(data.get('shell') or ('bash' if event.get('tool_name') == 'Bash' and os.name != 'nt' else ''))
    if str(event.get('tool_name') or '').endswith('__interact_with_process'):
      shell = desktop_process_shells(event).get(str(data.get('pid')), '')
      candidates = (shell,) if shell else ('powershell', 'bash', 'cmd')
    else:
      candidates = (shell,)
    if any(shell_secret_paths(tool_gate.command_of(event), candidate) for candidate in candidates):
      return True
  for path in paths:
    if not isinstance(path, str):
      continue
    if turn_end.protected_path(path):
      return True
  return False


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
  except turn_end.NotGit:
    return {}
  errors = io.StringIO()
  if turn_end.write_snapshot(root, parsed, errors):
    return {'decision': 'block', 'reason': errors.getvalue().strip()}
  return {}


def run_stage(mode: str, event: dict) -> dict:
  output, errors = io.StringIO(), io.StringIO()
  status = turn_end.run([mode], io.StringIO(json.dumps(event)), output, errors)
  if status:
    return {'decision': 'block', 'reason': errors.getvalue().strip() or f'{mode} hook failed'}
  return json.loads(output.getvalue()) if output.getvalue().strip() else {}


def changes_key(changes: list[turn_end.Change]) -> str:
  return hashlib.sha256(turn_end.encode_json({
    change.path: [change.before, change.after, change.before_deleted, change.after_deleted]
    for change in changes
  })).hexdigest()


def review(changes: list[turn_end.Change]) -> dict:
  changes = [change for change in changes if not turn_end.protected_path(change.path)]
  if not changes:
    return {}
  if shutil.which('codex') is None:
    return {'decision': 'block', 'reason': 'codex is not on PATH; review did not run.'}
  env = dict(os.environ, TURN_END_CHILD='1')
  # Separate workspace prevents project hooks/config/AGENTS from re-entering.
  # Auth remains in CODEX_HOME; user config and MCP servers are not loaded.
  with tempfile.TemporaryDirectory(prefix='codex-hook-review-') as temp:
    output = Path(temp) / 'review.txt'
    try:
      result = subprocess.run([
        'codex', '--no-daemon', 'exec', '--ignore-user-config', '--ephemeral',
        '--skip-git-repo-check', '--sandbox', 'read-only', '--color', 'never',
        '-c', 'features.hooks=false', '-c', 'agents.enabled=false',
        '-c', 'features.multi_agent=false', '-c', 'features.memories=false',
        '-c', 'features.shell_tool=false', '-c', 'features.apps=false',
        '-c', 'web_search="disabled"', '-c', 'project_doc_max_bytes=0',
        '--output-last-message', str(output), '-',
      ], input=turn_end.review_prompt(changes, complete=True), cwd=temp, env=env, capture_output=True,
        text=True, encoding='utf-8', errors='replace', timeout=turn_end.REVIEW_TIMEOUT,
        check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
      return {'decision': 'block', 'reason': f'Codex review failed: {type(error).__name__}'}
    if result.returncode:
      return {'decision': 'block', 'reason': f'Codex review exited {result.returncode}; check login and retry.'}
    text = output.read_text(encoding='utf-8').strip() if output.exists() else ''
  if text == turn_end.REVIEW_PASS:
    return {}
  return {'decision': 'block', 'reason': turn_end.trim_out(text) or 'Codex review returned no verdict.'}


def stop(event: dict) -> dict:
  reason = event.get('reason') or ''
  if reason in ('shutdown', 'channel_closed'):
    return {}
  if event.get('hook_event_name') == 'Stop' and reason not in ('', 'end_turn'):
    return {}
  session, prompt = tool_gate.ids_of(event)
  # Existing definitions are gated before editing. New Go files have no refs;
  # both still need diagnostics after the last successful edit.
  if (prompt and tool_gate.state_path(session, prompt, 'gopls-edited').exists()
      and not tool_gate.state_path(session, prompt, 'gopls-diag').exists()):
    return {'decision': 'block', 'reason': tool_gate.GO_DIAG_BLOCK, '_failure_stage': 'diagnostics'}
  result = run_stage('format', event)
  if result:
    return dict(result, _failure_stage='format')
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
    if mode == 'review' and event.get('hook_event_name') == 'SubagentStop':
      continue
    cache = tool_gate.state_path(session, prompt, mode + '.passed')
    if cache.exists() and cache.read_text(encoding='utf-8') == digest:
      continue
    result = review(changes) if mode == 'review' else run_stage(mode, event)
    if result:
      return dict(result, _failure_stage=mode)
    cache.write_text(digest, encoding='utf-8')
  return {}


def dispatch(raw: dict) -> dict:
  if os.environ.get(turn_end.CHILD_ENV) == '1':
    return {}
  event = normalize(raw)
  name = event.get('hook_event_name')
  if name == 'UserPromptSubmit':
    # Preserve the original baseline on a hook continuation.
    return ensure_snapshot(event, force=event['promptId'] == event.get('turn_id'))
  if name == 'PreToolUse':
    result = ensure_snapshot(event)
    if result:
      return {'hookSpecificOutput': {'hookEventName': name, 'permissionDecision': 'deny', 'permissionDecisionReason': result['reason']}}
  if name in ('PreToolUse', 'PostToolUse'):
    result = tool_policy(event)
    if name == 'PreToolUse' and result.get('decision') == 'deny':
      return {'hookSpecificOutput': {
        'hookEventName': name, 'permissionDecision': 'deny',
        'permissionDecisionReason': result['reason'],
      }}
    return {} if result.get('decision') == 'allow' else result
  if name in ('Stop', 'SubagentStop'):
    return remember_block(event, stop(event))
  return {}


def main() -> int:
  try:
    raw = json.load(sys.stdin)
    result = dispatch(raw)
  except (OSError, ValueError, TypeError, KeyError) as error:
    print(f'Codex hook failed: {type(error).__name__}', file=sys.stderr)
    return 2
  if result:
    json.dump(result, sys.stdout)
    sys.stdout.write('\n')
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
