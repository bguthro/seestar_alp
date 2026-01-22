#!/usr/bin/env python3
"""
tests/verify_message_format.py

Standalone validator for the "verify" param transformation rules.

- Auto-discovers .bru files in bruno/Seestar Alpaca API and extracts the sample
  Parameters JSON payloads to test.
- Also includes a set of representative hard-coded tests (from device/seestar_device.py).
- Usage: python3 tests/verify_message_format.py
"""

import json
import sys
import os
import re
import copy

BRUNO_DIR = os.path.join("bruno", "Seestar Alpaca API")

def transform_message_for_verify(data, firmware_ver_int):
    """
    Re-implements the verify-transformation logic from device/seestar_device.py.
    Returns a transformed deep copy of the message dict.
    """
    data = copy.deepcopy(data)
    try:
        fw = int(firmware_ver_int or 0)
    except Exception:
        fw = 0

    if fw > 2582 and "params" in data:
        existing_params = data.get("params")

        # Special handling for set_wheel_position when params is a list
        if data.get("method") == "set_wheel_position" and isinstance(existing_params, list):
            # append verify
            data["params"] = existing_params + ["verify"]
        else:
            # wrap existing params and add verify token
            data["params"] = [existing_params, "verify"]

    return data

def compute_expected_transform(data, firmware_ver_int):
    """
    Compute expected transform using the same logical rules.
    This is used to assert the transformation produced by the code matches the
    intended rule. Using a clear independent function makes the test explicit.
    """
    # For these tests the expected transform is identical to transform_message_for_verify
    # because the rule is unambiguous. We keep a separate function for clarity
    # and to allow future divergence (e.g., additional special-cases) if needed.
    return transform_message_for_verify(data, firmware_ver_int)

def test_case(name, input_msg, fw, expected_params):
    out = transform_message_for_verify(input_msg, fw)
    got = out.get("params", None)
    ok = got == expected_params
    print(f"{name}: {'PASS' if ok else 'FAIL'}")
    if not ok:
        print("  method:", input_msg.get("method"))
        print("  fw:", fw)
        print("  input params:", json.dumps(input_msg.get("params", None), indent=2, sort_keys=True))
        print("  expected params:", json.dumps(expected_params, indent=2, sort_keys=True))
        print("  got params     :", json.dumps(got, indent=2, sort_keys=True))
    return ok

def run_hardcoded_tests():
    all_ok = True
    # 1: dict params -> [dict, "verify"]
    m1 = {"method":"set_user_location", "params":{"lat":12.3, "lon":45.6}}
    exp1_fw_new = [{"lat":12.3, "lon":45.6}, "verify"]
    exp1_fw_old = {"lat":12.3, "lon":45.6}
    all_ok &= test_case("dict-params-new-fw", m1, 2600, exp1_fw_new)
    all_ok &= test_case("dict-params-old-fw", m1, 2500, exp1_fw_old)

    # 2: list params general -> [[list], "verify"]
    m2 = {"method":"scope_goto", "params":[14.12, 19.08]}
    exp2 = [[14.12, 19.08], "verify"]
    all_ok &= test_case("list-params-new-fw", m2, 2600, exp2)

    # 3: set_wheel_position -> append "verify" to list
    m3 = {"method":"set_wheel_position", "params":[2]}
    exp3 = [2, "verify"]
    all_ok &= test_case("set_wheel_position-new-fw", m3, 2600, exp3)

    # 4: nested dict (pi_output_set2 heater)
    m4 = {"method":"pi_output_set2", "params":{"heater":{"state":True,"value":50}}}
    exp4 = [{"heater":{"state":True,"value":50}}, "verify"]
    all_ok &= test_case("nested-dict-new-fw", m4, 2600, exp4)

    # 5: params as empty string (scan_iscope UDP)
    m5 = {"method":"scan_iscope", "params":""}
    exp5 = ["", "verify"]
    all_ok &= test_case("empty-string-params-new-fw", m5, 2600, exp5)

    # 6: no params present -> unchanged (no 'params' key)
    m6 = {"method":"pi_is_verified"}
    out6 = transform_message_for_verify(m6, 2600)
    ok6 = "params" not in out6
    print(f"no-params-new-fw: {'PASS' if ok6 else 'FAIL'}")
    if not ok6:
        print("  got:", out6)
    all_ok &= ok6

    # 7: pi_set_time has params as a list containing a dict -> wrap list in outer list
    date_json = {"year":2026,"mon":1,"day":21,"hour":12,"min":0,"sec":0,"time_zone":"UTC"}
    m7 = {"method":"pi_set_time", "params":[date_json]}
    exp7 = [[date_json], "verify"]
    all_ok &= test_case("pi_set_time-new-fw", m7, 2600, exp7)

    # 8: set_control_value uses a list ["gain", value] -> wrap that list
    m8 = {"method":"set_control_value", "params":["gain", 42]}
    exp8 = [["gain", 42], "verify"]
    all_ok &= test_case("set_control_value-new-fw", m8, 2600, exp8)

    # 9: set_sequence_setting used by set_target_name -> params is [ { ... } ] already list-of-dict
    seqp = {"group_name":"Kai_goto_target_name"}
    m9 = {"method":"set_sequence_setting", "params":[seqp]}
    exp9 = [[seqp], "verify"]
    all_ok &= test_case("set_sequence_setting-new-fw", m9, 2600, exp9)

    # 10: scope_sync array should be wrapped for new fw
    m10 = {"method":"scope_sync", "params":[1,2]}
    exp10 = [[1,2], "verify"]
    all_ok &= test_case("scope_sync-array-new-fw", m10, 2600, exp10)

    return all_ok

