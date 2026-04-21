import os

for p, d, f in os.walk(r'c:\lada ai'):
    if 'node_modules' in p or '.git' in p: continue
    for x in f:
        if x.endswith('.ts') or x.endswith('.json'):
            fp = os.path.join(p, x)
            try:
                with open(fp, 'r', encoding='utf-8') as file:
                    text = file.read()
                if '"test/setup' in text or '"./test/setup' in text:
                    text = text.replace('"test/setup', '"tests/setup')
                    text = text.replace('"./test/setup', '"./tests/setup')
                    with open(fp, 'w', encoding='utf-8') as file:
                        file.write(text)
                    print('Fixed ' + fp)
            except Exception: pass
