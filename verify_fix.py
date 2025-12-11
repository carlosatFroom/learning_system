
def clean_id(youtube_id):
    if '&' in youtube_id:
        youtube_id = youtube_id.split('&')[0]
    if '?' in youtube_id:
        youtube_id = youtube_id.split('?')[0]
    return youtube_id

test_cases = [
    ("98DcoXwGX6I", "98DcoXwGX6I"),
    ("98DcoXwGX6I&pp=123", "98DcoXwGX6I"),
    ("98DcoXwGX6I?t=10", "98DcoXwGX6I"),
    ("98DcoXwGX6I&list=PL123", "98DcoXwGX6I"),
]

print("Running Cleaning Logic Verification...")
all_passed = True
for raw, expected in test_cases:
    result = clean_id(raw)
    if result == expected:
        print(f"[PASS] {raw} -> {result}")
    else:
        print(f"[FAIL] {raw} -> {result} (Expected: {expected})")
        all_passed = False

if all_passed:
    print("\nSUCCESS: All cleaning logic tests passed.")
else:
    print("\nFAILURE: Some tests failed.")
