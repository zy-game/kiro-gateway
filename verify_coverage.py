import json
import re
from collections import Counter

# Read validation contract
with open(r'C:\Users\15849\.factory\missions\1543c72d-ce4b-47b6-b4a6-64be6e278256\validation-contract.md', 'r', encoding='utf-8') as f:
    contract_text = f.read()

# Extract all assertion IDs from contract
contract_assertions = set(re.findall(r'VAL-[A-Z]+-\d+', contract_text))

# Read features.json
with open(r'C:\Users\15849\.factory\missions\1543c72d-ce4b-47b6-b4a6-64be6e278256\features.json', 'r', encoding='utf-8') as f:
    features_data = json.load(f)

# Extract all assertions from fulfills arrays
claimed_assertions = []
for feature in features_data['features']:
    for assertion in feature['fulfills']:
        claimed_assertions.append(assertion)

# Count occurrences
claim_counts = Counter(claimed_assertions)

# Find issues
unclaimed = sorted(contract_assertions - set(claimed_assertions))
duplicates = sorted([a for a, count in claim_counts.items() if count > 1])
invalid = sorted(set(claimed_assertions) - contract_assertions)

# Report
print(f'Total assertions in contract: {len(contract_assertions)}')
print(f'Total assertions claimed in features: {len(claimed_assertions)}')
print(f'Unique assertions claimed: {len(set(claimed_assertions))}')
print()
print(f'Unclaimed assertions: {unclaimed if unclaimed else "none"}')
print(f'Duplicate claims: {duplicates if duplicates else "none"}')
print(f'Invalid claims: {invalid if invalid else "none"}')
print()

if not unclaimed and not duplicates and not invalid:
    print('Coverage: PASS')
    print(f'Coverage verified: all {len(contract_assertions)} assertions claimed exactly once.')
else:
    print('Coverage: FAIL')
    if duplicates:
        print('\nDuplicate details:')
        for dup in duplicates:
            print(f'  {dup}: claimed {claim_counts[dup]} times')
