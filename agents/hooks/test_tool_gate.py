import json
import os
import tempfile
import unittest

import tool_gate


def event(name, tool, **fields):
  payload = {
    'hook_event_name': name,
    'toolName': tool,
    'sessionId': 'parent',
    'promptId': 'turn-1',
  }
  payload.update(fields)
  return payload


def context_of(result):
  specific = result.get('hookSpecificOutput') or {}
  return specific.get('additionalContext', '')


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

  def test_deny_git_status(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'run_terminal_command',
      toolInput={'command': 'git status'},
    ))
    self.assertEqual(result['decision'], 'deny')
    self.assertIn('gk__git_status', result['reason'])

  def test_deny_git_add(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'run_terminal_command',
      toolInput={'command': 'git add'},
    ))
    self.assertEqual(result['decision'], 'deny')
    self.assertIn('gk__git_add', result['reason'])

  def test_deny_git_c_diff(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'run_terminal_command',
      toolInput={'command': 'git -C "C:\\repo with space" diff'},
    ))
    self.assertEqual(result['decision'], 'deny')
    self.assertIn('gk__git_log_or_diff', result['reason'])

  def test_deny_git_exe(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'run_terminal_command',
      toolInput={'command': r'C:\Program Files\Git\cmd\git.exe status'},
    ))
    self.assertEqual(result['decision'], 'deny')
    self.assertIn('gk__git_status', result['reason'])

  def test_allow_remote_v(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'run_terminal_command',
      toolInput={'command': 'git remote -v'},
    ))
    self.assertEqual(result['decision'], 'allow')

  def test_allow_remote_set_url(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'run_terminal_command',
      toolInput={'command': 'git remote set-url origin git@github.com-rannday:rannday/dotfiles.git'},
    ))
    self.assertEqual(result['decision'], 'allow')

  def test_deny_builtin_grep(self):
    result = tool_gate.handle(event('PreToolUse', 'grep', toolInput={'pattern': 'Install'}))
    self.assertEqual(result['decision'], 'deny')
    self.assertIn('fff__grep', result['reason'])
    self.assertIn('fff__multi_grep', result['reason'])

  def test_allow_fff_grep_pre_tool(self):
    result = tool_gate.handle(event('PreToolUse', 'fff__grep', toolInput={'query': 'Install'}))
    self.assertEqual(result['decision'], 'allow')

  def test_third_fff_grep_nudges(self):
    payload = event('PostToolUse', 'fff__grep')
    first = tool_gate.handle(payload)
    second = tool_gate.handle(payload)
    third = tool_gate.handle(payload)
    self.assertNotIn('additionalContext', json.dumps(first))
    self.assertNotIn('additionalContext', json.dumps(second))
    self.assertIn('cavecrew-investigator', context_of(third))
    self.assertNotIn('decision', third)

  def test_child_session_has_own_cap(self):
    parent = event('PostToolUse', 'fff__grep')
    child = event('PostToolUse', 'fff__grep', sessionId='child', promptId='turn-1')
    tool_gate.handle(parent)
    tool_gate.handle(parent)
    self.assertNotIn('additionalContext', json.dumps(tool_gate.handle(child)))

  def test_go_edit_without_refs_is_denied(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'search_replace',
      toolInput={'file_path': 'pkg/main.go'},
    ))
    self.assertEqual(result['decision'], 'deny')
    self.assertIn('gopls__go_symbol_references', result['reason'])
    self.assertNotIn('go_vulncheck', result['reason'])

  def test_diagnostics_before_edit_does_not_count(self):
    tool_gate.handle(event('PostToolUse', 'gopls__go_diagnostics'))
    result = tool_gate.handle(event(
      'PreToolUse',
      'write',
      toolInput={'file_path': 'pkg/main.go'},
    ))
    self.assertEqual(result['decision'], 'deny')
    self.assertIn('gopls__go_symbol_references', result['reason'])
    self.assertNotIn('go_vulncheck', result['reason'])

  def test_refs_before_edit_still_requires_diagnostics_after(self):
    tool_gate.handle(event('PostToolUse', 'gopls__go_symbol_references'))
    allowed = tool_gate.handle(event(
      'PreToolUse',
      'search_replace',
      toolInput={'file_path': 'pkg/main.go'},
    ))
    self.assertEqual(allowed['decision'], 'allow')
    recorded = tool_gate.handle(event(
      'PostToolUse',
      'search_replace',
      toolInput={'file_path': 'pkg/main.go'},
    ))
    self.assertEqual(recorded, {})
    result = tool_gate.handle(event('Stop', '', reason='end_turn'))
    self.assertEqual(result['decision'], 'block')
    self.assertIn('gopls__go_diagnostics', result['reason'])
    self.assertNotIn('gopls__go_symbol_references', result['reason'])
    self.assertNotIn('go_vulncheck', result['reason'])

  def test_diagnostics_before_edit_does_not_satisfy_stop(self):
    tool_gate.handle(event('PostToolUse', 'gopls__go_symbol_references'))
    tool_gate.handle(event('PostToolUse', 'gopls__go_diagnostics'))
    tool_gate.handle(event(
      'PostToolUse',
      'write',
      toolInput={'file_path': 'pkg/main.go'},
    ))
    result = tool_gate.handle(event('Stop', '', reason='end_turn'))
    self.assertEqual(result['decision'], 'block')
    self.assertIn('gopls__go_diagnostics', result['reason'])
    self.assertNotIn('go_vulncheck', result['reason'])

  def test_diagnostics_after_edit_lets_stop_finish(self):
    tool_gate.handle(event('PostToolUse', 'gopls__go_symbol_references'))
    tool_gate.handle(event(
      'PostToolUse',
      'search_replace',
      toolInput={'file_path': 'pkg/main.go'},
    ))
    recorded = tool_gate.handle(event('PostToolUse', 'gopls__go_diagnostics'))
    self.assertEqual(recorded, {})
    self.assertNotIn('go_vulncheck', json.dumps(recorded))
    self.assertEqual(tool_gate.handle(event('Stop', '', reason='end_turn')), {})

  def test_second_edit_requires_diagnostics_again(self):
    tool_gate.handle(event('PostToolUse', 'gopls__go_symbol_references'))
    tool_gate.handle(event(
      'PostToolUse',
      'search_replace',
      toolInput={'file_path': 'pkg/a.go'},
    ))
    tool_gate.handle(event('PostToolUse', 'gopls__go_diagnostics'))
    tool_gate.handle(event(
      'PostToolUse',
      'search_replace',
      toolInput={'file_path': 'pkg/b.go'},
    ))
    result = tool_gate.handle(event('Stop', '', reason='end_turn'))
    self.assertEqual(result['decision'], 'block')
    self.assertIn('gopls__go_diagnostics', result['reason'])

  def test_stop_blocks_when_refs_were_skipped(self):
    tool_gate.handle(event(
      'PostToolUse',
      'search_replace',
      toolInput={'file_path': 'pkg/main.go'},
    ))
    result = tool_gate.handle(event('Stop', '', reason='end_turn'))
    self.assertEqual(result['decision'], 'block')
    self.assertIn('gopls__go_symbol_references', result['reason'])
    self.assertIn('gopls__go_diagnostics', result['reason'])
    self.assertNotIn('go_vulncheck', result['reason'])

  def test_stop_without_edit_does_not_block(self):
    self.assertEqual(tool_gate.handle(event('Stop', '', reason='end_turn')), {})

  def test_stop_skips_non_end_turn(self):
    tool_gate.handle(event(
      'PostToolUse',
      'search_replace',
      toolInput={'file_path': 'pkg/main.go'},
    ))
    self.assertEqual(tool_gate.handle(event('Stop', '', reason='shutdown')), {})

  def test_subagent_stop_still_blocks(self):
    tool_gate.handle(event(
      'PostToolUse',
      'search_replace',
      toolInput={'file_path': 'pkg/main.go'},
    ))
    result = tool_gate.handle(event('SubagentStop', '', reason='shutdown'))
    self.assertEqual(result['decision'], 'block')
    self.assertNotIn('go_vulncheck', result['reason'])

  def test_go_stop_is_per_session(self):
    tool_gate.handle(event(
      'PostToolUse',
      'search_replace',
      toolInput={'file_path': 'pkg/main.go'},
    ))
    child = tool_gate.handle(event(
      'Stop',
      '',
      sessionId='child',
      promptId='turn-1',
      reason='end_turn',
    ))
    self.assertEqual(child, {})

  def test_serena_rename_go_is_denied(self):
    tool_gate.handle(event('PostToolUse', 'gopls__go_symbol_references'))
    result = tool_gate.handle(event(
      'PreToolUse',
      'serena__rename_symbol',
      toolInput={'relative_path': 'pkg/main.go', 'name_path': 'Main', 'new_name': 'Start'},
    ))
    self.assertEqual(result['decision'], 'deny')
    self.assertIn('gopls__go_rename_symbol', result['reason'])

  def test_serena_rename_non_go_is_allowed(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'serena__rename_symbol',
      toolInput={'relative_path': 'pkg/main.py', 'name_path': 'main', 'new_name': 'start'},
    ))
    self.assertEqual(result['decision'], 'allow')

  def test_serena_go_edit_without_refs_is_denied(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'serena__replace_symbol_body',
      toolInput={'relative_path': 'pkg/main.go', 'name_path': 'Main', 'body': 'package p\n'},
    ))
    self.assertEqual(result['decision'], 'deny')
    self.assertIn('gopls__go_symbol_references', result['reason'])

  def test_serena_non_go_edit_is_allowed(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'serena__replace_symbol_body',
      toolInput={'relative_path': 'pkg/main.py', 'name_path': 'main', 'body': 'pass\n'},
    ))
    self.assertEqual(result['decision'], 'allow')

  def test_serena_safe_delete_go_without_refs_is_denied(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'serena__safe_delete_symbol',
      toolInput={'relative_path': 'pkg/main.go', 'name_path_pattern': 'Main'},
    ))
    self.assertEqual(result['decision'], 'deny')
    self.assertIn('gopls__go_symbol_references', result['reason'])

  def test_serena_replace_content_go_without_refs_is_denied(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'serena__replace_content',
      toolInput={
        'relative_path': 'pkg/main.go',
        'needle': 'x',
        'repl': 'y',
        'mode': 'literal',
      },
    ))
    self.assertEqual(result['decision'], 'deny')
    self.assertIn('gopls__go_symbol_references', result['reason'])

  def test_serena_replace_content_non_go_is_allowed(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'serena__replace_content',
      toolInput={
        'relative_path': 'pkg/main.py',
        'needle': 'x',
        'repl': 'y',
        'mode': 'literal',
      },
    ))
    self.assertEqual(result['decision'], 'allow')

  def test_replace_in_files_go_glob_without_refs_is_denied(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'serena__replace_in_files',
      toolInput={'needle': 'x', 'repl': 'y', 'mode': 'literal', 'paths_include_glob': '**/*.go'},
    ))
    self.assertEqual(result['decision'], 'deny')
    self.assertIn('gopls__go_symbol_references', result['reason'])

  def test_replace_in_files_py_glob_is_allowed(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'serena__replace_in_files',
      toolInput={'needle': 'x', 'repl': 'y', 'mode': 'literal', 'paths_include_glob': '**/*.py'},
    ))
    self.assertEqual(result['decision'], 'allow')

  def test_replace_in_files_dry_run_does_not_edit(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'serena__replace_in_files',
      toolInput={
        'relative_path': 'pkg/main.go',
        'needle': 'x',
        'repl': 'y',
        'mode': 'literal',
        'dry_run': True,
      },
    ))
    self.assertEqual(result['decision'], 'allow')
    recorded = tool_gate.handle(event(
      'PostToolUse',
      'serena__replace_in_files',
      toolInput={
        'relative_path': 'pkg/main.go',
        'needle': 'x',
        'repl': 'y',
        'mode': 'literal',
        'dry_run': True,
      },
    ))
    self.assertEqual(recorded, {})
    self.assertEqual(tool_gate.handle(event('Stop', '', reason='end_turn')), {})

  def test_replace_in_files_go_edit_blocks_stop_without_diagnostics(self):
    tool_gate.handle(event('PostToolUse', 'gopls__go_symbol_references'))
    allowed = tool_gate.handle(event(
      'PreToolUse',
      'serena__replace_in_files',
      toolInput={'relative_path': 'pkg/main.go', 'needle': 'x', 'repl': 'y', 'mode': 'literal'},
    ))
    self.assertEqual(allowed['decision'], 'allow')
    tool_gate.handle(event(
      'PostToolUse',
      'serena__replace_in_files',
      toolInput={'relative_path': 'pkg/main.go', 'needle': 'x', 'repl': 'y', 'mode': 'literal'},
    ))
    result = tool_gate.handle(event('Stop', '', reason='end_turn'))
    self.assertEqual(result['decision'], 'block')
    self.assertIn('gopls__go_diagnostics', result['reason'])

  def test_replace_in_files_unscoped_without_refs_is_denied(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'serena__replace_in_files',
      toolInput={'needle': 'x', 'repl': 'y', 'mode': 'literal'},
    ))
    self.assertEqual(result['decision'], 'deny')
    self.assertIn('gopls__go_symbol_references', result['reason'])

  def test_replace_in_files_exclude_go_is_allowed(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'serena__replace_in_files',
      toolInput={
        'needle': 'x',
        'repl': 'y',
        'mode': 'literal',
        'paths_exclude_glob': '**/*.go',
      },
    ))
    self.assertEqual(result['decision'], 'allow')

  def test_hook_matchers_cover_serena_go_edits(self):
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'confs', 'grok')
    needed = (
      'serena__rename_symbol',
      'serena__safe_delete_symbol',
      'serena__replace_content',
      'serena__replace_in_files',
    )
    for name in ('windows.hooks.json', 'linux.hooks.json'):
      with open(os.path.join(root, name), encoding='utf-8') as handle:
        text = handle.read()
      for tool in needed:
        self.assertIn(tool, text)

  def test_git_branch_create_is_denied(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'gk__git_branch',
      toolInput={'directory': 'C:\\repo', 'action': 'create', 'branch_name': 'topic'},
    ))
    self.assertEqual(result['decision'], 'deny')
    self.assertIn('create', result['reason'])
    self.assertIn('Confirm in chat', result['reason'])

  def test_git_branch_create_ignores_case_and_space(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'gk__git_branch',
      toolInput={'directory': 'C:\\repo', 'action': ' Create '},
    ))
    self.assertEqual(result['decision'], 'deny')

  def test_git_branch_list_is_allowed(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'gk__git_branch',
      toolInput={'directory': 'C:\\repo', 'action': 'list'},
    ))
    self.assertEqual(result['decision'], 'allow')

  def test_git_branch_missing_action_is_allowed(self):
    result = tool_gate.handle(event(
      'PreToolUse',
      'gk__git_branch',
      toolInput={'directory': 'C:\\repo'},
    ))
    self.assertEqual(result['decision'], 'allow')

  def test_hook_matchers_cover_git_branch(self):
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'confs', 'grok')
    for name in ('windows.hooks.json', 'linux.hooks.json'):
      with open(os.path.join(root, name), encoding='utf-8') as handle:
        text = handle.read()
      self.assertIn('^gk__git_branch$', text)

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

  def test_hook_matchers_cover_github_tree_reads(self):
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'confs', 'grok')
    needed = ('github__get_file_contents', 'github__search_code')
    for name in ('windows.hooks.json', 'linux.hooks.json'):
      with open(os.path.join(root, name), encoding='utf-8') as handle:
        text = handle.read()
      for tool in needed:
        self.assertIn(tool, text)

  def test_remotes_of_host_alias(self):
    text = (
      'origin\tgit@github.com-rannday:rannday/dotfiles.git (fetch)\n'
      'upstream\thttps://github.com/sggsa/other.git (push)\n'
    )
    self.assertEqual(
      tool_gate.remotes_of(text),
      {('rannday', 'dotfiles'), ('sggsa', 'other')},
    )

  def patch_remotes(self, remotes):
    old = tool_gate.local_remotes
    tool_gate.local_remotes = lambda cwd: remotes
    self.addCleanup(lambda: setattr(tool_gate, 'local_remotes', old))

  def test_github_file_read_of_local_repo_is_denied(self):
    self.patch_remotes({('rannday', 'dotfiles')})
    result = tool_gate.handle(event(
      'PreToolUse',
      'github__get_file_contents',
      cwd='C:\\repo',
      toolInput={'owner': 'Rannday', 'repo': 'dotfiles.git', 'path': 'README.md'},
    ))
    self.assertEqual(result['decision'], 'deny')
    self.assertIn('fff', result['reason'])
    self.assertIn('gk', result['reason'])

  def test_github_file_read_of_other_repo_is_allowed(self):
    self.patch_remotes({('rannday', 'dotfiles')})
    result = tool_gate.handle(event(
      'PreToolUse',
      'github__get_file_contents',
      cwd='C:\\repo',
      toolInput={'owner': 'xai-org', 'repo': 'plugin-marketplace', 'path': 'README.md'},
    ))
    self.assertEqual(result['decision'], 'allow')

  def test_github_search_of_local_repo_is_denied(self):
    self.patch_remotes({('rannday', 'dotfiles')})
    result = tool_gate.handle(event(
      'PreToolUse',
      'github__search_code',
      cwd='C:\\repo',
      toolInput={'query': 'Install repo:rannday/dotfiles language:py'},
    ))
    self.assertEqual(result['decision'], 'deny')
    self.assertIn('local tree', result['reason'])

  def test_github_search_without_repo_qualifier_is_allowed(self):
    self.patch_remotes({('rannday', 'dotfiles')})
    result = tool_gate.handle(event(
      'PreToolUse',
      'github__search_code',
      cwd='C:\\repo',
      toolInput={'query': 'Install language:py'},
    ))
    self.assertEqual(result['decision'], 'allow')

  def test_github_file_read_without_cwd_uses_process_workspace(self):
    seen = []
    old = tool_gate.local_remotes

    def fake(cwd):
      seen.append(cwd)
      return {('rannday', 'dotfiles')}

    tool_gate.local_remotes = fake
    self.addCleanup(lambda: setattr(tool_gate, 'local_remotes', old))
    result = tool_gate.handle(event(
      'PreToolUse',
      'github__get_file_contents',
      toolInput={'owner': 'rannday', 'repo': 'dotfiles'},
    ))
    self.assertEqual(result['decision'], 'deny')
    self.assertIn('local tree', result['reason'])
    self.assertTrue(seen[0].strip())

  def test_non_go_edit_does_not_block(self):
    pre = tool_gate.handle(event(
      'PreToolUse',
      'search_replace',
      toolInput={'file_path': 'README.md'},
    ))
    self.assertEqual(pre['decision'], 'allow')
    post = tool_gate.handle(event(
      'PostToolUse',
      'search_replace',
      toolInput={'file_path': 'README.md'},
    ))
    self.assertEqual(post, {})
    self.assertEqual(tool_gate.handle(event('Stop', '', reason='end_turn')), {})


if __name__ == '__main__':
  unittest.main()
