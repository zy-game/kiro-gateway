import json

# Read validation state
with open(r'C:\Users\15849\.factory\missions\e1318aaa-e97f-4a29-83bb-3631d7619d26\validation-state.json', 'r', encoding='utf-8') as f:
    state = json.load(f)

# Read flow reports
flow_reports = [
    r'E:\kiro-gateway\.factory\validation\m2-resource-management\user-testing\flows\http-client-config.json',
    r'E:\kiro-gateway\.factory\validation\m2-resource-management\user-testing\flows\concurrent-load.json',
    r'E:\kiro-gateway\.factory\validation\m2-resource-management\user-testing\flows\connection-management.json'
]

passed = []
failed = []
blocked = []

for report_path in flow_reports:
    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)
    
    for assertion in report['assertions']:
        aid = assertion['id']
        status = assertion['status']
        
        if status == 'pass':
            passed.append(aid)
            state[aid] = 'passed'
        elif status == 'fail':
            failed.append({
                'id': aid,
                'reason': assertion.get('issues', 'Test failed')
            })
            state[aid] = 'failed'
        elif status == 'blocked':
            blocked.append({
                'id': aid,
                'blockedBy': assertion.get('issues', 'Unknown blocker')
            })
            state[aid] = 'failed'

# Write updated validation state
with open(r'C:\Users\15849\.factory\missions\e1318aaa-e97f-4a29-83bb-3631d7619d26\validation-state.json', 'w', encoding='utf-8') as f:
    json.dump(state, f, indent=2)

print("Passed assertions:", passed)
print("\nFailed assertions:", json.dumps(failed, indent=2))
print("\nBlocked assertions:", json.dumps(blocked, indent=2))
print("\nTotal: {} passed, {} failed, {} blocked".format(len(passed), len(failed), len(blocked)))
