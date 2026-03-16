import json
import sys

# Read features.json
with open(r'C:\Users\15849\.factory\missions\e1318aaa-e97f-4a29-83bb-3631d7619d26\features.json', 'r') as f:
    features_data = json.load(f)

# Extract m2-resource-management completed features
milestone_features = [
    f for f in features_data['features'] 
    if f.get('milestone') == 'm2-resource-management' 
    and f.get('status') == 'completed'
    and not (f.get('skillName', '').startswith('scrutiny-') or f.get('skillName', '').startswith('user-testing-'))
]

# Collect all fulfills
fulfills = set()
for f in milestone_features:
    fulfills.update(f.get('fulfills', []))

print("Assertions from completed features:")
print(json.dumps(sorted(list(fulfills)), indent=2))

# Read validation-state.json
with open(r'C:\Users\15849\.factory\missions\e1318aaa-e97f-4a29-83bb-3631d7619d26\validation-state.json', 'r') as f:
    state = json.load(f)

# Filter for pending m2 assertions
pending = [k for k, v in state.items() if v == 'pending' and k.startswith('m2-')]

print("\nPending m2 assertions:")
print(json.dumps(pending, indent=2))

# Intersection
testable = sorted(list(fulfills.intersection(set(pending))))
print("\nTestable assertions (completed features + pending state):")
print(json.dumps(testable, indent=2))
