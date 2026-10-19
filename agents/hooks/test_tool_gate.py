import json
import os
import tempfile
import unittest
from pathlib import Path

import tomllib
import tool_gate


def permission_list(text, name):
  marker = f'{name} = ['
  start = text.index(marker) + len(marker)
  end = text.index('\n]', start)
  return text[start:end]

class ToolGateTests(unittest.TestCase):
  def setUp(self):
    self._tmp = tempfile.TemporaryDirectory()
    self._old = os.environ.get('GROK_TOOL_GATE_STATE')
    os.environ['GROK_TOOL_GATE_STATE'] = self._tmp.name

  def tearDown(self):
    if self._old is None:
      os.environ.pop('GROK_TOOL_GATE_STATE', None)
    else:
      os.environ['GROK_TOOL_GATE_STATE'] = self._old
    self._tmp.cleanup()

  def test_git_branch_stays_allow_not_ask(self):
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'confs', 'grok')
    with open(os.path.join(root, 'config.toml'), encoding='utf-8') as handle:
      text = handle.read()
    allow = permission_list(text, 'allow')
    ask = permission_list(text, 'ask')
    deny = permission_list(text, 'deny')
    self.assertIn('"MCPTool(gk__git_branch)"', allow)
    self.assertNotIn('gk__git_branch', ask)
    self.assertNotIn('gk__git_branch', deny)

  def test_serena_rename_stays_allow(self):
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'confs', 'grok')
    with open(os.path.join(root, 'config.toml'), encoding='utf-8') as handle:
      text = handle.read()
    allow = permission_list(text, 'allow')
    deny = permission_list(text, 'deny')
    self.assertIn('"MCPTool(serena__rename_symbol)"', allow)
    self.assertNotIn('serena__rename_symbol', deny)
    self.assertNotIn('gopls__', deny)

  def test_safe_delete_stays_ask_not_allow(self):
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'confs', 'grok')
    with open(os.path.join(root, 'config.toml'), encoding='utf-8') as handle:
      text = handle.read()
    allow = permission_list(text, 'allow')
    ask = permission_list(text, 'ask')
    deny = permission_list(text, 'deny')
    self.assertIn('"MCPTool(serena__safe_delete_symbol)"', ask)
    self.assertNotIn('serena__safe_delete_symbol', allow)
    self.assertNotIn('serena__safe_delete_symbol', deny)

  def test_no_preference_registrations(self):
    root = Path(__file__).resolve().parents[2]
    for platform in ('linux', 'windows'):
      hooks = json.loads((root / 'confs/grok' / (platform + '.hooks.json')).read_text())
      commands = [hook['command'] for groups in hooks['hooks'].values() for group in groups for hook in group['hooks']]
      self.assertFalse(any('tool_gate.py' in command or ' review' in command or ' remind' in command for command in commands))

  def test_codex_security_and_readonly_stop_registrations(self):
    root = Path(__file__).resolve().parents[2]
    for platform in ('linux', 'windows'):
      hooks = json.loads((root / 'confs/codex' / (platform + '.hooks.json')).read_text())['hooks']
      self.assertEqual(set(hooks), {'PreToolUse', 'Stop'})
      stop = hooks['Stop'][0]
      self.assertNotIn('matcher', stop)
      self.assertEqual(stop['hooks'][0]['command'], hooks['PreToolUse'][0]['hooks'][0]['command'])
      self.assertEqual(stop['hooks'][0]['timeout'], 15)
      self.assertRegex('mcp__filesystem__edit_file', hooks['PreToolUse'][0]['matcher'])

  def test_permission_parity_and_mutations_prompt(self):
    root = Path(__file__).resolve().parents[2] / 'confs/codex'
    configs = [tomllib.loads((root / (platform + '.config.toml')).read_text()) for platform in ('linux', 'windows')]
    def permissions(config):
      return {name: (server.get('default_tools_approval_mode'), server.get('tools', {}), server.get('disabled_tools', [])) for name, server in config['mcp_servers'].items()}
    linux, windows = map(permissions, configs)
    self.assertEqual(linux, windows)
    for config in configs:
      for name in ('filesystem', 'serena', 'git', 'fetch', 'github', 'gopls'):
        self.assertEqual(config['mcp_servers'][name]['default_tools_approval_mode'], 'prompt')
      git = config['mcp_servers']['git']
      self.assertEqual(git['args'], ['mcp-server-git'])
      for tool in ('git_status', 'git_diff_unstaged', 'git_diff_staged', 'git_diff',
          'git_log', 'git_show', 'git_branch'):
        self.assertEqual(git['tools'][tool]['approval_mode'], 'approve', tool)
      for tool in ('git_add', 'git_commit', 'git_reset', 'git_create_branch', 'git_checkout'):
        self.assertEqual(git['tools'][tool]['approval_mode'], 'prompt', tool)
      filesystem = config['mcp_servers']['filesystem']
      for tool in ('read_file', 'read_text_file', 'read_media_file', 'read_multiple_files',
          'list_directory', 'list_directory_with_sizes', 'directory_tree',
          'search_files', 'get_file_info', 'list_allowed_directories'):
        self.assertEqual(filesystem['tools'][tool]['approval_mode'], 'approve', tool)
      for tool in ('edit_file', 'write_file', 'create_directory', 'move_file'):
        self.assertEqual(filesystem['tools'][tool]['approval_mode'], 'prompt', tool)
      self.assertEqual(config['mcp_servers']['fetch']['args'], ['mcp-server-fetch'])
      self.assertIn('merge_pull_request', config['mcp_servers']['github']['http_headers']['X-MCP-Exclude-Tools'])

  def test_state_keys_stay_within_fixture(self):
    for session, prompt in (('../session', '../../prompt'), ('.', '..'), ('..', '.')):
      path = tool_gate.state_path(session, prompt, 'security.json')
      self.assertTrue(path.resolve().is_relative_to(Path(self._tmp.name).resolve()))

  def test_quoted_command_segments(self):
    self.assertEqual(tool_gate.split_segments('echo "a;b" && cat "two words.txt"'), ['echo "a;b"', 'cat "two words.txt"'])
    self.assertEqual(tool_gate.tokenize('cat "two words.txt"'), ['cat', 'two words.txt'])

if __name__ == '__main__':
  unittest.main()
