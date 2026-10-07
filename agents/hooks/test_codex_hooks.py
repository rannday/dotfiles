import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import codex_hooks
import tool_gate
import turn_end


def event(name='PreToolUse', tool='', **fields):
  return dict(hook_event_name=name, tool_name=tool, session_id='parent', turn_id='turn-1', **fields)


class CodexHooksTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.env = patch.dict(os.environ, {'GROK_TOOL_GATE_STATE': self.temp.name})
    self.env.start()
    self.addCleanup(self.env.stop)

  def policy(self, raw):
    return codex_hooks.tool_policy(codex_hooks.normalize(raw))

  def shell_read(self, command, **fields):
    raw = event(tool='exec_command', cwd=self.temp.name, tool_input={'cmd': command})
    raw.update(fields)
    return self.policy(raw)

  def test_shell_reads_need_no_prior_mcp_call_or_project_marker(self):
    for command in ('Get-Content docs.txt', 'gc docs.txt', 'cat docs.txt',
      'type docs.txt', 'head -n 10 docs.txt', 'tail docs.txt',
      "sed -n '1,10p' docs.txt", '$lines = Get-Content docs.txt',
      'pwsh -c "gc docs.txt"', 'cmd /c "echo ok & type docs.txt"',
      'cd elsewhere; gc docs.txt', 'gc $path'):
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command).get('decision'), 'deny')
    self.assertFalse(list(Path(self.temp.name).rglob('serena-read-failures.json')))

  def test_serena_reads_create_no_fallback_state(self):
    for response in ({'isError': True}, {'content': [{'type': 'text', 'text': 'source'}]}):
      self.policy(event('PostToolUse', 'mcp__serena__read_file', cwd=self.temp.name,
        tool_input={'relative_path': 'docs.txt'}, tool_response=response))
    self.assertFalse(list(Path(self.temp.name).rglob('serena-read-failures.json')))

  def test_installed_adapter_imports_colocated_hooks_before_stale_copies(self):
    home = Path(self.temp.name) / 'home with spaces'
    stale_dir = home / '.codex/hooks/bin'
    shared_dir = home / '.agents/hooks/bin'
    stale_dir.mkdir(parents=True)
    shared_dir.mkdir(parents=True)
    source = Path(__file__).parent
    shutil.copyfile(source / 'codex_hooks.py', shared_dir / 'codex_hooks.py')
    for name in ('tool_gate.py', 'turn_end.py'):
      shutil.copyfile(source / name, shared_dir / name)
      (stale_dir / name).write_text('raise RuntimeError("stale local hook")', encoding='utf-8')
    result = subprocess.run([
      sys.executable, '-B', '-c',
      ('import pathlib,runpy,sys; '
      'sys.path.insert(0,sys.argv[3]); '
      'loaded=runpy.run_path(str(pathlib.Path(sys.argv[1])/"codex_hooks.py")); '
      'assert all(pathlib.Path(loaded[name].__file__).parent == pathlib.Path(sys.argv[2]) '
      'for name in ("tool_gate", "turn_end"))'),
      str(shared_dir), str(shared_dir), str(stale_dir),
    ], capture_output=True, text=True, check=False)
    self.assertEqual(result.returncode, 0, result.stderr)

  def test_snake_case_ids_and_mcp_names(self):
    parsed = codex_hooks.normalize(event(tool='mcp__fff__ffgrep'))
    self.assertEqual(tool_gate.ids_of(parsed), ('codex-parent', 'turn-1'))
    self.assertEqual(parsed['toolName'], 'fff__grep')
    self.assertEqual(turn_end.parse_event(parsed).prompt_id, 'turn-1')

  def test_subagent_stop_uses_child_identity(self):
    parsed = codex_hooks.normalize(event('SubagentStop', agent_id='child'))
    self.assertEqual(parsed['sessionId'], 'codex-child')

  def test_child_tool_to_subagent_stop_uses_child_turn_baseline(self):
    child = codex_hooks.normalize(dict(event(tool='apply_patch', cwd=self.temp.name), session_id='child', turn_id='child-turn'))
    with patch.object(turn_end, 'ensure_git'), patch.object(turn_end, 'write_snapshot', return_value=0):
      codex_hooks.ensure_snapshot(child)
    stop = codex_hooks.normalize(dict(event('SubagentStop', agent_id='child', cwd='parent-workspace'), turn_id='parent-turn'))
    self.assertEqual(stop['sessionId'], child['sessionId'])
    self.assertEqual(stop['promptId'], 'child-turn')
    self.assertEqual(stop['cwd'], self.temp.name)

  def test_bash_git_has_no_routing_block_in_codex_shape(self):
    with patch.object(codex_hooks, 'ensure_snapshot', return_value={}):
      result = codex_hooks.dispatch(event(tool='Bash', tool_input={'command': 'git -C repo diff'}))
    self.assertNotEqual(result.get('hookSpecificOutput', {}).get('permissionDecision'), 'deny')

  def test_exec_command_cmd_is_not_a_policy_bypass(self):
    for command in ('Get-Content .env', 'Get-Content secret.pem'):
      with self.subTest(command=command):
        result = self.policy(event(tool='exec_command', tool_input={'cmd': command}))
        self.assertEqual(result['decision'], 'deny')

  def test_recursive_windows_deletion_is_denied_in_any_argument_order(self):
    commands = (
      'Remove-Item -Recurse build',
      'remove-item build -Force -rEcUrSe',
      'Remove-Item -LiteralPath build -Recurse:$true',
      'del build /S',
      'RMDIR /q build /s',
      'rd build /s /q',
      'cmd.exe /c "del build /S"',
      'cmd /c rd build /q /s',
      'pwsh -NoProfile -Command "Remove-Item build -Recurse"',
      'powershell.exe -Command "Remove-Item -Force build -recurse"',
      'Write-Output ok; Remove-Item build -Recurse',
      'Get-ChildItem build | Remove-Item -Recurse',
      '& Remove-Item build -Recurse',
      'Remove-Item build -rec',
      'Remove-Item build -RE',
      'Remove-Item build -recur:$true',
      '& { Remove-Item build -Recurse }',
      '. { Remove-Item build -rec }',
      '& { Write-Output ok; Remove-Item build -rec }',
      'Get-ChildItem build | ForEach-Object { Remove-Item $_ -rec }',
      'pwsh -Command "& { Remove-Item build -Recurse }"',
      'cmd /c "echo ok & rd build /s"',
      'cmd /c "echo ok && del build /S"',
    )
    for command in commands:
      with self.subTest(command=command):
        result = self.policy(event(tool='exec_command', tool_input={'cmd': command}))
        self.assertEqual(result['decision'], 'deny')
        self.assertIn('Recursive Windows deletion', result['reason'])

  def test_wsl_nested_windows_deletion_keeps_guard(self):
    commands = (
      ('wsl.exe --distribution Debian --cd /tmp --exec '
        '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe '
        '-Command "Remove-Item build -Recurse"'),
      'wsl -d Debian --cd /tmp "pwsh -Command \'Remove-Item build -Recurse\'"',
      'wsl.exe -d Debian -e cmd.exe /c "rd build /s"',
    )
    for command in commands:
      with self.subTest(command=command):
        self.assertTrue(codex_hooks.recursive_windows_delete(command))
    for command in (
      'wsl.exe -d Debian -e printf "%s" "Remove-Item build -Recurse"',
      'wsl.exe -d Debian "printf \'%s\' \'Remove-Item build -Recurse\'"',
      'wsl.exe -d Debian -e pwsh -Command "Remove-Item build.txt"',
    ):
      with self.subTest(command=command):
        self.assertFalse(codex_hooks.recursive_windows_delete(command))

  def test_nonrecursive_deletion_and_quoted_text_are_allowed(self):
    commands = (
      'Remove-Item build.txt',
      'Remove-Item -Force build.txt',
      "Remove-Item -LiteralPath '-Recurse'",
      'del build.txt /q',
      'rmdir empty',
      'rd empty',
      'Write-Output "Remove-Item build -Recurse"',
      'echo del build /s',
      'Remove-Item build.txt; Write-Output -Recurse',
      'cmd /c "echo del build /s"',
      'pwsh -Command "Write-Output Remove-Item -Recurse"',
      '"Remove-Item build -Recurse"',
      'Remove-Item build -Recurse:$false',
      'Remove-Item build -rec:false',
      '& { Remove-Item build -Recurse:$false }',
      '& { Write-Output "Remove-Item build -Recurse" }',
      'Write-Output "& { Remove-Item build -Recurse }"',
      'Get-ChildItem build | ForEach-Object { Write-Output "Remove-Item -rec" }',
      'cmd /c \'echo "ok & rd build /s"\'',
    )
    for command in commands:
      with self.subTest(command=command):
        result = self.policy(event(tool='exec_command', tool_input={'cmd': command}))
        self.assertNotEqual(result.get('decision'), 'deny')

  def test_apply_patch_multiple_paths_require_go_refs(self):
    command = '*** Begin Patch\n*** Update File: docs.md\n*** Update File: pkg/main.go\n*** End Patch'
    result = self.policy(event(tool='apply_patch', tool_input={'command': command}))
    self.assertEqual(result['decision'], 'deny')

  def test_patch_move_and_delete_paths(self):
    self.assertEqual(codex_hooks.patch_paths('*** Delete File: old.go\n*** Move to: new.go'), ['old.go', 'new.go'])

  def test_new_go_file_does_not_require_nonexistent_refs(self):
    command = '*** Begin Patch\n*** Add File: pkg/new.go\n+package pkg\n*** End Patch'
    self.assertEqual(self.policy(event(tool='apply_patch', tool_input={'command': command})), {})
    self.policy(event('PostToolUse', 'apply_patch', tool_input={'command': command}))
    result = codex_hooks.stop(codex_hooks.normalize(event('Stop')))
    self.assertEqual(result['decision'], 'block')
    self.assertIn('diagnostics', result['reason'])
    self.assertNotIn('symbol_references', result['reason'])

  def test_go_edit_invalidates_prior_diagnostics(self):
    self.policy(event('PostToolUse', 'mcp__gopls__go_symbol_references'))
    command = '*** Update File: pkg/main.go\n@@\n-x\n+y'
    self.assertEqual(self.policy(event(tool='apply_patch', tool_input={'command': command})), {})
    self.policy(event('PostToolUse', 'apply_patch', tool_input={'command': command}))
    self.policy(event('PostToolUse', 'mcp__gopls__go_diagnostics'))
    self.assertEqual(tool_gate.handle(codex_hooks.normalize(event('Stop'))), {})
    self.policy(event('PostToolUse', 'apply_patch', tool_input={'command': command}))
    self.assertEqual(tool_gate.handle(codex_hooks.normalize(event('Stop')))['decision'], 'block')

  def test_failed_mcp_refs_do_not_count(self):
    self.policy(event('PostToolUse', 'mcp__gopls__go_symbol_references', tool_response={'isError': True}))
    result = self.policy(event(tool='mcp__serena__replace_symbol_body', tool_input={'relative_path': 'main.go'}))
    self.assertEqual(result['decision'], 'deny')

  def test_failed_patch_does_not_record_edit(self):
    self.policy(event('PostToolUse', 'apply_patch', tool_input={'command': '*** Update File: main.go'}, tool_response={'error': 'failed'}))
    self.assertEqual(tool_gate.handle(codex_hooks.normalize(event('Stop'))), {})

  def test_serena_go_rename_requires_refs_without_routing_block(self):
    self.assertEqual(self.policy(event(tool='mcp__serena__rename_symbol', tool_input={'relative_path': 'main.go'}))['decision'], 'deny')
    self.policy(event('PostToolUse', 'mcp__gopls__go_symbol_references'))
    renamed = event(tool='mcp__serena__rename_symbol', tool_input={'relative_path': 'main.go'})
    self.assertEqual(self.policy(renamed)['decision'], 'allow')
    self.policy(dict(renamed, hook_event_name='PostToolUse'))
    self.assertIn('diagnostics', self.policy(event('Stop'))['reason'])
    self.policy(event('PostToolUse', 'mcp__gopls__go_diagnostics'))
    self.assertEqual(self.policy(event('Stop')), {})
    self.assertEqual(self.policy(event(tool='mcp__serena__rename_symbol', tool_input={'relative_path': 'main.py'}))['decision'], 'allow')

  def test_github_checkout_read_has_no_routing_block(self):
    with patch.object(tool_gate, 'local_remotes', return_value={('user', 'repo')}):
      result = self.policy(event(tool='mcp__github__get_file_contents', tool_input={'owner': 'user', 'repo': 'repo'}))
    self.assertNotEqual(result.get('decision'), 'deny')

  def test_search_routing_has_no_blocks_or_nudges(self):
    results = [self.policy(event('PostToolUse', 'mcp__fff__ffgrep')) for _ in range(4)]
    self.assertEqual(results, [{}, {}, {}, {}])
    for tool in ('grep', 'Grep'):
      self.assertNotEqual(self.policy(event(tool=tool)).get('decision'), 'deny')
    self.assertFalse(list(Path(self.temp.name).rglob('fff-grep.count')))

  def test_native_and_desktop_shell_routing_is_allowed_on_both_platforms(self):
    for shell in ('powershell', 'pwsh', 'bash', 'sh'):
      for tool, key in (('exec_command', 'cmd'),
          ('mcp__desktop_commander__start_process', 'command')):
        with self.subTest(shell=shell, tool=tool):
          self.assertNotEqual(self.policy(event(tool=tool,
            tool_input={key: 'git diff', 'shell': shell})).get('decision'), 'deny')
          self.assertEqual(self.policy(event(tool=tool,
            tool_input={key: 'cat .env', 'shell': shell}))['decision'], 'deny')

  def test_branch_creation_uses_host_approvals_not_permanent_deny(self):
    self.assertEqual(self.policy(event(tool='mcp__gk__git_branch', tool_input={'action': 'create'})), {})

  def test_secret_paths_read_shell_and_patch(self):
    for tool, data in (
      ('read_file', {'path': 'repo/.env'}),
      ('Bash', {'command': 'Get-Content "C:\\repo\\secret.pem"'}),
      ('apply_patch', {'command': '*** Add File: .env.production'}),
      ('mcp__serena__replace_content', {'relative_path': '.env.dev.local'}),
      ('mcp__desktop_commander__read_file', {'path': 'C:/repo/.env.local'}),
      ('mcp__desktop_commander__get_file_info', {'path': 'keys/server.pem'}),
      ('mcp__desktop_commander__read_multiple_files', {'paths': ['notes.txt', 'keys/server.pem']}),
      ('mcp__desktop_commander__write_file', {'path': '.env.seed', 'content': 'secret'}),
      ('mcp__desktop_commander__move_file', {'source': 'secret.pem', 'destination': 'notes.txt'}),
      ('mcp__desktop_commander__move_file', {'source': 'notes.txt', 'destination': '.env.test'}),
    ):
      with self.subTest(tool=tool):
        self.assertEqual(self.policy(event(tool=tool, tool_input=data))['decision'], 'deny')
    self.assertFalse(codex_hooks.secret_paths(codex_hooks.normalize(event(tool='read_file', tool_input={'path': '.env.example'}))))
    for tool, data in (
      ('read_file', {'path': 'C:/repo/docs.txt', 'offset': 0, 'length': 10}),
      ('read_multiple_files', {'paths': ['docs.txt', '.env.example']}),
    ):
      self.assertNotEqual(self.policy(event(tool='mcp__desktop_commander__' + tool,
        tool_input=data)).get('decision'), 'deny')

  def test_wrapped_shell_secret_paths_stay_denied(self):
    for command in ('gc .env', 'Get-Content (".env") -TotalCount 10',
      'pwsh -c "gc .env"', 'cmd /c "type secret.pem"',
      'bash -lc "cat .env.production"', 'gc .env; Write-Output ok'):
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command).get('decision'), 'deny')

  def test_shell_glob_quotes_and_line_continuations(self):
    denied = (
      "cat '.en'?", "cat .en'v'", "cat '.env'", 'cat "key.pem"',
      "bash -lc 'cat *'", "cat '.en'?[a-z]*",
      'cat .en\\\nv', 'cat .en\\\r\nv', 'cat key.p\\\nem',
      'cat ".en\\\nv"',
      'cat .en"${suffix}"', 'cat key.p"${extension}"',
      'Get-Content .`\nenv', 'Get-Content .`\r\nenv',
      'Get-Content ".`\nenv"', "pwsh -c 'Get-Content .`\nenv'",
      "bash -lc 'cat .en\\\nv'",
    )
    allowed = (
      "echo '*'", 'echo "?"', "echo '[.]env'", 'echo "[[:alpha:]]"',
      r'echo \*', r'echo \?', r'echo \[.]env',
      "cat '.en?'", "cat '.en*'", "cat '.en'\"?\"",
      "cat '.en'?\"*\"",
      "cat '.env.example'*'.txt'", "bash -lc 'echo \"*\"'",
      'cat doc\\\ns.txt', 'cat doc\\\r\ns.txt',
      "cat '.en\\\nv'", "echo '.e{nv,x}'",
      'cat "${prefix}*.pdf"', 'cat "${prefix}?.txt"',
      'Get-Content doc`\ns.txt', 'Get-Content doc`\r\ns.txt',
      "Get-Content '.`\nenv'",
    )
    for command in denied:
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command).get('decision'), 'deny')
    for command in allowed:
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'bash'}).get('decision'), 'deny')

  def test_wsl_implicit_shell_keeps_secret_guards(self):
    commands = (
      'wsl.exe --distribution Debian --cd /tmp "cat .env"',
      'wsl.exe -d Debian --cd /tmp cat .en[v]',
      'wsl --distribution=Debian --cd=/tmp "cat .en?"',
      '& "C:\\Windows\\System32\\wsl.exe" -d Debian "cat secret.pem"',
      'wsl.exe -d Debian --exec sh -c "cat .en[v]"',
    )
    for command in commands:
      with self.subTest(command=command):
        self.assertTrue(codex_hooks.shell_secret_paths(command, 'powershell'))

  def test_wsl_direct_exec_and_quoted_output_stay_literal(self):
    commands = (
      'wsl.exe -d Debian --cd /tmp --exec cat .en[v]',
      'wsl.exe --distribution=Debian --cd=/tmp -e cat .en?',
      'wsl.exe -d Debian "printf \'%s\' \'.en[v]\'"',
      'wsl.exe -d Debian --exec printf "%s" ".en[v]"',
      'wsl.exe --list --verbose',
    )
    for command in commands:
      with self.subTest(command=command):
        self.assertFalse(codex_hooks.shell_secret_paths(command, 'powershell'))

  def test_shell_redirections_keep_secret_guards(self):
    denied = (
      'cat <.env', 'cat<.env', 'cat 0<.env', "cat <'.env'",
      'echo ok >secret.pem', 'echo ok 2>secret.pem', 'echo ok >>secret.pem',
      'echo ok &>secret.pem', 'echo ok >|secret.pem', 'cat <.en"v"',
      'bash -lc \'cat<.env\'', 'cmd /c "type <.env"',
    )
    allowed = (
      'cat <docs.txt', 'echo ok 2>report.txt', 'cat 0<"docs with spaces.txt"',
      'echo "<.env"', "echo '>notes.txt'", 'cat "<docs.txt"',
      r'cat \<docs.txt', r'cat docs\>notes.txt', 'type ^<docs.txt', r'cat \<.env',
    )
    for command in denied:
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command).get('decision'), 'deny')
    for command in allowed:
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command).get('decision'), 'deny')

  def test_powershell_quoted_path_wildcards_keep_secret_guards(self):
    denied = (
      'Get-Content ".en?"', "gc '*.pem'", 'cat -Path ".en?"',
      'type -Path "*.pem"', 'Get-Content -LiteralPath docs.txt -Path "*.pem"',
      'Get-Content -Path:".en?"', 'Get-Content -LiteralPath:.env',
      r'Microsoft.PowerShell.Management\Get-Content ".en?"',
      'Remove-Item "*.pem"', 'Set-Content -Path ".en?" -Value ok',
      'Add-Content ".en?" ok', 'Clear-Content "*.pem"',
      'Copy-Item "*.pem" docs.txt', 'Move-Item "*.pem" docs.txt',
      'Get-Content -LiteralPath ".env"', 'Get-Content -LiteralPath "key.pem"',
      'Write-Output ok; gc ".en?"', 'Write-Output ok | gc "*.pem"',
      "pwsh -Command 'gc \".en?\"'", "bash -lc 'pwsh -c \"gc .en?\"'",
    )
    allowed = (
      'Write-Output "*"', "echo '*'", 'Get-Content "*.txt"',
      'Get-Content -LiteralPath ".en?"', 'gc -LiteralPath ".en?"',
      'Remove-Item -LiteralPath ".en?"',
      'Get-Content -LiteralPath .en?', 'gc -LiteralPath:".en?"',
      r'Microsoft.PowerShell.Management\Get-Content -LiteralPath ".en?"',
      'Set-Content docs.txt -Value "*"', 'Select-String docs.txt -Pattern "*"',
      "bash -lc 'cat \"*\"'", "bash -lc 'echo \"*\"'",
    )
    for command in denied:
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')
    for command in allowed:
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')

  def test_powershell_explicit_path_parameters_keep_secret_guards(self):
    denied = (
      'Import-Csv -Path "*.pem"', 'Import-Csv ".en?"',
      'Import-Clixml "*.pem"', 'Import-Csv -Path ".env"',
      'Invoke-Custom -Path ".en?"', 'Invoke-Custom -Path:"*.pem"',
      'Invoke-Custom -Path @("docs.txt"; ".en`?")',
      'Invoke-Custom -Path (".en?")',
      'Write-Output (Invoke-Custom -Path "*.pem")',
      '& { Invoke-Custom -Path ".en?" }',
      "pwsh -c 'Import-Csv -Path \"*.pem\"'",
    )
    allowed = (
      'Import-Csv "*.csv"', 'Import-Clixml -Path "*.xml"',
      'Invoke-Custom -Path "*.txt"', 'Invoke-Custom -LiteralPath ".en?"',
      'Invoke-Custom -LiteralPath:".en?"',
      'Invoke-Custom -LiteralPath @(".en?")',
      'Invoke-Custom -Value @("ok"; "*")',
      'Invoke-Custom -Pattern @("ok"; "*")', 'Write-Output "*"',
      'Write-Output "Example -Path .en?"',
      'Write-Output (Invoke-Custom -LiteralPath ".en?") "*"',
    )
    for command in denied:
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')
    for command in allowed:
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')

  def test_powershell_path_binding_survives_unrelated_options(self):
    denied = (
      'Get-Content -Path -TotalCount 10 ".en?"',
      'Get-Content -LiteralPath -TotalCount 10 ".env"',
      'Get-Content -LiteralPath -Encoding utf8 "key.pem"',
      'Get-Content -Path -Tail:10 ".en?"',
      'Get-Content -Path -Raw ".en?"',
      'Get-Content -Path -ReadCount 1 @("docs.txt"; ".en?")',
    )
    allowed = (
      'Get-Content -LiteralPath -TotalCount 10 ".en?"',
      'Get-Content -LiteralPath -Tail:10 ".en?"',
      'Get-Content -LiteralPath -Encoding utf8 -ReadCount 1 ".en?"',
      'Get-Content -LiteralPath -Raw ".en?"',
      'Get-Content -Path docs.txt -Encoding "*"',
      'Get-Content -LiteralPath -Tail 1 @(".en?"; "*.txt")',
      'Get-Content -Path docs.txt -Include @("ok"; "*.txt")',
      'Get-Content -Path docs.txt -Encoding:"*"',
    )
    for command in denied:
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')
    for command in allowed:
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')

  def test_powershell_provider_selection_patterns_are_checked(self):
    denied = (
      'Get-ChildItem keys -Filter "*.pem"',
      'Get-ChildItem -LiteralPath keys -Filt ".en?"',
      'Get-ChildItem keys -Filter:"*.pe`?"',
      'Get-ChildItem keys -Include @("*.txt"; ".en?")',
      'Get-ChildItem keys -Inc ("*.pem")',
      'Get-ChildItem keys -Exclude @(".env"; "*.pem") -Include ".en?"',
      'Get-ChildItem keys -Exclude "$(Get-Content .env)"',
      'pwsh -c \'Get-ChildItem keys -Filter "*.pem"\'',
    )
    allowed = (
      'Get-ChildItem keys -Filter "*.txt"',
      'Get-ChildItem keys -Include @("*.txt"; "*.pdf")',
      'Get-ChildItem keys -Exclude "*.pem"',
      'Get-ChildItem keys -Excl @(".env"; "*.pem")',
      'Get-ChildItem keys -Exclude:".env"',
      'Get-Content -LiteralPath docs.txt -Filter "*.txt" ".en?"',
      'Get-Content -LiteralPath docs.txt -Include @("*.txt"; "*.pdf") ".en?"',
      'Set-Content docs.txt -Value "*"',
      'Select-String docs.txt -Pattern "*"',
      'Write-Output -Filter "*"',
    )
    for command in denied:
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')
    for command in allowed:
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')

  def test_powershell_unquoted_wildcards_require_path_context(self):
    allowed = (
      'Write-Output *', 'Write-Output @(*; ?; [abc])',
      'Set-Content docs.txt -Value *', 'Select-String docs.txt -Pattern *',
      'Set-Content docs.txt -Value @(*; ?)',
      'Select-String docs.txt -Pattern @(*; ?)',
      'Write-Output docs.txt >output.txt',
      'Write-Output docs.txt >output.txt *',
      'Write-Output "docs>file" *', 'Write-Output docs`>file *',
      "pwsh -c 'Write-Output *'",
    )
    denied = (
      'gc *', 'Get-Content -Path *', 'Get-ChildItem docs -Filter *',
      'Write-Output docs >*.pem', 'Write-Output docs 2>>.en?',
      'Write-Output docs > *', 'Write-Output docs > ".en?"',
      'Write-Output docs>>".en`?"', 'Write-Output docs 3>*.pe?',
      "pwsh -c 'Get-Content *'",
      'Write-Output .env', 'Write-Output key.pem',
      'Write-Output "$(Get-Content .env)"',
    )
    for command in allowed:
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')
    for command in denied:
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')
    self.assertEqual(self.shell_read('echo *',
      tool_input={'cmd': 'echo *', 'shell': 'bash'}).get('decision'), 'deny')

  def test_powershell_parameter_prefixes_preserve_path_binding(self):
    denied = (
      'Get-Content -LiteralPath docs.txt -Pa "*.pem"',
      'Get-Content -Lit docs.txt -Pa:".en?"',
      'Get-Content -LiteralPath docs.txt -P @(".en?")',
      'Get-Content -Lit -Tot 10 ".env"',
      'Get-Content -Pa -Tot:10 @(".en?")',
      'Select-String -LiteralPath docs.txt -P "*.pem"',
      'Invoke-Custom -LiteralPath docs.txt -Pa "*.pem"',
      'pwsh -c \'gc -Lit docs.txt -Pa "*.pem"\'',
    )
    allowed = (
      'Get-Content -Lit ".en?"', 'Get-Content -Lit:".en?"',
      'Get-Content -Lit -Tot 10 @(".en?")',
      'Get-Content -Lit -Tot:10 ".en?"',
      'Get-Content -Pa docs.txt -Enc "*"',
      'Select-String -LiteralPath docs.txt -Patt "*"',
    )
    for command in denied:
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')
    for command in allowed:
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')

  def test_explicit_bash_keeps_quoted_path_wildcards_literal(self):
    for command in ('cat ".en?"', "cat '.en*'", 'echo "*"'):
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': '/bin/bash'}).get('decision'), 'deny')

  def test_powershell_provider_paths_expand_shell_escaped_wildcards(self):
    denied = (
      'Get-Content ".en`?"', 'Get-Content -Path ".en`?"',
      'Get-Content -Path:".en`?"', 'Get-Content "`*.p[e]m"',
      'Get-Content "`*.pe`?"',
      'Get-Content "*.p`[e]m"', 'Remove-Item ".en`?"',
      'Get-Content -Path @("docs.txt"; ".en`?")',
      "pwsh -Command 'gc \".en`?\"'",
    )
    allowed = (
      'Get-Content -LiteralPath ".en`?"',
      'Get-Content -LiteralPath:".en`?"', 'Get-Content "docs`?.txt"',
      'Write-Output "`*"', 'Set-Content docs.txt -Value "`*"',
      'Select-String docs.txt -Pattern "`*"',
      'Get-Content -LiteralPath @(".en`?")',
      "bash -lc 'cat \".en\\?\"'",
    )
    for command in denied:
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')
    for command in allowed:
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')

  def test_powershell_assignments_keep_path_wildcard_guards(self):
    denied = (
      '$x=Get-Content "*.pem"', '$x=Get-Content "*.p[e]m"', '$x=gc ".en?"',
      '$x =Get-Content ".en?"', '$x= Get-Content ".en?"',
      '$x = Get-Content ".en?"', '[string]$x=Get-Content ".en?"',
      '$x=".env"', "$x='key.pem'",
      "pwsh -c '$x=gc \".en?\"'",
    )
    allowed = (
      '$x=Get-Content -LiteralPath ".en?"', '$x=Get-Content "*.txt"',
      '$x=Write-Output "*"', '$x =Write-Output "*"',
      '[string]$x = Get-Content -LiteralPath ".en?"',
      "$x='*'", '$x=".en?"', "$x='[.]env'", '[string]$x="*"',
    )
    for command in denied:
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')
    for command in allowed:
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')

  def test_powershell_parser_casts_allow_native_and_desktop_commands(self):
    command = ('$parseTokens = $null\n$parseErrors = $null\n'
      '[void][System.Management.Automation.Language.Parser]::ParseFile('
      "'modules/ssh.ps1', [ref]$parseTokens, [ref]$parseErrors)\n"
      'if ($parseErrors.Count -gt 0) { $parseErrors; exit 1 }\n'
      "Write-Output 'PowerShell syntax: passed'")
    for shell in ('powershell', 'pwsh'):
      for tool, key in (('exec_command', 'cmd'),
          ('mcp__desktop_commander__start_process', 'command')):
        with self.subTest(shell=shell, tool=tool):
          self.assertNotEqual(self.policy(event(tool=tool,
            tool_input={key: command, 'shell': shell})).get('decision'), 'deny')
    # Live native Windows exec events use Bash/command with no shell field.
    native = codex_hooks.normalize(event(tool='Bash', tool_input={'command': command}))
    with patch.object(codex_hooks.os, 'name', 'nt'):
      self.assertNotEqual(codex_hooks.tool_policy(native).get('decision'), 'deny')
    wrapped = "pwsh -Command '" + command.replace("'", '"') + "'"
    self.assertFalse(codex_hooks.shell_secret_paths(wrapped, 'bash'))

  def test_bash_event_alias_preserves_host_and_explicit_shell_guards(self):
    for platform in ('nt', 'posix'):
      for command in ('Get-Content .env', 'cat secret.pem'):
        native = codex_hooks.normalize(event(tool='Bash', tool_input={'command': command}))
        with self.subTest(platform=platform, command=command), patch.object(codex_hooks.os, 'name', platform):
          self.assertEqual(codex_hooks.tool_policy(native)['decision'], 'deny')
    for platform, explicit in (('posix', None), ('nt', 'bash')):
      data = {'command': 'echo *'}
      if explicit:
        data['shell'] = explicit
      native = codex_hooks.normalize(event(tool='Bash', tool_input=data))
      with self.subTest(platform=platform, explicit=explicit), patch.object(codex_hooks.os, 'name', platform):
        self.assertEqual(codex_hooks.tool_policy(native)['decision'], 'deny')

  def test_powershell_type_syntax_preserves_secret_and_provider_guards(self):
    allowed = (
      '[ref]$parseTokens', '[string[]]$names',
      '[System.Management.Automation.Language.Token[]]$parseTokens',
      '[string]$name = "docs.txt"', '$name=[string]$value',
      '[string]"docs.txt"', '[string]($value)',
    )
    denied = (
      'Get-Content -Path [ref]$path', 'Get-Content [ref]$path',
      'Invoke-Custom -Path "[ref]$path"', 'Get-Content "[ref]$path"',
      'Get-Content -Path "*.pem"', 'Get-Content -Path "[.]env"',
      '[ref]$parseTokens; Get-Content .env',
      '[string]".env"', '[string]"key.pem"',
      '$name=[string]".env"', '[string[]]$names = Get-Content "*.pem"',
    )
    for shell in ('powershell', 'pwsh'):
      for command in allowed:
        with self.subTest(shell=shell, command=command):
          self.assertFalse(codex_hooks.shell_secret_paths(command, shell))
      for command in denied:
        with self.subTest(shell=shell, command=command):
          self.assertTrue(codex_hooks.shell_secret_paths(command, shell))
    for shell in ('bash', 'sh'):
      for command in ('cat [ref]$path', 'cat [.]env', 'cat *.pem',
          'pwsh -Command \'[ref]$tokens; Get-Content -Path "*.pem"\''):
        with self.subTest(shell=shell, command=command):
          self.assertTrue(codex_hooks.shell_secret_paths(command, shell))

  def test_powershell_grouped_commands_keep_path_wildcard_guards(self):
    denied = (
      'Write-Output (Get-Content ".en?")', 'Write-Output ((gc "*.pem"))',
      'Write-Output ((gc "*.p[e]m"))', '$x=(gc ".en?")',
      "pwsh -c 'Write-Output (gc \".en?\")'",
    )
    allowed = (
      'Write-Output (Get-Content -LiteralPath ".en?") "*"',
      'Write-Output ((gc "*.txt")) "*"', '$x=(gc -LiteralPath ".en?")',
      'Write-Output "(Get-Content .en?)"', "Write-Output '(gc .en?)'",
      "bash -lc '(cat \".en?\")'",
    )
    for command in denied:
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')
    for command in allowed:
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')

  def test_powershell_grouped_path_arguments_keep_secret_guards(self):
    denied = (
      'Get-Content -Path @(".en?")', "Get-Content @('*.pem')",
      "Get-Content @('*.p[e]m')", 'Get-Content -Path (".en?")',
      'Get-Content -Path @("docs.txt", ".en?")',
      'Get-Content -Path @("docs.txt"), @(".en?")',
      'Get-Content -Path @("docs.txt"; ".en?")',
      'Get-Content -Path @("docs.txt"\n ".en?")',
      'Get-Content -Path @("docs.txt"\r\n ".en?")',
      'Write-Output (gc -Path @(".en?"))',
    )
    allowed = (
      "Get-Content -LiteralPath @('.en?')", 'Get-Content -Path @("*.txt")',
      "Write-Output @('*')", 'Write-Output (gc docs.txt) "*"',
      'Set-Content docs.txt -Value @("*")',
      'Select-String docs.txt -Pattern @("*")',
      'Set-Content docs.txt -Value @("ok"; "*")',
      'Set-Content docs.txt -Value @("ok"\n "*")',
      'Select-String docs.txt -Pattern @("ok"; "*")',
      'Select-String docs.txt -Pattern @("ok"\n "*")',
      'Write-Output (gc docs.txt; echo "*")',
    )
    for command in denied:
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')
    for command in allowed:
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')

  def test_powershell_script_blocks_keep_path_wildcard_guards(self):
    denied = (
      '& { Get-Content "*.pem" }', '&{gc ".en?"}',
      '& { Write-Output ok; Get-Content ".en?" }',
      '& { & { Remove-Item "*.pem" } }',
      '$block={ Get-Content -Path ".en`?" }; & $block',
      'Set-Content docs.txt -Value { Get-Content "*.pem" }',
      "pwsh -Command '& { gc \".en?\" }'",
    )
    allowed = (
      '& { Get-Content "*.txt" }', '& { Write-Output "*" }',
      '& { gc -LiteralPath ".en?"; echo "*" }',
      'Write-Output "{ Get-Content .en? }"',
      "Write-Output '{ Get-Content *.pem }'",
      'Set-Content docs.txt -Value { Write-Output "*" }',
      'Select-String docs.txt -Pattern { Write-Output "*" }',
      '& { Get-Content ${path} }',
      '& { gc -LiteralPath @(".en?"); Write-Output "*" }',
      "bash -lc 'cat report.{txt,pdf}'",
    )
    for command in denied:
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')
    for command in allowed:
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')

  def test_rg_negative_filters_do_not_select_secret_paths(self):
    commands = (
      "rg --files -g '!*.pem'", "rg --files -g'!*.pem'",
      "rg --files --glob '!*.pem'", "rg --files --glob='!*.pem'",
      "rg --files --iglob '!*.pem'", "rg --files --iglob='!*.pem'",
      "rg --files -g '!**/.env'", "rg --files -g '!**/.env.*.local'",
      "rg --files -g '!*.pem'; rg --files -g '!*.pem'",
    )
    for shell in ('pwsh', 'bash', 'cmd'):
      for command in commands:
        with self.subTest(shell=shell, command=command):
          self.assertFalse(codex_hooks.shell_secret_paths(command, shell))

  def test_rg_filter_exemptions_keep_secret_guards(self):
    commands = (
      "rg --files -g '*.pem'", "rg --files --glob='*.pem'",
      "rg --files --iglob='*.pem'", "rg --files -g '!*.pem' key.pem",
      "cat -g '!*.pem'", "rg --files -g; cat '!*.pem'",
      "rg --files -g > '!*.pem'", "rg --files -g '!*.pem' > key.pem",
      "rg --files -g '!*.pem'; cat key.pem",
      "rg --files -g '!*.pem' | cat key.pem",
      "rg --files -- -g '!*.pem'",
      "rg -e -g '!*.pem'", "rg --sort -g '!*.pem'",
      "rg --files --replace -g '!key.pem'", "rg --files -r -g '!key.pem'",
      'rg --files -g "!$(cat key.pem)"',
      'rg --files --glob="!$path.pem"',
    )
    for shell in ('pwsh', 'bash'):
      for command in commands:
        with self.subTest(shell=shell, command=command):
          self.assertTrue(codex_hooks.shell_secret_paths(command, shell))
    self.assertTrue(codex_hooks.shell_secret_paths('rg --files -g !*.pem', 'bash'))
    self.assertTrue(codex_hooks.shell_secret_paths('rg --files --glob="!`cat key.pem`"', 'bash'))

  def test_shell_globs_keep_secret_guards(self):
    denied = (
      'cat .en?', 'cat *.pem', 'cat *', 'cat .*',
      'cat *.p[e]m', 'cat .en[a-z]', 'cat .en[!x]', 'cat .en[^x]',
      'cat .env.example*', 'cat /tmp/.en?', 'cat /tmp/*.p[e]m',
      'cat .e{nv,x}', 'cat key.{pem,txt}', 'cat /tmp/.e{nv,x}',
      'cat .en[[:alpha:]]', 'cat *.p[[:alpha:]]m',
      'cat .en[[:digit:]v]', 'cat .en[[:unknown:]]',
      'cat .en[[:alnum:]]', 'cat .en[[:lower:]]', 'cat .en[[:upper:]]',
      'cat *.p[[:xdigit:]]m', 'cat .en[![:upper:]]', 'cat .en[!V]',
      'cat .en[!v]', 'cat *.p[!e]m',
    )
    allowed = (
      'cat *.txt', 'cat *.pdf', 'cat .env.example',
      'cat .env.example.*.txt', 'cat .en[!vV]', 'cat .en[a-u]',
      'cat *.p[!eE]m', 'cat /tmp/*.txt', 'cat /tmp/[a-z]*.pdf',
      'cat report.{txt,pdf}', 'cat .e{nx,ny}',
      'cat */docs.${extension}.txt',
      'cat *.p[[:digit:]]m', 'cat .en[![:alpha:]]',
    )
    for command in denied:
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command).get('decision'), 'deny')
    for command in allowed:
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command).get('decision'), 'deny')

  def test_bash_ansi_c_quoted_secret_paths_stay_denied(self):
    denied = (
      r"cat $'.en\x76'", r"cat $'\056env'", r"cat $'.en\166'",
      r"cat $'.en\u0076'", r"cat $'.en\U00000076'",
      r"cat key.$'p\x65m'", r"cat $'key.\160em'",
      r"cat $'\x2eenv.production'", r"cat $'.env\0.example'",
      r'''bash -lc "cat $'.en\x76'"''',
      r"bash -lc $'cat \x2eenv'",
    )
    allowed = (
      r"cat $'docs\x2etxt'", r"cat $'report\056pdf'",
      r"cat $'.env\x2eexample'", r"echo $'\x2a'", r"echo $'\077'",
      r"echo $'\133.\135env'", r"cat $'docs\tfile.txt'",
      r"echo $'\a\b\e\f\n\r\t\v\cA'", r"cat $'docs\'file.txt'",
      r"cat '.en\x76'", r"echo $'$(cat .env)'",
    )
    for command in denied:
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'bash'}).get('decision'), 'deny')
    for command in allowed:
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'bash'}).get('decision'), 'deny')
    command = r"Write-Output $'.en\x76'"
    self.assertNotEqual(self.shell_read(command,
      tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')

  def test_fragmented_shell_secret_paths_stay_denied(self):
    commands = (
      'bash -lc \'cat .en"v"\'',
      'cat .en"v"', "cat '.en'v", r'cat .en\v',
      'cat key.p"em"', 'cat .env.pro"duction"',
      'bash -lc \'sh -c "cat .en\\\"v\\\""\'',
      'pwsh -c \'Get-Content .en"v"\'',
      'cmd /c "type .en^v"', 'Get-Content .en`v',
      'cat .en"$suffix"', 'cat key.p${extension}',
      'cat .en$(printf v)', 'cat key.p$(printf em)',
      'cat .en${suffix', 'cat .en$(printf v',
      'cat .en`printf v`', 'cat key.p`printf em`',
      'cat .en`printf v', 'cat key.p`printf em',
      'cat .env.prod${suffix}.local', 'cat .en$(echo $(printf v))',
      "cat .en$(printf ')')", 'cat key.p$(echo $(printf em))',
      'cat .en$(basename /tmp/v)',
      'cat .e$(printf n)v', 'cat k$(printf ey).pem', 'cat .e${middle}v',
      'cat .${suffix}', 'cat docs.${extension}', 'cat docs.$(printf txt)',
      'cat docs.`printf txt`', 'cat */docs.${extension}',
      'Get-Content ".env.$stage.local"',
    )
    for command in commands:
      with self.subTest(command=command):
        data = {'cmd': command}
        if '`printf' in command:
          data['shell'] = 'bash'
        self.assertEqual(self.shell_read(command, tool_input=data).get('decision'), 'deny')

  def test_benign_shell_fragments_and_dynamic_paths_remain_allowed(self):
    commands = (
      'cat doc"s".txt', 'cat .env.ex"ample"', 'gc $path',
      'cat "$directory/docs.txt"', 'cat docs.${extension}.txt',
      'cat docs.$(printf txt).txt',
      'cat docs.`printf txt`.txt',
      'cat report.${extension}.pdf', 'cat report.$extension.pdf',
      'cat .env.${stage}.example', 'cat key.p${extension}.txt',
      'cat report.$(printf draft).pdf', 'cat report.`printf draft`.pdf',
      'cat report.$(echo $(printf draft)).pdf', "cat report.$(printf ')').pdf",
      'cat docs.$(basename /tmp/txt).txt', 'cat .p${directory}/docs.${extension}.txt',
      'bash -lc \'cat doc"s".txt\'',
      'bash -lc \'sh -c "cat docs.txt"\'',
      'pwsh -c \'Get-Content "docs with spaces.txt"\'',
    )
    for command in commands:
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command).get('decision'), 'deny')

  def test_executed_shell_substitutions_keep_secret_guards(self):
    commands = (
      'Write-Output "$(Get-Content .env)"', 'echo "$(cat secret.pem)"',
      'echo "$(echo $(cat .en\"v\"))"',
      'echo "$(printf \')\'; cat .env)"',
      'bash -lc \'echo "$(cat .env)"\'',
      r'Write-Output "\$(Get-Content .env)"',
      'bash -lc \'echo "^$(cat .env)"\'',
      r'echo "\$(cat .env)"',
    )
    for command in commands:
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command).get('decision'), 'deny')

  def test_nonsecret_and_literal_shell_substitutions_remain_allowed(self):
    commands = (
      'echo "$(cat docs.txt)"', 'Write-Output "$(Get-Content docs.txt)"',
      'echo "$(echo $(cat docs.txt))"',
      "echo '$(cat .env)'", "echo '$(cat secret.pem)'",
    )
    for command in commands:
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command).get('decision'), 'deny')

  def test_powershell_backtick_escaped_substitutions_are_literal(self):
    for command in (
        'Write-Output "`$(Get-Content .env)"',
        'Write-Output "`$(Get-Content secret.pem)"',
        'Write-Output "```$(Get-Content .env)"',
        'pwsh -Command \'Write-Output "`$(Get-Content .env)"\''):
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')
    for command in (
        'Write-Output "$(Get-Content .env)"',
        'Write-Output "``$(Get-Content .env)"',
        'Write-Output "````$(Get-Content secret.pem)"',
        'Get-Content .en`v', 'Get-Content key.p`em'):
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'pwsh'}).get('decision'), 'deny')

  def test_backtick_shell_substitutions_keep_secret_guards(self):
    commands = (
      'cat `cat .env`', 'echo "`cat secret.pem`"',
      'bash -lc \'cat `cat .env`\'',
      r'echo `echo \`cat .env\``',
      r'echo `cat .en\v`', 'echo `cat .en"v"`',
      'echo "$(echo `cat .env`)"',
      'echo `echo $(cat .env)`',
      'bash -lc \'echo "^`cat .env`"\'',
    )
    for command in commands:
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'bash'}).get('decision'), 'deny')

  def test_bash_escaped_substitutions_are_literal(self):
    allowed = (
      r'echo "\$(cat .env)"', r'echo "\`cat .env\`"',
      r'echo "\\\$(cat secret.pem)"', r'echo "\\\`cat secret.pem\`"',
      r'echo \`cat .env\`', r"echo '\$(cat .env)'",
      r'''bash -lc 'echo "\$(cat .env)"' ''',
      r'''bash -lc 'echo "\`cat .env\`"' ''',
    )
    denied = (
      'echo "$(cat .env)"', 'echo "`cat secret.pem`"',
      r'echo "\\$(cat .env)"', r'echo "\\`cat .env`"',
      r'''bash -lc 'echo "\\$(cat .env)"' ''',
      r'cat .en\v', r'cat key.p\em',
    )
    for command in allowed:
      with self.subTest(command=command):
        self.assertNotEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'bash'}).get('decision'), 'deny')
    for command in denied:
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': 'bash'}).get('decision'), 'deny')

  def test_nonsecret_and_literal_backticks_remain_allowed(self):
    commands = (
      'echo `cat docs.txt`', 'bash -lc \'echo `cat docs.txt`\'',
      r'echo `echo \`cat docs.txt\``', "echo '`cat .env`'",
      'echo "`cat docs.txt`"', 'echo `echo $(cat docs.txt)`',
      'echo "$(echo `cat docs.txt`)"',
      'Get-Content doc`s.txt',
    )
    for command in commands:
      with self.subTest(command=command):
        shell = 'pwsh' if command.startswith('Get-Content') else 'bash'
        self.assertNotEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': shell}).get('decision'), 'deny')

  def test_desktop_commander_secret_guard_is_wired_on_both_platforms(self):
    root = Path(__file__).resolve().parents[2] / 'confs/codex'
    for platform in ('windows', 'linux'):
      config = json.loads((root / (platform + '.hooks.json')).read_text(encoding='utf-8'))
      guards = [entry for entry in config['hooks']['PreToolUse']
        if any('codex_hooks.py' in hook['command'] for hook in entry['hooks'])]
      self.assertEqual(len(guards), 1)
      for tool in ('read_file', 'read_multiple_files', 'write_file', 'move_file'):
        for server in ('desktop_commander', 'desktop-commander'):
          self.assertRegex('mcp__' + server + '__' + tool, guards[0]['matcher'])

  def test_desktop_commander_process_input_keeps_terminal_guards(self):
    for command in ('Get-Content .env', 'Remove-Item cache -Recurse'):
      for tool, data in (
        ('start_process', {'command': command, 'timeout_ms': 1000}),
        ('interact_with_process', {'pid': 1, 'input': command}),
      ):
        with self.subTest(command=command, tool=tool):
          self.assertEqual(self.policy(event(tool='mcp__desktop_commander__' + tool,
            tool_input=data)).get('decision'), 'deny')
    for tool, data in (
      ('start_process', {'command': 'git status', 'timeout_ms': 1000}),
      ('interact_with_process', {'pid': 1, 'input': 'git status'}),
    ):
      self.assertNotEqual(self.policy(event(tool='mcp__desktop_commander__' + tool,
        tool_input=data)).get('decision'), 'deny')

  def test_desktop_process_shell_identity_and_unknown_fallback(self):
    def start(command, pid, **fields):
      raw = event('PostToolUse', 'mcp__desktop_commander__start_process',
        tool_input={'command': command, 'shell': 'powershell.exe'},
        tool_response={'content': [{'type': 'text', 'text':
          f'Process started with PID {pid} (shell: powershell.exe)\nInitial output:\n'}]})
      raw.update(fields)
      return self.policy(raw)
    def interact(command, pid, **fields):
      raw = event(tool='mcp__desktop_commander__interact_with_process',
        tool_input={'pid': pid, 'input': command})
      raw.update(fields)
      return self.policy(raw)
    start('bash', 10)
    for command in (r"cat $'.en\x76'", r"cat $'key.pe\155'"):
      self.assertEqual(interact(command, 10).get('decision'), 'deny')
      self.assertEqual(interact(command, 999).get('decision'), 'deny')
    start('pwsh -NoProfile', 11)
    self.assertNotEqual(interact('Write-Output *', 11).get('decision'), 'deny')
    self.assertEqual(interact('Get-Content "*.pem"', 11).get('decision'), 'deny')
    self.policy(event('PostToolUse', 'mcp__desktop_commander__interact_with_process',
      tool_input={'pid': 11, 'input': 'bash'}, tool_response={'content': []}))
    self.assertEqual(interact(r"cat $'.en\x76'", 11).get('decision'), 'deny')
    start('pwsh -NoProfile', 11)
    self.assertEqual(interact('Write-Output *', 11, session_id='other').get('decision'), 'deny')
    start('bash', 11, tool_response={'isError': True})
    self.assertNotEqual(interact('Write-Output *', 11).get('decision'), 'deny')
    self.policy(event('PostToolUse', 'mcp__desktop_commander__kill_process',
      tool_input={'pid': 11}, tool_response={'content': []}))
    self.assertEqual(interact('Write-Output *', 11).get('decision'), 'deny')
    start('bash', 11)
    self.assertEqual(interact('Write-Output *', 11).get('decision'), 'deny')
    start('pwsh', 11, tool_response={'content': [{'type': 'text', 'text':
      'Initial output:\nProcess started with PID 11 (shell: powershell.exe)'}]})
    self.assertEqual(interact('Write-Output *', 11).get('decision'), 'deny')

  def test_desktop_process_lifecycle_post_hooks_are_wired(self):
    root = Path(__file__).resolve().parents[2] / 'confs/codex'
    for platform in ('windows', 'linux'):
      config = json.loads((root / (platform + '.hooks.json')).read_text(encoding='utf-8'))
      matcher = config['hooks']['PostToolUse'][0]['matcher']
      for server in ('desktop_commander', 'desktop-commander'):
        for tool in ('start_process', 'interact_with_process', 'kill_process'):
          self.assertRegex('mcp__' + server + '__' + tool, matcher)

  def test_continuation_keeps_baseline_and_next_user_turn_resets(self):
    original = codex_hooks.normalize(event('Stop'))
    codex_hooks.remember_block(original, {'decision': 'block', 'reason': 'Fix tests.'})
    continued = codex_hooks.normalize(dict(event('UserPromptSubmit', prompt='Fix tests.'), turn_id='turn-2'))
    self.assertEqual(continued['promptId'], 'turn-1')
    self.assertEqual(codex_hooks.normalize(dict(event('PostToolUse'), turn_id='turn-2'))['promptId'], 'turn-1')
    new = codex_hooks.normalize(dict(event('UserPromptSubmit', prompt='New task.'), turn_id='turn-3'))
    self.assertEqual(new['promptId'], 'turn-3')

  def test_repeated_identical_block_stops_with_incomplete_warning(self):
    raw = codex_hooks.normalize(event('Stop'))
    block = {'decision': 'block', 'reason': 'Tests failed.'}
    self.assertEqual(codex_hooks.remember_block(raw, block), block)
    self.assertEqual(codex_hooks.remember_block(raw, block), block)
    result = codex_hooks.remember_block(raw, block)
    self.assertFalse(result['continue'])
    self.assertIn('Validation incomplete', result['systemMessage'])

  def test_wrapped_rephrased_blocks_keep_baseline_and_stop_after_three(self):
    original = codex_hooks.normalize(event('Stop'))
    reasons = ('gone.txt:L1: Diff omitted. Provide contents.', 'gone.txt:L1: Deletion cannot be reviewed.', 'gone.txt:L1: Provide the deletion diff.')
    with patch.object(codex_hooks, 'continuation_key', return_value='same-diff'):
      for number, reason in enumerate(reasons, 1):
        result = codex_hooks.remember_block(original, {'decision': 'block', 'reason': reason, '_failure_stage': 'review'})
        if number < 3:
          self.assertEqual(result['decision'], 'block')
          prompt = '<hook_prompt hook_run_id="stop:4:hooks.json">' + reason + '</hook_prompt>'
          continued = codex_hooks.normalize(dict(event('UserPromptSubmit', prompt=prompt), turn_id=f'turn-{number + 1}'))
          self.assertEqual(continued['promptId'], 'turn-1')
          original = codex_hooks.normalize(dict(event('Stop'), turn_id=f'turn-{number + 1}'))
          self.assertEqual(original['promptId'], 'turn-1')
        else:
          self.assertFalse(result['continue'])
          self.assertIn('Validation incomplete', result['systemMessage'])
    new = codex_hooks.normalize(dict(event('UserPromptSubmit', prompt='Please fix the hook.'), turn_id='new-turn'))
    self.assertEqual(new['promptId'], 'new-turn')

  def test_retry_budget_resets_when_diff_changes(self):
    raw = codex_hooks.normalize(event('Stop'))
    block = {'decision': 'block', 'reason': 'Tests failed.'}
    with patch.object(codex_hooks, 'continuation_key', side_effect=['old', 'old', 'new', 'new', 'new']):
      for _ in range(4):
        self.assertEqual(codex_hooks.remember_block(raw, block), block)
      self.assertFalse(codex_hooks.remember_block(raw, block)['continue'])

  def test_retry_budget_resets_when_failure_changes(self):
    raw = codex_hooks.normalize(event('Stop'))
    with patch.object(codex_hooks, 'continuation_key', return_value='same-diff'):
      for stage, reason in (('diagnostics', 'Fix diagnostics.'), ('test', 'Fix tests.'),
        ('review', 'a.py:L1: Fix logic.'), ('review', 'a.py:L2: Fix another issue.')):
        block = {'decision': 'block', 'reason': reason, '_failure_stage': stage}
        for _ in range(2):
          result = codex_hooks.remember_block(raw, block)
          self.assertEqual(result, {'decision': 'block', 'reason': reason})
      final_block = {'decision': 'block', 'reason': 'a.py:L2: Fix another issue.',
        '_failure_stage': 'review'}
      self.assertFalse(codex_hooks.remember_block(raw, final_block)['continue'])

  def test_retry_budget_resets_for_different_test_failures(self):
    raw = codex_hooks.normalize(event('Stop'))
    with patch.object(codex_hooks, 'continuation_key', return_value='same-diff'):
      for reason in ('Test A failed.', 'Test B failed.'):
        for _ in range(2):
          result = codex_hooks.remember_block(raw, {'decision': 'block', 'reason': reason, '_failure_stage': 'test'})
          self.assertEqual(result['decision'], 'block')

  def test_continuation_key_changes_with_deleted_contents(self):
    raw = codex_hooks.normalize(event('Stop', cwd=self.temp.name))
    changes = [turn_end.Change('gone.txt', 'old\n', '', after_deleted=True)]
    with patch.object(turn_end, 'load_changes', return_value=changes):
      first = codex_hooks.continuation_key(raw)
      changes[0] = turn_end.Change('gone.txt', 'different\n', '', after_deleted=True)
      self.assertNotEqual(first, codex_hooks.continuation_key(raw))

  def test_recursive_review_child_skips_all_hooks(self):
    with patch.dict(os.environ, {'TURN_END_CHILD': '1'}), patch.object(codex_hooks, 'normalize') as normalize:
      self.assertEqual(codex_hooks.dispatch(event('Stop')), {})
      normalize.assert_not_called()

  def test_format_block_prevents_tests_and_review(self):
    raw = codex_hooks.normalize(event('Stop'))
    with patch.object(tool_gate, 'handle', return_value={}), patch.object(codex_hooks, 'run_stage', return_value={'decision': 'block', 'reason': 'formatted'}) as stage, patch.object(codex_hooks, 'review') as review:
      self.assertEqual(codex_hooks.stop(raw)['reason'], 'formatted')
      self.assertEqual(stage.call_args.args[0], 'format')
      stage.assert_called_once()
      review.assert_not_called()

  def test_shutdown_skips_entire_stop_runner(self):
    for reason in ('shutdown', 'channel_closed', 'cancelled'):
      with patch.object(codex_hooks, 'run_stage') as stage, patch.object(codex_hooks, 'review') as review:
        self.assertEqual(codex_hooks.stop(codex_hooks.normalize(event('Stop', reason=reason))), {})
        stage.assert_not_called()
        review.assert_not_called()

  def test_protected_paths_never_read_by_codex_snapshot(self):
    with patch.object(turn_end, 'git', return_value=b'?? .env\0?? keys/server.pem\0?? notes.txt\0'), patch.object(turn_end, 'read_bytes', return_value=b'notes') as read:
      files = turn_end.capture(self.temp.name, protect_secrets=True)
      self.assertEqual(list(files), ['notes.txt'])
      read.assert_called_once_with(os.path.join(self.temp.name, 'notes.txt'))

  def test_protected_only_diff_skips_model_review(self):
    with patch.object(codex_hooks, 'run_stage', return_value={}), patch.object(turn_end, 'ensure_git'), patch.object(turn_end, 'load_changes', return_value=[turn_end.Change('.env', 'secret', 'new secret')]), patch.object(codex_hooks, 'review') as review:
      self.assertEqual(codex_hooks.stop(codex_hooks.normalize(event('Stop'))), {})
      review.assert_not_called()

  def test_same_diff_caches_passes_new_edit_invalidates(self):
    raw = codex_hooks.normalize(event('Stop'))
    changes = [turn_end.Change('notes.txt', 'old', 'new')]
    with patch.object(tool_gate, 'handle', return_value={}), patch.object(turn_end, 'ensure_git'), patch.object(turn_end, 'load_changes', return_value=changes), patch.object(codex_hooks, 'run_stage', return_value={}) as stage, patch.object(codex_hooks, 'review', return_value={}) as review:
      self.assertEqual(codex_hooks.stop(raw), {})
      self.assertEqual(codex_hooks.stop(raw), {})
      review.assert_called_once()
      self.assertEqual([c.args[0] for c in stage.call_args_list], ['format', 'test', 'format'])
      changes[0].after = 'newer'
      self.assertEqual(codex_hooks.stop(raw), {})
      self.assertEqual(review.call_count, 2)

  def test_subagent_skips_model_review(self):
    raw = codex_hooks.normalize(event('SubagentStop', agent_id='child'))
    with patch.object(tool_gate, 'handle', return_value={}), patch.object(turn_end, 'ensure_git'), patch.object(turn_end, 'load_changes', return_value=[turn_end.Change('main.go')]), patch.object(codex_hooks, 'run_stage', return_value={}), patch.object(codex_hooks, 'review') as review:
      self.assertEqual(codex_hooks.stop(raw), {})
      review.assert_not_called()

  def test_no_snapshot_skips_review(self):
    with patch.object(tool_gate, 'handle', return_value={}), patch.object(codex_hooks, 'run_stage', return_value={}), patch.object(turn_end, 'ensure_git'), patch.object(turn_end, 'load_changes', side_effect=turn_end.NoSnapshot), patch.object(codex_hooks, 'review') as review:
      self.assertEqual(codex_hooks.stop(codex_hooks.normalize(event('Stop'))), {})
      review.assert_not_called()

  def test_review_sends_complete_large_diff_through_stdin(self):
    changes = [
      turn_end.Change(
        path=f'large-{number}.txt', before='old\n',
        after=''.join(f'large-{number}-line-{index:04d}\n' for index in range(1200)),
      )
      for number in range(2)
    ]
    expected = ''.join(turn_end.change_diff(change) for change in changes)
    self.assertGreater(len(expected), 32767)

    def run(args, **kwargs):
      self.assertEqual(args[-1], '-')
      self.assertTrue(kwargs['input'].endswith(expected))
      self.assertNotIn(kwargs['input'], args)
      self.assertNotIn('Truncated:', kwargs['input'])
      self.assertNotIn('Omitted:', kwargs['input'])
      output = Path(args[args.index('--output-last-message') + 1])
      output.write_text('No issues.', encoding='utf-8')
      return SimpleNamespace(returncode=0)

    with patch.object(codex_hooks.shutil, 'which', return_value='codex'), patch.object(codex_hooks.subprocess, 'run', side_effect=run):
      self.assertEqual(codex_hooks.review(changes), {})

  def test_review_failure_preserves_bounded_stderr(self):
    for stderr in ('invalid configuration', 'network connection failed',
        'startup failed', 'x' * 5000 + '\r\nnetwork connection failed', ''):
      with self.subTest(stderr=stderr[-40:]), patch.object(codex_hooks.shutil, 'which', return_value='codex'), patch.object(codex_hooks.subprocess, 'run', return_value=SimpleNamespace(returncode=7, stderr=stderr)):
        result = codex_hooks.review([turn_end.Change('notes.txt')])
        expected = 'Codex review exited 7.'
        if stderr:
          expected += '\n' + turn_end.trim_out(stderr)
        self.assertEqual(result, {'decision': 'block', 'reason': expected})

  def test_review_isolated_and_empty_verdict_blocks(self):
    def run(args, **kwargs):
      self.assertIn('--ignore-user-config', args)
      self.assertIn('--ephemeral', args)
      self.assertIn('features.hooks=false', args)
      self.assertEqual(kwargs['env']['TURN_END_CHILD'], '1')
      self.assertEqual(args[args.index('--sandbox') + 1], 'read-only')
      output = Path(args[args.index('--output-last-message') + 1])
      output.write_text(self.verdict, encoding='utf-8')
      return SimpleNamespace(returncode=0)
    with patch.object(codex_hooks.shutil, 'which', return_value='codex'), patch.object(codex_hooks.subprocess, 'run', side_effect=run):
      self.verdict = 'No issues.'
      self.assertEqual(codex_hooks.review([turn_end.Change('notes.txt')]), {})
      self.verdict = ''
      self.assertEqual(codex_hooks.review([turn_end.Change('notes.txt')])['decision'], 'block')


if __name__ == '__main__':
  unittest.main()
