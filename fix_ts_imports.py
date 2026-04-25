import os
import re

directory = 'test'
pattern = re.compile(r'(import\s+(?:type\s+)?\{\s*[^}]*\bLADAConfig\b[^}]*\}\s+from\s+[\'\"])(.*?)src/config/config\.js([\'\"])')

count = 0
for root, dirs, files in os.walk(directory):
    for f in files:
        if f.endswith('.ts') or f.endswith('.js'):
            filepath = os.path.join(root, f)
            with open(filepath, 'r', encoding='utf-8') as file:
                content = file.read()
            
            new_content, num_subs = pattern.subn(r'\g<1>\g<2>src/config/types.openclaw.js\g<3>', content)
            
            if num_subs > 0:
                with open(filepath, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                count += 1
                print(f'Fixed {filepath}')

print(f'Fixed {count} files.')
