#!/usr/bin/env python3
"""Turn-end gate for any git workspace.

snapshot records the dirty tree. format and test dispatch by changed path.
The Go stack runs gofmt, go test, go vet, and gopls check on edited Go files.
review runs grok -p with XAI_API_KEY. It does not sign in, and it does not lint .editorconfig.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

DELETED_HASH = 'deleted'
MODES = ('snapshot', 'format', 'test', 'review')
CHILD_ENV = 'TURN_END_CHILD'
REVIEW_PASS = 'No issues.'
REVIEW_TIMEOUT = 240
REVIEW_CAP = 12000
REVIEW_FILE_CAP = 3000


class NotGit(Exception):
  pass


class NoSnapshot(Exception):
  pass


@dataclass
class Event:
  client: str = ''
  reason: str = ''
  session_id: str = ''
  prompt_id: str = ''
  prompt: str = ''
  cwd: str = ''
  workspace_root: str = ''
  stop_hook_active: bool = False
  last_assistant_message: str = ''


@dataclass
class FileState:
  hash: str
  content: str = ''
  deleted: bool = False

  def to_json(self) -> dict[str, str | bool]:
    out: dict[str, str | bool] = {'hash': self.hash}
    if self.content:
      out['content'] = self.content
    if self.deleted:
      out['deleted'] = True
    return out

  @classmethod
  def from_json(cls, raw: dict) -> FileState:
    return cls(
      hash=raw.get('hash', ''),
      content=raw.get('content', ''),
      deleted=bool(raw.get('deleted', False)),
    )


@dataclass
class Snapshot:
  files: dict[str, FileState] = field(default_factory=dict)
  prompt: str = ''


@dataclass
class Change:
  path: str
  before: str = ''
  after: str = ''
  before_deleted: bool = False
  after_deleted: bool = False


@dataclass
class GoCmd:
  directory: str
  args: list[str]


@dataclass
class ModuleWork:
  directory: str
  pkgs: list[str]


def main() -> int:
  for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, 'reconfigure', None)
    if reconfigure is None:
      continue
    try:
      reconfigure(encoding='utf-8', errors='surrogateescape')
    except (AttributeError, OSError, ValueError):
      pass
  return run(sys.argv[1:], sys.stdin, sys.stdout, sys.stderr)


def run(args: list[str], stdin, stdout, stderr) -> int:
  if len(args) != 1 or args[0] not in MODES:
    write_text(stderr, 'usage: turn_end.py snapshot|format|test|review\n')
    return 1
  mode = args[0]
  try:
    raw = read_text(stdin)
  except OSError as err:
    write_text(stderr, f'read hook input: {err}\n')
    return 1
  event = Event()
  if raw.strip():
    try:
      event = parse_event(json.loads(raw))
    except json.JSONDecodeError as err:
      write_text(stderr, f'parse hook input: {err}\n')
      return 1
  if skip_gate(mode, event):
    return 0
  root = workspace(event)
  if not root:
    write_text(stderr, 'hook workspace is empty\n')
    return 1
  try:
    os.chdir(root)
  except OSError as err:
    write_text(stderr, f'chdir: {err}\n')
    return 1
  try:
    ensure_git(root)
  except NotGit:
    return 0
  if mode == 'snapshot':
    return write_snapshot(root, event, stderr)
  if mode == 'format':
    return gate_format(root, event, stdout, stderr)
  if mode == 'test':
    return gate_test(root, event, stdout, stderr)
  return gate_review(root, event, stdout, stderr)


def skip_gate(mode: str, event: Event) -> bool:
  if os.environ.get(CHILD_ENV) == '1':
    return True
  if event.reason in ('channel_closed', 'shutdown'):
    return True
  if mode == 'snapshot':
    return False
  # Stop also fires at session end. SubagentStop still gates.
  hook = os.environ.get('GROK_HOOK_EVENT', '')
  return hook == 'stop' and event.reason not in ('', 'end_turn')


def parse_event(raw: dict) -> Event:
  session = raw.get('sessionId') or raw.get('session_id') or ''
  prompt_id = raw.get('promptId') or raw.get('prompt_id') or raw.get('turn_id') or ''
  workspace_root = raw.get('workspaceRoot') or raw.get('workspace_root') or ''
  return Event(
    client=raw.get('client') or '',
    reason=raw.get('reason') or '',
    session_id=session,
    prompt_id=prompt_id,
    prompt=raw.get('prompt') or '',
    cwd=raw.get('cwd') or '',
    workspace_root=workspace_root,
    stop_hook_active=bool(raw.get('stopHookActive') or raw.get('stop_hook_active')),
    last_assistant_message=raw.get('lastAssistantMessage') or raw.get('last_assistant_message') or '',
  )


def workspace(event: Event) -> str:
  for value in (
    os.environ.get('GROK_WORKSPACE_ROOT', ''),
    os.environ.get('CLAUDE_PROJECT_DIR', ''),
    event.workspace_root,
    event.cwd,
  ):
    if value:
      return value
  return os.getcwd()


def ensure_git(root: str) -> None:
  try:
    out = subprocess.run(
      ['git', 'rev-parse', '--is-inside-work-tree'],
      cwd=root,
      check=False,
      capture_output=True,
    )
  except OSError as err:
    raise NotGit() from err
  if out.returncode != 0 or out.stdout.decode('utf-8', errors='replace').strip() != 'true':
    raise NotGit()


def write_snapshot(root: str, event: Event, stderr) -> int:
  try:
    files = capture(root, protect_secrets=True) if event.client == 'codex' else capture(root)
    save_snapshot(root, event, Snapshot(files=files, prompt=event.prompt))
  except OSError as err:
    write_text(stderr, f'snapshot: {err}\n')
    return 1
  return 0


def gate_format(root: str, event: Event, stdout, stderr) -> int:
  try:
    changes = load_changes(root, event)
  except NoSnapshot:
    return 0
  except OSError as err:
    write_text(stderr, f'{err}\n')
    return 1
  go_changes = [change for change in changes if is_go_source(change)]
  if not go_changes:
    return 0
  if shutil.which('gofmt') is None:
    return block(stdout, 'gofmt is not on PATH. Changed Go files were not formatted.')
  rewritten = []
  for change in go_changes:
    path = os.path.join(root, from_slash(change.path))
    try:
      before = read_bytes(path)
    except OSError as err:
      write_text(stderr, f'gofmt read {change.path}: {err}\n')
      return 1
    out, err = run_combined(['gofmt', '-w', path], root)
    if err is not None:
      return block(stdout, f'gofmt failed on {change.path}: {err}\n{trim_out(out)}')
    try:
      after = read_bytes(path)
    except OSError as err:
      write_text(stderr, f'gofmt reread {change.path}: {err}\n')
      return 1
    if before != after:
      rewritten.append(change.path)
  if not rewritten:
    return 0
  joined = ', '.join(rewritten)
  return block(
    stdout,
    'gofmt rewrote '
    + joined
    + '. Review the formatted diff, then finish again so test and review run on the formatted files.',
  )


def gate_test(root: str, event: Event, stdout, stderr) -> int:
  try:
    changes = load_changes(root, event)
  except NoSnapshot:
    return 0
  except OSError as err:
    write_text(stderr, f'{err}\n')
    return 1
  commands = test_cmds(root, changes)
  checks = gopls_cmds(root, changes)
  if not commands and not checks:
    return 0
  if checks and shutil.which('gopls') is None:
    return block(stdout, 'gopls is not on PATH. Changed Go files were not checked.')
  if commands and shutil.which('go') is None:
    return block(stdout, 'go is not on PATH. Changed Go files were not tested.')
  fails = []
  env = {key: value for key, value in os.environ.items() if key != 'GOFLAGS'}
  for item in commands:
    out, err = run_combined(['go', *item.args], item.directory, env)
    if err is None:
      continue
    where = item.directory
    try:
      rel = os.path.relpath(item.directory, root)
    except ValueError:
      rel = ''
    if rel and rel != '.':
      where = to_slash(rel)
    fails.append(f"go {' '.join(item.args)} in {where} failed:\n{trim_out(out)}")
  for args in checks:
    out, err = run_combined(args, root)
    if err is None and not out.strip():
      continue
    fails.append(f"{' '.join(args)} failed:\n{trim_out(out)}")
  if not fails:
    return 0
  return block(stdout, '\n'.join(fails))


def gate_review(root: str, event: Event, stdout, stderr) -> int:
  if os.environ.get('GROK_HOOK_EVENT', '') == 'subagent_stop':
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


def test_cmds(root: str, changes: list[Change]) -> list[GoCmd]:
  commands = []
  for module in modules_touched(root, changes):
    commands.append(GoCmd(module.directory, ['test', *module.pkgs]))
    commands.append(GoCmd(module.directory, ['vet', *module.pkgs]))
  return commands


def gopls_cmds(root: str, changes: list[Change]) -> list[list[str]]:
  commands = []
  for change in changes:
    if not is_go_source(change):
      continue
    path = os.path.join(root, from_slash(change.path))
    commands.append(['gopls', 'check', '-severity=warning', path])
  return commands


def is_go_source(change: Change) -> bool:
  return change.path.endswith('.go') and not change.after_deleted


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


def change_diff(change: Change) -> str:
  if '\0' in change.before or '\0' in change.after:
    return f'{change.path}: binary diff omitted\n'
  diff = ''.join(difflib.unified_diff(
    change.before.splitlines(keepends=True),
    change.after.splitlines(keepends=True),
    fromfile=change.path,
    tofile='/dev/null' if change.after_deleted else change.path,
    n=1,
  ))
  return diff or f'{change.path}: changed\n'


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


@dataclass
class ModuleAcc:
  all: bool = False
  pkgs: set[str] = field(default_factory=set)


def modules_touched(root: str, changes: list[Change]) -> list[ModuleWork]:
  by_dir: dict[str, ModuleAcc] = {}
  for change in changes:
    absolute = os.path.join(root, from_slash(change.path))
    module = find_module(root, absolute)
    if not module:
      continue
    acc = by_dir.get(module)
    if acc is None:
      acc = ModuleAcc()
      by_dir[module] = acc
    mod_file = rel_slash(root, os.path.join(module, 'go.mod'))
    sum_file = rel_slash(root, os.path.join(module, 'go.sum'))
    if change.path in (mod_file, sum_file):
      acc.all = True
    elif change.path.endswith('.go'):
      directory = os.path.dirname(absolute)
      try:
        rel = os.path.relpath(directory, module)
      except ValueError:
        continue
      rel = to_slash(rel)
      acc.pkgs.add('.' if rel == '.' else './' + rel)
  work = []
  for directory in sorted(by_dir):
    acc = by_dir[directory]
    if acc.all:
      pkgs = ['./...']
    else:
      pkgs = sorted(acc.pkgs)
    if pkgs:
      work.append(ModuleWork(directory, pkgs))
  return work


def find_module(root: str, path: str) -> str:
  root = os.path.normpath(root)
  try:
    is_dir = os.path.isdir(path)
  except OSError:
    is_dir = False
  directory = path if is_dir else os.path.dirname(path)
  while True:
    if os.path.isfile(os.path.join(directory, 'go.mod')):
      return directory
    if os.path.normpath(directory) == root:
      return ''
    parent = os.path.dirname(directory)
    if parent == directory:
      return ''
    directory = parent


def rel_slash(root: str, path: str) -> str:
  try:
    rel = os.path.relpath(path, root)
  except ValueError:
    return to_slash(path)
  return to_slash(rel)


def load_changes(root: str, event: Event) -> list[Change]:
  snap = read_snapshot(root, event)
  now = capture(root, protect_secrets=True) if event.client == 'codex' else capture(root)
  paths = sorted(set(snap.files) | set(now))
  changes = []
  for path in paths:
    if event.client == 'codex' and protected_path(path):
      continue
    before = snap.files.get(path)
    after = now.get(path)
    if (
      before is not None
      and after is not None
      and before.hash == after.hash
      and before.deleted == after.deleted
    ):
      continue
    if before is None:
      content, missing = head_content(root, path)
      before = FileState(hash=hash_state(content, missing), content=content, deleted=missing)
    if after is None:
      after = worktree_state(root, path)
    if before.hash == after.hash and before.deleted == after.deleted:
      continue
    changes.append(Change(
      path=path,
      before=before.content,
      after=after.content,
      before_deleted=before.deleted,
      after_deleted=after.deleted,
    ))
  return changes


def hash_state(content: str, deleted: bool) -> str:
  if deleted:
    return DELETED_HASH
  return hash_bytes(encode_text(content))


def protected_path(path: str) -> bool:
  base = to_slash(path).rsplit('/', 1)[-1].lower().strip('"\'(),;')
  return (
    base in {'.env', '.env.seed', '.env.local', '.env.development', '.env.production', '.env.test'}
    or bool(re.fullmatch(r'\.env\..+\.local', base))
    or base.endswith('.pem')
  )


def capture(root: str, protect_secrets: bool = False) -> dict[str, FileState]:
  out = git(root, 'status', '--porcelain=v1', '-uall', '-z')
  files = {}
  for path in parse_porcelain(out):
    path = to_slash(path)
    if protect_secrets and protected_path(path):
      continue
    absolute = os.path.join(root, from_slash(path))
    if os.path.isdir(absolute):
      continue
    try:
      data = read_bytes(absolute)
    except FileNotFoundError:
      files[path] = FileState(hash=DELETED_HASH, deleted=True)
      continue
    files[path] = FileState(hash=hash_bytes(data), content=decode_text(data))
  return files


def parse_porcelain(blob: bytes) -> list[str]:
  paths = []
  while blob:
    index = blob.find(b'\0')
    if index < 0:
      raise OSError('git status record missing NUL')
    rec = decode_text(blob[:index])
    blob = blob[index + 1:]
    if rec == '':
      continue
    if len(rec) < 3 or rec[2] != ' ':
      raise OSError(f'git status record {rec!r}')
    path = rec[3:]
    if rec[0] in 'RC' or rec[1] in 'RC':
      nxt = blob.find(b'\0')
      if nxt < 0:
        raise OSError('git status rename missing second path')
      paths.append(decode_text(blob[:nxt]))
      blob = blob[nxt + 1:]
    paths.append(path)
  return paths


def worktree_state(root: str, path: str) -> FileState:
  absolute = os.path.join(root, from_slash(path))
  if os.path.isdir(absolute):
    return FileState(hash=DELETED_HASH, deleted=True)
  try:
    data = read_bytes(absolute)
  except FileNotFoundError:
    content, missing = head_content(root, path)
    return FileState(hash=hash_state(content, missing), content=content, deleted=missing)
  return FileState(hash=hash_bytes(data), content=decode_text(data))


def head_content(root: str, path: str) -> tuple[str, bool]:
  try:
    out = git(root, 'show', 'HEAD:' + to_slash(path))
  except OSError:
    return '', True
  return decode_text(out), False


def git(root: str, *args: str) -> bytes:
  try:
    out = subprocess.run(
      ['git', *args],
      cwd=root,
      check=False,
      capture_output=True,
    )
  except OSError as err:
    raise OSError(f"git {' '.join(args)}: {err}") from err
  if out.returncode != 0:
    err_text = out.stderr.decode('utf-8', errors='replace').strip()
    raise OSError(f"git {' '.join(args)}: exit {out.returncode}: {err_text}")
  return out.stdout


def hash_bytes(data: bytes) -> str:
  return hashlib.sha256(data).hexdigest()


def read_snapshot(root: str, event: Event) -> Snapshot:
  path = snapshot_path(root, event)
  try:
    raw = json.loads(decode_text(read_bytes(path)))
  except FileNotFoundError as err:
    raise NoSnapshot() from err
  except json.JSONDecodeError as err:
    raise OSError(f'parse snapshot: {err}') from err
  files = {}
  for name, state in (raw.get('files') or {}).items():
    files[name] = FileState.from_json(state)
  return Snapshot(files=files, prompt=raw.get('prompt') or '')


def save_snapshot(root: str, event: Event, snap: Snapshot) -> None:
  path = snapshot_path(root, event)
  os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
  payload: dict[str, object] = {
    'files': {name: state.to_json() for name, state in snap.files.items()},
  }
  if snap.prompt:
    payload['prompt'] = snap.prompt
  data = encode_json(payload)
  tmp = path + '.tmp'
  write_bytes(tmp, data, 0o600)
  os.replace(tmp, path)


def snapshot_path(root: str, event: Event) -> str:
  digest = hashlib.sha256(encode_text(os.path.normpath(root))).hexdigest()[:16]
  return os.path.join(
    tempfile.gettempdir(),
    'stophook',
    digest,
    safe_id(event.session_id),
    safe_id(event.prompt_id) + '.json',
  )


def safe_id(value: str) -> str:
  if not value:
    return 'none'
  kept = [char for char in value if char.isalnum() or char in '-_']
  if not kept:
    return 'none'
  return ''.join(kept)


def block(stdout, reason: str) -> int:
  write_text(stdout, encode_json({'decision': 'block', 'reason': reason}).decode('utf-8'))
  return 0


def trim_out(text: str) -> str:
  text = text.replace('\r\n', '\n')
  if len(text) > 4000:
    text = text[-4000:]
  return text.strip()


def read_text(stream) -> str:
  if hasattr(stream, 'buffer'):
    return stream.buffer.read().decode('utf-8')
  data = stream.read()
  if isinstance(data, bytes):
    return data.decode('utf-8')
  return data


def write_text(stream, text: str) -> None:
  if hasattr(stream, 'buffer'):
    stream.buffer.write(text.encode('utf-8'))
    stream.buffer.flush()
    return
  stream.write(text)
  flush = getattr(stream, 'flush', None)
  if flush is not None:
    flush()


def encode_json(payload: dict[str, object]) -> bytes:
  text = json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n'
  return text.encode('utf-8')


def decode_text(data: bytes) -> str:
  return data.decode('utf-8', errors='surrogateescape')


def encode_text(text: str) -> bytes:
  return text.encode('utf-8', errors='surrogateescape')


def read_bytes(path: str) -> bytes:
  with open(path, 'rb') as handle:
    return handle.read()


def write_bytes(path: str, data: bytes, mode: int) -> None:
  fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
  try:
    os.write(fd, data)
  finally:
    os.close(fd)


def run_combined(args: list[str], cwd: str, env: dict[str, str] | None = None) -> tuple[str, Exception | None]:
  try:
    out = subprocess.run(
      args,
      cwd=cwd,
      env=env,
      check=False,
      capture_output=True,
    )
  except OSError as err:
    return '', err
  text = (out.stdout + out.stderr).decode('utf-8', errors='replace')
  if out.returncode != 0:
    return text, OSError(f'exit {out.returncode}')
  return text, None


def to_slash(path: str) -> str:
  return path.replace('\\', '/')


def from_slash(path: str) -> str:
  return path.replace('/', os.sep)


if __name__ == '__main__':
  raise SystemExit(main())
