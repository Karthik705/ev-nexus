import json
with open('llm_fixtures.json') as f:
    d = json.load(f)
for k, v in d.items():
    src = v.get('source', 'MISSING') if v else 'null'
    print(k + ': ' + src)
print()
live = sum(1 for v in d.values() if v and v.get('source') == 'gemini_live')
synth = sum(1 for v in d.values() if v and v.get('source') == 'synthetic_manual')
missing_src = sum(1 for v in d.values() if v and 'source' not in v)
print('gemini_live:', live, '  synthetic_manual:', synth, '  missing_source_field:', missing_src)