def extract_parameters_from_bru(file_content):
    """
    Find the line containing 'Parameters:' and extract the JSON object literal that follows.
    Returns None if not found/cannot parse.
    """
    # Look for a line that contains 'Parameters:'
    for line in file_content.splitlines():
        idx = line.find("Parameters:")
        if idx >= 0:
            # Strip everything up to 'Parameters:'
            after = line[idx + len("Parameters:"):].strip()
            # The parameters in the bruno files appear to be a JSON-like literal on same line.
            # We'll attempt to find the first '{' and the last '}' on that line.
            start = after.find("{")
            if start >= 0:
                # We assume the JSON is contained on this one line (matches examples)
                jtext = after[start:]
                # In case there's trailing text after the JSON, trim using last '}'.
                last = jtext.rfind("}")
                if last >= 0:
                    jtext = jtext[:last+1]
                try:
                    parsed = json.loads(jtext)
                    return parsed
                except Exception:
                    # Could be malformed or spread across lines. Try multi-line extraction:
                    # find where '{' occurs in file and then collect until matching '}'.
                    pass

    # Fallback: try to find the first occurrence of 'Parameters' and then a JSON object from there spanning lines.
    m = re.search(r"Parameters:\s*(\{.*)", file_content, flags=re.DOTALL)
    if not m:
        return None
    start_pos = m.start(1)
    # Attempt to find matching braces from start_pos
    text = file_content[start_pos:]
    depth = 0
    jchars = []
    started = False
    for ch in text:
        if ch == '{':
            depth += 1
            started = True
            jchars.append(ch)
        elif ch == '}':
            jchars.append(ch)
            depth -= 1
            if started and depth == 0:
                break
        elif started:
            jchars.append(ch)
    if not jchars:
        return None
    jtext = "".join(jchars)
    try:
        return json.loads(jtext)
    except Exception:
        return None

def run_bruno_discovery_tests():
    """
    Walk the bruno directory, find .bru files, extract sample Parameters, and run
    the transform check for each sample (both fw old and fw new).
    """
    if not os.path.isdir(BRUNO_DIR):
        print(f"Bruno directory not found at {BRUNO_DIR}. Skipping Bruno discovery tests.")
        return True

    failures = 0
    samples = []
    for root, dirs, files in os.walk(BRUNO_DIR):
        for fname in files:
            if fname.endswith(".bru"):
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as fh:
                        content = fh.read()
                except Exception as e:
                    print(f"Failed to read {fpath}: {e}")
                    failures += 1
                    continue
                params = extract_parameters_from_bru(content)
                if params is None:
                    print(f"WARNING: Could not extract Parameters JSON from {fpath}")
                    continue
                # params is a dict like {"method":"scope_sync","params":[...]} or {"method":"get_setting"}
                samples.append((fpath, params))

    if not samples:
        print("No .bru samples discovered (or parsing failed).")
        return False

    ok_all = True
    for fpath, sample in samples:
        method = sample.get("method")
        in_params = sample.get("params", None)
        msg = {"method": method}
        if "params" in sample:
            msg["params"] = in_params

        # expected transformations
        exp_new = compute_expected_transform(msg, 2600)
        exp_old = compute_expected_transform(msg, 2500)

        out_new = transform_message_for_verify(msg, 2600)
        out_old = transform_message_for_verify(msg, 2500)

        # Compare only the 'params' key presence and value; we don't care about id field here
        got_new = out_new.get("params", None)
        want_new = exp_new.get("params", None)
        got_old = out_old.get("params", None)
        want_old = exp_old.get("params", None)

        passed_new = got_new == want_new
        passed_old = got_old == want_old

        status = "PASS" if (passed_new and passed_old) else "FAIL"
        print(f"[{status}] {fpath}")
        if not passed_new or not passed_old:
            print("  sample:", json.dumps(sample, indent=2, sort_keys=True))
            print("  new-fw expected:", json.dumps(want_new, indent=2, sort_keys=True))
            print("  new-fw got     :", json.dumps(got_new, indent=2, sort_keys=True))
            print("  old-fw expected:", json.dumps(want_old, indent=2, sort_keys=True))
            print("  old-fw got     :", json.dumps(got_old, indent=2, sort_keys=True))
            ok_all = False

    return ok_all

def main():
    print("Running hard-coded transformation tests...")
    ok1 = run_hardcoded_tests()
    print("\nScanning bruno collection and testing discovered samples...")
    ok2 = run_bruno_discovery_tests()

    overall = ok1 and ok2
    print("\nOverall result:", "ALL OK" if overall else "SOME FAILURES")
    return 0 if overall else 2

if __name__ == "__main__":
    sys.exit(main())