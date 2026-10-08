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

  def test_codex_security_only_registrations(self):
    root = Path(__file__).resolve().parents[2]
    for platform in ('linux', 'windows'):
      hooks = json.loads((root / 'confs/codex' / (platform + '.hooks.json')).read_text())['hooks']
      self.assertEqual(set(hooks), {'PreToolUse', 'PostToolUse'})
      self.assertIn('interact_with_process', hooks['PostToolUse'][0]['matcher'])

  def test_permission_parity_and_mutations_prompt(self):
    root = Path(__file__).resolve().parents[2] / 'confs/codex'
    configs = [tomllib.loads((root / (platform + '.config.toml')).read_text()) for platform in ('linux', 'windows')]
    def permissions(config):
      return {name: (server.get('default_tools_approval_mode'), server.get('tools', {}), server.get('disabled_tools', [])) for name, server in config['mcp_servers'].items()}
    self.assertEqual(permissions(configs[0]), permissions(configs[1]))
    for config in configs:
      for name in ('desktop-commander', 'serena', 'gk', 'github', 'gopls'):
        self.assertEqual(config['mcp_servers'][name]['default_tools_approval_mode'], 'prompt')
      self.assertNotIn('fetch', config['mcp_servers']['gk'].get('tools', {}))
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
