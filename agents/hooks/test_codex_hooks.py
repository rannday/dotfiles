import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import codex_hooks


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

  def test_nonobject_hook_input_reports_concise_failure(self):
    for value in ([], ['Stop'], None, True, 7, 'Stop'):
      with self.subTest(value=value), patch.object(sys, 'stdin', io.StringIO(json.dumps(value))), \
        patch.object(sys, 'stdout', io.StringIO()) as stdout, \
        patch.object(sys, 'stderr', io.StringIO()) as stderr:
        self.assertEqual(codex_hooks.main(), 2)
        self.assertEqual(stdout.getvalue(), '')
        self.assertEqual(stderr.getvalue(), 'Codex hook failed: TypeError\n')

  def test_unknown_event_is_quiet_without_state_access(self):
    with patch.object(sys, 'stdin', io.StringIO(json.dumps(event('FutureEvent')))), \
      patch.object(sys, 'stdout', io.StringIO()) as stdout, \
      patch.object(sys, 'stderr', io.StringIO()) as stderr, \
      patch.object(codex_hooks, 'normalize', side_effect=AssertionError('unexpected normalization')):
      self.assertEqual(codex_hooks.main(), 0)
      self.assertEqual(stdout.getvalue(), '')
      self.assertEqual(stderr.getvalue(), '')
    self.assertEqual(list(Path(self.temp.name).iterdir()), [])

  def test_retired_lifecycle_events_are_quiet_and_stateless(self):
    for name in ('UserPromptSubmit', 'Stop', 'SubagentStop'):
      with self.subTest(name=name), patch.object(codex_hooks, 'normalize', side_effect=AssertionError('unexpected normalization')):
        self.assertEqual(codex_hooks.dispatch(event(name, agent_id='child')), {})
    self.assertEqual(list(Path(self.temp.name).iterdir()), [])

  def test_ordinary_tools_are_stateless_without_routing_prerequisites(self):
    tools = (
      ('exec_command', {'cmd': 'git -C repo status'}),
      ('exec_command', {'cmd': 'rg marker src'}),
      ('grep', {'pattern': 'marker'}),
      ('apply_patch', {'command': '*** Update File: docs.md\n*** Update File: pkg/main.go'}),
      ('apply_patch', {'command': '*** Add File: pkg/new.go\n+package pkg'}),
      ('mcp__serena__replace_symbol_body', {'relative_path': 'main.go'}),
      ('mcp__serena__rename_symbol', {'relative_path': 'main.go'}),
      ('mcp__gopls__go_diagnostics', {}),
      ('mcp__fff__ffgrep', {}),
    )
    for tool, data in tools:
      for name in ('PreToolUse', 'PostToolUse'):
        with self.subTest(tool=tool, name=name):
          self.assertEqual(codex_hooks.dispatch(event(name, tool, tool_input=data)), {})
    self.assertEqual(list(Path(self.temp.name).iterdir()), [])

  def test_review_child_environment_does_not_bypass_safety(self):
    with patch.dict(os.environ, {'TURN_END_CHILD': '1'}):
      result = codex_hooks.dispatch(event(tool='exec_command', tool_input={'cmd': 'cat .env'}))
    self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')

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
    for name in ('tool_gate.py',):
      shutil.copyfile(source / name, shared_dir / name)
      (stale_dir / name).write_text('raise RuntimeError("stale local hook")', encoding='utf-8')
    for name in ('turn_end.py', 'grok_review.py'):
      (stale_dir / name).write_text('raise RuntimeError("retired review dependency")', encoding='utf-8')
    result = subprocess.run([
      sys.executable, '-B', '-c',
      ('import pathlib,runpy,sys; '
      'sys.path.insert(0,sys.argv[3]); '
      'loaded=runpy.run_path(str(pathlib.Path(sys.argv[1])/"codex_hooks.py")); '
      'assert all(pathlib.Path(loaded[name].__file__).parent == pathlib.Path(sys.argv[2]) '
      'for name in ("tool_gate",)); '
      'assert "turn_end" not in sys.modules and "grok_review" not in sys.modules'),
      str(shared_dir), str(shared_dir), str(stale_dir),
    ], capture_output=True, text=True, check=False)
    self.assertEqual(result.returncode, 0, result.stderr)

  def test_session_id_and_mcp_names(self):
    parsed = codex_hooks.normalize(event(tool='mcp__fff__grep'))
    self.assertEqual(parsed['sessionId'], 'codex-parent')
    self.assertEqual(parsed['toolName'], 'fff__grep')

  def test_bash_git_has_no_routing_block_in_codex_shape(self):
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


  def test_patch_move_and_delete_paths(self):
    self.assertEqual(codex_hooks.patch_paths('*** Delete File: old.go\n*** Move to: new.go'), ['old.go', 'new.go'])

  def test_github_checkout_read_has_no_routing_block(self):
    result = self.policy(event(tool='mcp__github__get_file_contents', tool_input={'owner': 'user', 'repo': 'repo'}))
    self.assertNotEqual(result.get('decision'), 'deny')

  def test_search_routing_has_no_blocks_or_nudges(self):
    results = [self.policy(event('PostToolUse', 'mcp__fff__ffgrep')) for _ in range(4)]
    self.assertEqual(results, [{}, {}, {}, {}])
    for tool in ('grep', 'Grep'):
      self.assertNotEqual(self.policy(event(tool=tool)).get('decision'), 'deny')
    self.assertFalse(list(Path(self.temp.name).rglob('fff-grep.count')))

  def test_native_shell_routing_is_allowed_on_both_platforms(self):
    for shell in ('powershell', 'pwsh', 'bash', 'sh'):
      for tool, key in (('exec_command', 'cmd'), ('Bash', 'command')):
        with self.subTest(shell=shell, tool=tool):
          self.assertNotEqual(self.policy(event(tool=tool,
            tool_input={key: 'git diff', 'shell': shell})).get('decision'), 'deny')
          self.assertEqual(self.policy(event(tool=tool,
            tool_input={key: 'cat .env', 'shell': shell}))['decision'], 'deny')

  def test_branch_creation_uses_host_approvals_not_permanent_deny(self):
    self.assertEqual(self.policy(event(tool='mcp__git__git_create_branch', tool_input={'repo_path': 'repo', 'branch_name': 'new'})), {})

  def test_secret_paths_read_shell_and_patch(self):
    for tool, data in (
      ('read_file', {'path': 'repo/.env'}),
      ('Bash', {'command': 'Get-Content "C:\\repo\\secret.pem"'}),
      ('apply_patch', {'command': '*** Add File: .env.production'}),
      ('mcp__serena__replace_content', {'relative_path': '.env.dev.local'}),
      ('mcp__filesystem__read_text_file', {'path': 'C:/repo/.env.local'}),
      ('mcp__filesystem__get_file_info', {'path': 'keys/server.pem'}),
      ('mcp__filesystem__read_multiple_files', {'paths': ['notes.txt', 'keys/server.pem']}),
      ('mcp__filesystem__write_file', {'path': '.env.seed', 'content': 'secret'}),
      ('mcp__filesystem__move_file', {'source': 'secret.pem', 'destination': 'notes.txt'}),
      ('mcp__filesystem__move_file', {'source': 'notes.txt', 'destination': '.env.test'}),
    ):
      with self.subTest(tool=tool):
        self.assertEqual(self.policy(event(tool=tool, tool_input=data))['decision'], 'deny')
    self.assertFalse(codex_hooks.secret_paths(codex_hooks.normalize(event(tool='read_file', tool_input={'path': '.env.example'}))))
    for tool, data in (
      ('read_file', {'path': 'C:/repo/docs.txt', 'offset': 0, 'length': 10}),
      ('read_multiple_files', {'paths': ['docs.txt', '.env.example']}),
    ):
      self.assertNotEqual(self.policy(event(tool='mcp__filesystem__' + tool,
        tool_input=data)).get('decision'), 'deny')

  @unittest.expectedFailure
  def test_python_fixture_heredoc_allowance_is_unresolved(self):
    # Pending acceptance, not a passing safety proof: the parser cannot analyze Python.
    # Inert, minimized capture: computed ordinary paths, no protected names.
    command = ("python3 - <<'PY'\n"
      "from pathlib import Path\n"
      "for name in ('postgresql', 'mysql'):\n"
      "    path = Path('tests') / (name + '.py')\n"
      "    path.write_text(path.read_text().replace('old', 'new'))\n"
      "PY\n")
    self.assertEqual(self.policy(event(tool='exec_command',
      tool_input={'cmd': command, 'shell': 'bash'})), {})

  def test_unclassified_heredoc_reports_parser_limit_not_secret_detection(self):
    for shell, command, fragment in (
      ('bash', "python3 - <<'PY'\nprint('ordinary text')\nPY\n", 'here-document'),
      ('pwsh', "@'\nordinary text\n'@ | Invoke-Expression", 'here-string'),
      ('bash', 'bash -c "python3 - <<EOF\nprint(1)\nEOF\n"', 'here-document'),
      ('bash', 'echo $(sh <<EOF\nprintf ordinary\nEOF\n)', 'here-document'),
    ):
      with self.subTest(shell=shell, command=command):
        result = codex_hooks.dispatch(event(tool='exec_command',
          tool_input={'cmd': command, 'shell': shell}))['hookSpecificOutput']
        self.assertEqual(result['permissionDecision'], 'deny')
        self.assertIn('Cannot safely classify', result['permissionDecisionReason'])
        self.assertIn(fragment, result['permissionDecisionReason'])
        self.assertNotIn('Protected .env or PEM path.', result['permissionDecisionReason'])

  def test_fixture_and_documentation_data_do_not_select_protected_paths(self):
    body = '# Examples only: .env and keys/example.pem\nvalue = ".env"\n'
    for target in ('tests/postgresql.py', 'tests/mysql.py', 'docs/fixtures.md'):
      with self.subTest(target=target):
        for tool, data in (
          ('mcp__filesystem__write_file', {'path': target, 'content': body}),
          ('apply_patch', {'command': '*** Begin Patch\n*** Update File: ' + target
            + '\n@@\n+' + body.replace('\n', '\n+') + '\n*** End Patch'}),
          ('exec_command', {'shell': 'bash', 'cmd': "cat > " + target + " <<'PY'\n" + body + 'PY\n'}),
        ):
          self.assertEqual(self.policy(event(tool=tool, tool_input=data)), {})
    # Consecutive literal writes retain both ordinary targets.
    command = ''.join("cat > " + target + " <<'PY'\n" + body + 'PY\n'
      for target in ('tests/postgresql.py', 'tests/mysql.py'))
    self.assertEqual(self.policy(event(tool='exec_command',
      tool_input={'shell': 'bash', 'cmd': command})), {})

  def test_protected_targets_retain_denial_and_diagnostic(self):
    targets = ('.env', '.env.seed', '.env.local', '.env.development',
      '.env.production', '.env.test', '.env.dev.local', 'keys/example.pem')
    for target in targets:
      for command in (f'cat "{target}"', f'cat < "{target}"',
          f'printf text > "{target}"', f'printf text >> "{target}"',
          f'bash -c \'cat "{target}"\'', f'printf ordinary\ncat "{target}"'):
        with self.subTest(target=target, command=command):
          result = self.policy(event(tool='exec_command',
            tool_input={'shell': 'bash', 'cmd': command}))
          self.assertEqual(result['decision'], 'deny')
          self.assertIn('Protected .env or PEM path.', result['reason'])
    for command in ("cat '.en'v", r'cat .en\v', "cat 'keys/example.'pem"):
      with self.subTest(command=command):
        self.assertEqual(self.policy(event(tool='exec_command',
          tool_input={'shell': 'bash', 'cmd': command}))['decision'], 'deny')

  def test_documentation_literal_writes(self):
    body = 'Sanitize .env\n```sh\ncat keys/example.pem\n```'
    commands = (
      ('bash', "cat > docs/isc-report-evidence.md <<'REPORT'\n" + body + '\nREPORT\n'),
      ('sh', "cat <<'REPORT' > docs/isc-report-submission.md\n" + body + '\nREPORT\n'),
      ('bash', "cat <<-'REPORT' > report.txt\n\t" + body.replace('\n', '\n\t') + '\n\tREPORT\n'),
      ('bash', ''.join("cat > docs/" + name + " <<'REPORT'\n" + body + '\nREPORT\n'
        for name in ('isc-report-evidence.md', 'isc-report-submission.md'))),
      ('bash', "printf '%s\\n' '" + body + "' > docs/isc-report-evidence.md"),
      ('powershell', "Set-Content -LiteralPath docs/isc-report-submission.md -Value '" + body + "'"),
      ('pwsh', "Set-Content -Path report.txt -Value @'\n" + body + "\n'@\n"),
      ('pwsh', "@'\n" + body + "\n'@ | Set-Content -LiteralPath report.txt"),
      ('bash', "printf '%s\\n' '.env' > report.txt"),
      ('bash', "printf '%s\\n' 'keys/example.pem' > report.txt"),
      ('pwsh', "Set-Content -LiteralPath report.txt -Value '.env'"),
      ('pwsh', "Set-Content -LiteralPath report.txt -Value 'keys/example.pem'"),
    )
    for shell, command in commands:
      with self.subTest(shell=shell, command=command):
        self.assertEqual(self.policy(event(tool='exec_command',
          tool_input={'cmd': command, 'shell': shell})), {})

  def test_documentation_writes_through_shell_and_wsl_wrappers(self):
    command = "cat > report.md <<'EOF'\n.env\n```sh\ncat example.pem\n```\nEOF\n"
    for tool, shell, wrapped in (
      ('Bash', 'bash', command),
      ('exec_command', 'powershell', "wsl.exe --distribution Debian --cd /tmp --exec /bin/bash -c '" + command.replace("'EOF'", '"EOF"') + "'"),
      ('exec_command', 'powershell', "wsl.exe -d Debian '" + command.replace("'EOF'", '"EOF"') + "'"),
      ('exec_command', 'bash', "bash -c '" + command.replace("'", "'\"'\"'") + "'"),
    ):
      with self.subTest(tool=tool, wrapped=wrapped):
        self.assertEqual(self.policy(event(tool=tool,
          tool_input={'cmd': wrapped, 'shell': shell})), {})

  def test_literal_documentation_write_executes_only_in_disposable_directory(self):
    body = 'Sanitize .env\n```sh\ncat keys/example.pem\n```'
    if os.name == 'nt':
      shell = 'powershell'
      command = "Set-Content -LiteralPath report.md -Value @'\n" + body + "\n'@\n"
      commands = [(shell, command, ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command])]
    else:
      shell = 'sh'
      command = "cat > report.md <<'EOF'\n" + body + '\nEOF\n'
      commands = [(shell, command, ['/bin/' + shell, '-c', command]) for shell in ('sh', 'bash')]
    for shell, command, argv in commands:
      with self.subTest(shell=shell):
        raw = event(tool='exec_command', tool_input={'cmd': command, 'shell': shell})
        with patch.object(sys, 'stdin', io.StringIO(json.dumps(raw))), \
          patch.object(sys, 'stdout', io.StringIO()) as stdout:
          self.assertEqual(codex_hooks.main(), 0)
          self.assertEqual(stdout.getvalue(), '')
        result = subprocess.run(argv, cwd=self.temp.name, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((Path(self.temp.name) / 'report.md').read_text(encoding='utf-8').strip(), body)
        self.assertEqual([path.name for path in Path(self.temp.name).iterdir()], ['report.md'])

  def test_documentation_patch_and_structured_write_contents_are_inert(self):
    body = 'Mention .env and keys/example.pem\n```sh\ncat .env\n```'
    for name in ('isc-report-evidence.md', 'isc-report-submission.md'):
      for operation in ('Add', 'Update'):
        command = ('*** Begin Patch\n*** ' + operation + ' File: docs/' + name
          + '\n+' + body.replace('\n', '\n+') + '\n*** End Patch')
        self.assertEqual(self.policy(event(tool='apply_patch', tool_input={'command': command})), {})
      self.assertEqual(self.policy(event(tool='mcp__filesystem__write_file',
        tool_input={'path': 'docs/' + name, 'content': body})), {})

  def test_documentation_exemptions_preserve_protected_targets_and_execution(self):
    commands = (
      ('bash', "cat > .env <<'EOF'\ntext\nEOF\n"),
      ('bash', "cat <<'EOF' > key.pem\ntext\nEOF\n"),
      ('bash', "cat <<'EOF' > report.md\ntext\nEOF\ncat .env"),
      ('bash', "cat > report.md <<'EOF'\n.env\nEOF\ncat > key.pem <<'EOF'\ntext\nEOF\n"),
      ('bash', "cat <<'EOF' > report.md < key.pem\ntext\nEOF\n"),
      ('bash', "cat <<'EOF' | sh\ncat .env\nEOF\n"),
      ('bash', "sh <<'EOF'\ncat .env\nEOF\n"),
      ('bash', "cat <<EOF > report.md\n$(cat .env)\nEOF\n"),
      ('bash', "cat <<EOF > report.md\n'$(cat .env)'\nEOF\n"),
      ('bash', "printf '%s\\n' \"$(cat key.pem)\" > report.md"),
      ('bash', "printf '%s\\n' '.env' > .env"),
      ('bash', "printf '%s\\n' 'text' > *.pem"),
      ('pwsh', "Set-Content -LiteralPath key.pem -Value '.env'"),
      ('pwsh', "Set-Content -Path '*.pem' -Value 'text'"),
      ('pwsh', "Set-Content -LiteralPath report.md -Value \"$(Get-Content .env)\""),
      ('pwsh', "@'\nGet-Content .env\n'@ | Invoke-Expression"),
      ('pwsh', "Set-Content -Path report.md -Value @'\nGet-Content .env\n'@ -PassThru | Invoke-Expression"),
      ('bash', "cat <<'EOF' > report.md\n.env\nNOT_EOF"),
    )
    for shell, command in commands:
      with self.subTest(shell=shell, command=command):
        self.assertEqual(self.policy(event(tool='exec_command',
          tool_input={'cmd': command, 'shell': shell}))['decision'], 'deny')

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

  def test_powershell_parser_casts_allow_native_commands(self):
    command = ('$parseTokens = $null\n$parseErrors = $null\n'
      '[void][System.Management.Automation.Language.Parser]::ParseFile('
      "'modules/ssh.ps1', [ref]$parseTokens, [ref]$parseErrors)\n"
      'if ($parseErrors.Count -gt 0) { $parseErrors; exit 1 }\n'
      "Write-Output 'PowerShell syntax: passed'")
    for shell in ('powershell', 'pwsh'):
      for tool, key in (('exec_command', 'cmd'), ('Bash', 'command')):
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
      'bash -lc \'echo "^$(cat .env)"\'',
    )
    for command in commands:
      with self.subTest(command=command):
        self.assertEqual(self.shell_read(command).get('decision'), 'deny')

  def test_backslash_before_substitution_uses_shell_dialect(self):
    for command in (r'Write-Output "\$(Get-Content .env)"', r'echo "\$(cat .env)"'):
      for shell in ('powershell', 'pwsh', 'sh', 'bash'):
        with self.subTest(command=command, shell=shell):
          result = self.shell_read(command, tool_input={'cmd': command, 'shell': shell})
          if shell in ('powershell', 'pwsh'):
            self.assertEqual(result.get('decision'), 'deny')
          else:
            self.assertNotEqual(result.get('decision'), 'deny')

  def test_dynamic_assignments_are_not_path_prefixes(self):
    commands = (
      ('powershell', ('function Install-UserFile { param($Source,$Destination) '
        '$script:auditCopies += [pscustomobject]@{Source=$Source;Destination=$Destination} }')),
      ('pwsh', '@{Source=$Source;Destination=$Destination}'),
      ('pwsh', '[pscustomobject]@{Source=$Source\nDestination=$Destination}'),
      ('powershell', "@{'Source'=$Source;Destination=$Destination}"),
      ('powershell', '$copy=$value'),
      ('sh', 'copy_count=$((copy_count + 1))'),
      ('bash', 'first=$value second=$other printf done'),
      ('sh', 'install_user_file() { require_file "$1"; copy_count=$((copy_count + 1)); }'),
    )
    for shell, command in commands:
      with self.subTest(shell=shell, command=command):
        self.assertNotEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': shell}).get('decision'), 'deny')

  def test_assignment_path_lists_are_separate_path_candidates(self):
    allowed = (
      ('bash', 'PATH="$PWD/build-quality-venv/bin:$PATH" python3 -B scripts/quality.py'),
      ('sh', 'PATH="$PWD/build-quality-venv/bin:$PATH" python3 -B scripts/quality.py'),
      ('bash', 'python3 -B scripts/quality.py'),
      ('bash', 'cmake --build build'),
      ('bash', 'PATH="$PWD/bin:$PATH" MODE=check python3 "scripts/quality check.py"'),
      ('bash', 'PATH="/tmp/tools with spaces/bin:$PATH" cmake --build "build [draft].txt"'),
      ('bash', 'PATH="/tmp/.env.example/bin:$PATH" python3 scripts/quality.py'),
      ('zsh', 'MODE="two words" PATH="${PWD}/bin:${PATH}" cmake --build build'),
      ('bash', 'PATH="$(printf bin):$PATH" python3 scripts/quality.py'),
      ('bash', 'PATH="bin:$PATH" python3 "scripts/a;b.txt" "build/key.pem.txt"'),
      ('pwsh', '$env:PATH="$PWD/build-quality-venv/bin;$env:PATH"; python -B scripts/quality.py'),
      ('powershell', '$env:PATH="C:\\tools;$env:PATH"; cmake --build build'),
    )
    for shell, command in allowed:
      with self.subTest(shell=shell, command=command):
        self.assertEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': shell}), {})

  def test_assignment_path_lists_preserve_protected_entries_and_executed_bodies(self):
    denied = (
      ('bash', 'PATH="/tmp/key.pem:$PATH" python3 scripts/quality.py'),
      ('bash', 'PATH="$PATH:./.env" python3 scripts/quality.py'),
      ('bash', 'PATH="/tmp/.en${suffix}:$PATH" cmake --build build'),
      ('bash', 'PATH="$(cat /tmp/key.pem):$PATH" python3 scripts/quality.py'),
      ('bash', 'PATH="$(printf bin):$PATH" cat <./.env'),
      ('bash', 'PATH="bin:$PATH" cmake --build build && cat /tmp/key.pem'),
      ('bash', 'PATH="bin:$PATH" python3 scripts/quality.py >./key.pem'),
      ('bash', 'PATH="bin:$PATH" cat "prefix:$suffix"'),
      ('pwsh', '$env:PATH="C:\\keys\\key.pem;$env:PATH"; python scripts/quality.py'),
      ('pwsh', '$env:PATH="$env:PATH;.env"; cmake --build build'),
      ('bash', 'PATH=*:./.env cmake --build build'),
      ('pwsh', '$env:PATH="*;$env:PATH;.env"; cmake --build build'),
      ('pwsh', '$env:PATH="$(Get-Content .env);$env:PATH"; python scripts/quality.py'),
      ('bash', 'PATH="bin:$PATH" cat /tmp/key.pem'),
      ('bash', 'PATH="bin:$PATH" cat ../.env'),
      ('bash', 'PATH="bin:$PATH"; (cat .env)'),
      ('bash', 'PATH="bin:$PATH" cat key.{txt,pem}'),
      ('bash', 'PATH="bin:$PATH" cat .en${suffix}'),
      ('bash', 'PATH="bin:$PATH" cat *.pem'),
      ('bash', 'PATH="bin:$PATH" cat "PATH=$suffix"'),
      ('bash', 'SOURCE="bin:$SOURCE" python3 scripts/quality.py'),
      ('bash', 'PATH={bin:tools,key.pem}:$PATH python3 scripts/quality.py'),
      ('bash', 'PATH=[.:x]env:$PATH python3 scripts/quality.py'),
      ('pwsh', '$source="bin;$source"; python scripts/quality.py'),
    )
    for shell, command in denied:
      with self.subTest(shell=shell, command=command):
        self.assertEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': shell}).get('decision'), 'deny')

  def test_path_shaped_filename_operands_keep_whole_path_checks(self):
    for shell in ('bash', 'sh', 'zsh'):
      for operand in ('PATH=prefix:$suffix', 'PATH=.en${suffix}', 'PATH=key.p${suffix}'):
        for command in (f'cat <{operand}', f'cat >{operand}', f'cat {operand}',
            f'cat <{operand} PATH="bin:$PATH"', f'echo ok; cat >{operand}'):
          with self.subTest(shell=shell, command=command):
            self.assertEqual(self.shell_read(command,
              tool_input={'cmd': command, 'shell': shell}).get('decision'), 'deny')

  def test_consumed_powershell_path_assignments_keep_whole_path_checks(self):
    for shell in ('pwsh', 'powershell'):
      for value in ('prefix;$suffix', '.en${suffix}', 'key.p${suffix}'):
        assignment = f'$env:PATH="{value}"'
        for command in (f'Get-Content ({assignment})', f'Get-Content (({assignment}))',
            f'Get-Content $({assignment})', f'Get-Content $({assignment}; $env:PATH)',
            f'Unknown-Command ({assignment})', f'Get-Content >{assignment}'):
          with self.subTest(shell=shell, command=command):
            self.assertEqual(self.shell_read(command,
              tool_input={'cmd': command, 'shell': shell}).get('decision'), 'deny')

  def test_standalone_path_assignments_keep_empty_and_quoted_entries(self):
    for shell in ('bash', 'sh', 'zsh'):
      for value in ('', ':', ':$PATH:', '/tmp/bin:/opt/bin:$PATH',
          '/tmp/tools with spaces/bin:$PATH', '/tmp/odd[dir]/bin:$PATH'):
        for command in (f'PATH="{value}" python3 -B scripts/quality.py',
            f'MODE="two words" PATH="{value}"; cmake --build build',
            f'echo ready; PATH="{value}" cmake --build build'):
          with self.subTest(shell=shell, command=command):
            self.assertEqual(self.shell_read(command,
              tool_input={'cmd': command, 'shell': shell}), {})
    for shell in ('pwsh', 'powershell'):
      for value in ('', ';', ';$env:PATH;', 'C:\\tools;D:\\bin;$env:PATH',
          'C:\\tools with spaces\\bin;;$env:PATH'):
        command = f'$env:PATH="{value}"; cmake --build build'
        with self.subTest(shell=shell, command=command):
          self.assertEqual(self.shell_read(command,
            tool_input={'cmd': command, 'shell': shell}), {})

  def test_path_assignment_protected_names_remain_detected(self):
    for name in ('.env', '.env.seed', '.env.local', '.env.development',
        '.env.production', '.env.test', '.env.stage.local', 'key.pem', 'KEY.PEM'):
      for shell, command in (
          ('bash', f'PATH="/tmp/{name}:$PATH" python3 scripts/quality.py'),
          ('sh', f'PATH="$PATH:./{name}" cmake --build build'),
          ('pwsh', f'$env:PATH="C:\\fixture\\{name};$env:PATH"; cmake --build build'),
          ('bash', f'cat <PATH=prefix:./{name}')):
        with self.subTest(shell=shell, command=command):
          self.assertEqual(self.shell_read(command,
            tool_input={'cmd': command, 'shell': shell}).get('decision'), 'deny')

  def test_uncertain_path_assignment_roles_keep_conservative_checks(self):
    denied = (
      ('bash', '"PATH"="prefix:$suffix"'),
      ('bash', '""PATH="prefix:$suffix"'),
      ('bash', 'P"AT"H="prefix:$suffix"'),
      ('bash', '"MODE"=check PATH="prefix:$suffix"'),
      ('sh', 'M\u00d6DE=check PATH="prefix:$suffix"'),
      ('bash', 'cat "PATH=prefix:$suffix"'),
      ('bash', 'cat >"PATH=prefix:$suffix"'),
      ('bash', 'cat >out PATH="prefix:$suffix"'),
      ('bash', 'echo ok && PATH="prefix:$suffix" cmake --build build'),
      ('bash', '(PATH="prefix:$suffix" cmake --build build)'),
      ('bash', 'echo "$(PATH="prefix:$suffix" cmake --build build)"'),
      ('bash', 'echo "$(sh -c \'PATH="prefix:$suffix" cmake --build build\')"'),
      ('bash', 'cat $(# )\nPATH="prefix:$suffix"\nprintf %s "$PATH"\n)'),
      ('bash', 'cat $(cat <<EOF\n)\nEOF\nPATH="prefix:$suffix"\nprintf %s "$PATH"\n)'),
      ('bash', 'cat $(case x in x) :;; esac\nPATH="prefix:$suffix"\nprintf %s "$PATH"\n)'),
      ('bash', 'cat <(case x in x) :;; esac\nPATH="prefix:$suffix"\nprintf %s "$PATH"\n)'),
      ('bash', 'cat \rPATH=prefix:$suffix'),
      ('sh', 'cat \rPATH=prefix:$suffix'),
      ('zsh', 'cat \rPATH=prefix:$suffix'),
      ('pwsh', 'Unknown-Command $env:PATH="prefix;$suffix"'),
      ('pwsh', '$env:PATH="prefix;$suffix" | Unknown-Command'),
      ('pwsh', 'Unknown-Command { $env:PATH="prefix;$suffix" }'),
      ('pwsh', 'Get-Content $(Write-Output ready; $env:PATH="prefix;$suffix")'),
      ('pwsh', 'Get-Content (# )\n$env:PATH="prefix;$suffix")'),
      ('pwsh', 'Get-Content (# )\n$env:PATH="prefix;$suffix"\n)'),
      ('pwsh', 'Get-Content (# )\n$env:PATH="prefix;$suffix";\n)'),
      ('pwsh', 'Unknown-Command { # }\n$env:PATH="prefix;$suffix" }'),
      ('pwsh', 'Unknown-Command { # }\n$env:PATH="prefix;$suffix"\n}'),
      ('pwsh', "Get-Content $(@'\n')'\n'@\n$env:PATH=\"prefix;$suffix\"\n$env:PATH\n)"),
      ('pwsh', '$env:PATH = "prefix;$suffix"; cmake --build build'),
      ('cmd', 'set PATH=prefix:%suffix%'),
    )
    for shell, command in denied:
      with self.subTest(shell=shell, command=command):
        self.assertEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': shell}).get('decision'), 'deny')

  def test_path_assignment_pretooluse_protocol(self):
    for shell, command, denied in (
        ('bash', 'PATH="$PWD/build-quality-venv/bin:$PATH" python3 -B scripts/quality.py', False),
        ('bash', 'PATH="bin:$PATH" cat .env', True),
        ('bash', 'cat <PATH=prefix:$suffix', True),
        ('bash', 'cat >PATH=prefix:$suffix', True),
        ('pwsh', 'Get-Content ($env:PATH="prefix;$suffix")', True)):
      raw = event(tool='exec_command', cwd=self.temp.name,
        tool_input={'cmd': command, 'shell': shell})
      with self.subTest(command=command), patch.object(sys, 'stdin', io.StringIO(json.dumps(raw))), \
        patch.object(sys, 'stdout', io.StringIO()) as stdout, \
        patch.object(sys, 'stderr', io.StringIO()) as stderr:
        self.assertEqual(codex_hooks.main(), 0)
        self.assertEqual(stderr.getvalue(), '')
        if denied:
          self.assertEqual(json.loads(stdout.getvalue()), {'hookSpecificOutput': {
            'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
            'permissionDecisionReason': 'Protected .env or PEM path. Use a redacted example file.',
          }})
        else:
          self.assertEqual(stdout.getvalue(), '')

  def test_wildcard_overlap_uses_complete_candidate_names(self):
    for candidate, protected, expected in (
        ('bin:*', '*.pem', True), ('bin', '*.pem', False),
        ('*.txt', '*.pem', False), ('.en?', '.env', True),
        ('key.pem.txt', '*.pem', False)):
      with self.subTest(candidate=candidate):
        self.assertEqual(codex_hooks.shell_patterns_overlap(candidate, protected), expected)

  def test_installer_command_strings_keep_dynamic_assignments_allowed(self):
    windows = r'''$script:CONF_DIR = 'C:\Users\rannd\Projects\dotfiles\confs'
$script:DRY_RUN = $false
$script:auditCopies = @()
function Write-Log { param($Message, $Level) }
function Assert-File { param($Path) if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { throw 'Missing source file' } }
function Assert-Directory { param($Path) if (!(Test-Path -LiteralPath $Path -PathType Container)) { throw 'Missing source directory' } }
function Install-UserFile { param($Source,$Destination) $script:auditCopies += [pscustomobject]@{Source=$Source;Destination=$Destination} }
. .\modules\codex.ps1
function Install-CodexCli {}
function New-CodexDirectory { param($Path) }
Invoke-codex
if ($script:auditCopies.Count -lt 11) { throw 'Incomplete installation mapping' }
if (($script:auditCopies | Where-Object {$_.Source -like '*cavecrew-*.toml'}).Count -ne 3) { throw 'Missing crew role' }
if (($script:auditCopies | Where-Object {$_.Source -like '*hooks\*.py'}).Count -ne 2) { throw 'Missing hook source' }
if (!(($script:auditCopies | Where-Object {$_.Source -like '*windows.config.toml'}).Destination -like '*\.codex\config.toml')) { throw 'Wrong platform config destination' }
"Mocked Windows installer mapping OK: $($script:auditCopies.Count) files; no destination writes"'''
    posix = '''copy_count=0
install_user_file() { require_file "$1"; copy_count=$((copy_count + 1)); }
require_file() { test -f "$1" || exit 1; }
. ./modules/codex.sh
module_codex
test "$copy_count" -ge 11
printf 'Mocked Linux installer mapping OK: %s files\\n' "$copy_count"'''
    for shell, command in (('powershell', windows), ('sh', posix)):
      with self.subTest(shell=shell):
        self.assertNotEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': shell}).get('decision'), 'deny')

  def test_assignment_values_keep_secret_guards(self):
    commands = (
      ('powershell', '$copy="key.pem"'),
      ('powershell', '$copy=.en$part'),
      ('pwsh', '[pscustomobject]@{Source=".env"}'),
      ('pwsh', '@{Source=$value.pem}'),
      ('sh', 'SOURCE=.env'),
      ('sh', 'copy_count=$((copy_count + 1)).pem'),
      ('bash', 'SOURCE=.en$part'),
    )
    for shell, command in commands:
      with self.subTest(shell=shell, command=command):
        self.assertEqual(self.shell_read(command,
          tool_input={'cmd': command, 'shell': shell}).get('decision'), 'deny')

  def test_assignment_like_filename_operands_keep_secret_guards(self):
    for shell in ('powershell', 'pwsh', 'sh', 'bash'):
      for command in ('cat "Source=key.pem"', 'cat "Source=$value"', 'cat Source=$value'):
        with self.subTest(shell=shell, command=command):
          self.assertEqual(self.shell_read(command,
            tool_input={'cmd': command, 'shell': shell}).get('decision'), 'deny')
    for shell in ('powershell', 'pwsh'):
      for command in ('@{Source=Get-Content Source=$value}',
        '[pscustomobject]@{Source=Get-Content Source=$value}',
        '@{Source=(Get-Content Source=$value)}',
        "@{'Source'=Get-Content Source=$value}",
        '[pscustomobject]@{First=$value;Source=Get-Content Source=$value}',
        '@{First=$value\nSource=Get-Content Source=$value}'):
        with self.subTest(shell=shell, command=command):
          self.assertEqual(self.shell_read(command,
            tool_input={'cmd': command, 'shell': shell}).get('decision'), 'deny')

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

  def test_filesystem_guard_is_wired_on_both_platforms(self):
    root = Path(__file__).resolve().parents[2] / 'confs/codex'
    for platform in ('windows', 'linux'):
      config = json.loads((root / (platform + '.hooks.json')).read_text(encoding='utf-8'))
      self.assertEqual(set(config['hooks']), {'PreToolUse'})
      guards = [entry for entry in config['hooks']['PreToolUse']
        if any('codex_hooks.py' in hook['command'] for hook in entry['hooks'])]
      self.assertEqual(len(guards), 1)
      for tool in ('read_text_file', 'read_multiple_files', 'edit_file', 'write_file',
          'create_directory', 'move_file', 'list_directory', 'get_file_info',
          'search_files', 'future_tool'):
        self.assertRegex('mcp__filesystem__' + tool, guards[0]['matcher'])

  def test_filesystem_paths_are_protected_in_both_path_dialects(self):
    for root in ('/home/rann/project/', 'C:/Users/rannd/project/', 'C:\\Users\\rannd\\project\\'):
      for name in ('.env', '.env.local', '.env.production', '.env.test.local', 'KEY.PEM'):
        path = root + name
        for tool in ('read_text_file', 'edit_file', 'write_file', 'create_directory',
            'list_directory', 'get_file_info', 'search_files'):
          with self.subTest(path=path, tool=tool):
            data = {'path': path, 'content': 'public', 'edits': [], 'dryRun': True}
            result = codex_hooks.dispatch(event(tool='mcp__filesystem__' + tool, tool_input=data))
            self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')
        for data in ({'source': path, 'destination': root + 'safe.txt'},
            {'source': root + 'safe.txt', 'destination': path},
            {'paths': [root + 'safe.txt', path]}):
          tool = 'read_multiple_files' if 'paths' in data else 'move_file'
          self.assertEqual(self.policy(event(tool='mcp__filesystem__' + tool,
            tool_input=data)).get('decision'), 'deny')

  def test_filesystem_safe_operations_leave_approval_to_host(self):
    operations = {
      'read_text_file': {'path': '/project/docs.txt'},
      'read_multiple_files': {'paths': ['/project/docs.txt', '/project/.env.example']},
      'edit_file': {'path': '/project/main.py', 'edits': [{'oldText': 'a', 'newText': 'b'}]},
      'write_file': {'path': '/project/new.txt', 'content': 'Example: .env and key.pem'},
      'create_directory': {'path': '/project/new'},
      'move_file': {'source': '/project/old.txt', 'destination': '/project/new.txt'},
    }
    for tool, data in operations.items():
      with self.subTest(tool=tool):
        self.assertEqual(self.policy(event(tool='mcp__filesystem__' + tool, tool_input=data)), {})
    self.assertEqual(list(Path(self.temp.name).iterdir()), [])

  def test_filesystem_malformed_arguments_do_not_crash_or_hide_valid_paths(self):
    # MCP schemas reject missing/wrong types; the hook independently checks
    # recognizable paths and never interprets content as a target.
    for data in ({}, None, [], 'not json', 7, {'path': None}, {'path': 7},
        {'path': {}}, {'paths': [None, 7, {}]}, {'unexpected': 'public'}):
      for tool in ('read_text_file', 'edit_file', 'write_file', 'create_directory', 'move_file'):
        with self.subTest(data=data, tool=tool):
          self.assertEqual(self.policy(event(tool='mcp__filesystem__' + tool, tool_input=data)), {})
    for data in ({'source': None, 'destination': '/project/.env'},
        {'source': 'C:/project/key.pem', 'destination': {}},
        {'paths': [None, {}, '/project/.env']},
        {'path': '/project/.env', 'edits': 'malformed', 'unexpected': True}):
      self.assertEqual(self.policy(event(tool='mcp__filesystem__move_file',
        tool_input=data)).get('decision'), 'deny')

  def test_native_shell_encoded_paths_keep_terminal_guards(self):
    for tool, key in (('exec_command', 'cmd'), ('Bash', 'command')):
      for shell, command in (('bash', r"cat $'.en\x76'"),
          ('bash', r"cat $'key.pe\155'"), ('pwsh', 'Get-Content "*.pem"'),
          ('pwsh', 'Remove-Item cache -Recurse')):
        with self.subTest(tool=tool, shell=shell, command=command):
          self.assertEqual(self.policy(event(tool=tool,
            tool_input={key: command, 'shell': shell})).get('decision'), 'deny')

if __name__ == '__main__':
  unittest.main()
