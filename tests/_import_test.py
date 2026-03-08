import sys
import os
import io
import importlib

# Fix stdout encoding for Unicode support
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add project root to sys.path
PROJECT_ROOT = r'c:\JarvisAI'
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

results_success = []
results_failure = []

def test_import(module_name, display_name=None):
    label = display_name or module_name
    try:
        mod = importlib.import_module(module_name)
        results_success.append(label)
        print(f'  [OK]   {label}')
        return True
    except Exception as e:
        err_type = type(e).__name__
        err_msg = str(e).split(chr(10))[0][:120]
        results_failure.append((label, f'{err_type}: {err_msg}'))
        print(f'  [FAIL] {label}  -->  {err_type}: {err_msg}')
        return False

print('=' * 80)
print('COMPREHENSIVE IMPORT TEST - c:\JarvisAI')
print('=' * 80)

# 1. Root-level modules
root_modules = [
    'lada_jarvis_core',
    'lada_ai_router',
    'lada_desktop_app',
    'main',
    'voice_tamil_free',
]
print(f'\n[1/3] ROOT MODULES ({len(root_modules)} files)')
print('-' * 60)
for m in root_modules:
    test_import(m)

# 2. modules/*.py
modules_dir = os.path.join(PROJECT_ROOT, 'modules')
mod_files = sorted([
    f[:-3] for f in os.listdir(modules_dir)
    if f.endswith('.py') and f != '__init__.py'
])
print(f'\n[2/3] modules/ PACKAGE ({len(mod_files)} files)')
print('-' * 60)
for m in mod_files:
    test_import(f'modules.{m}')

# 3. modules/agents/*.py
agents_dir = os.path.join(PROJECT_ROOT, 'modules', 'agents')
agent_files = sorted([
    f[:-3] for f in os.listdir(agents_dir)
    if f.endswith('.py') and f != '__init__.py'
])
print(f'\n[3/3] modules/agents/ PACKAGE ({len(agent_files)} files)')
print('-' * 60)
for m in agent_files:
    test_import(f'modules.agents.{m}')

# Summary
total = len(results_success) + len(results_failure)
print()
print('=' * 80)
print(f'RESULTS:  {len(results_success)}/{total} succeeded,  {len(results_failure)}/{total} failed')
print('=' * 80)

if results_failure:
    print()
    print('FAILED IMPORTS:')
    for name, reason in results_failure:
        print(f'  - {name}')
        print(f'    {reason}')

print()
print('Done.')
