import subprocess
import time
import xml.etree.ElementTree as ET
import os
import re

def run_adb(command, device_id="U4G6R20509000263"):
    cmd = f"adb -s {device_id} {command}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

def take_screenshot(device_id, name):
    os.makedirs("captures/device", exist_ok=True)
    filename = f"captures/device/{name}_{int(time.time())}.png"
    run_adb(f"shell screencap -p /sdcard/screen.png", device_id)
    subprocess.run(f"adb -s {device_id} pull /sdcard/screen.png {filename}", shell=True, capture_output=True)
    print(f"Screenshot saved to {filename}")
    return filename

def get_screen_xml(device_id="U4G6R20509000263"):
    run_adb("shell uiautomator dump /sdcard/view.xml", device_id)
    xml_content = run_adb("shell cat /sdcard/view.xml", device_id)
    return xml_content

def find_and_click(text_pattern, device_id="U4G6R20509000263"):
    xml_content = get_screen_xml(device_id)
    if not xml_content or ("UI hierachy" not in xml_content and "<hierarchy" not in xml_content):
        return False
    
    try:
        root = ET.fromstring(xml_content)
    except Exception as e:
        return False

    for node in root.iter('node'):
        text = node.get('text', '')
        content_desc = node.get('content-desc', '')
        res_id = node.get('resource-id', '')
        cls = node.get('class', '')
        
        # Stricter matching: must be a button or have specific text
        if re.fullmatch(text_pattern, text, re.IGNORECASE) or re.fullmatch(text_pattern, content_desc, re.IGNORECASE):
            bounds = node.get('bounds')
            if bounds:
                match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if match:
                    x1, y1, x2, y2 = map(int, match.groups())
                    center_x = (x1 + x2) // 2
                    center_y = (y1 + y2) // 2
                    
                    # Log what we found
                    print(f"MATCH: '{text_pattern}' | ID: {res_id} | Class: {cls} | Bounds: {bounds}")
                    
                    # Take screenshot before clicking
                    take_screenshot(device_id, f"before_{text_pattern}")
                    
                    print(f"Clicking at ({center_x}, {center_y})...")
                    run_adb(f"shell input tap {center_x} {center_y}", device_id)
                    time.sleep(1)
                    return True
    return False

def handle_install_prompts(device_id="U4G6R20509000263", timeout=180):
    start_time = time.time()
    # Using fullmatch patterns for better precision
    patterns = ["CONTINUE", "INSTALL", "OPEN", "ACCEPT", "ALLOW", "DONE", "UPDATE"]
    print(f"Monitoring device {device_id} for installation prompts (Timeout: {timeout}s)...")
    
    last_action_time = time.time()
    while time.time() - start_time < timeout:
        found = False
        for pattern in patterns:
            if find_and_click(pattern, device_id):
                found = True
                last_action_time = time.time()
                time.sleep(3) # Wait for UI transition
                break
        
        if not found:
            # If no buttons found for 30 seconds, take a "stuck" screenshot
            if time.time() - last_action_time > 30:
                take_screenshot(device_id, "stuck_waiting")
                last_action_time = time.time()
            time.sleep(2)
            
    print("Installation monitoring complete.")

if __name__ == "__main__":
    import sys
    device = sys.argv[1] if len(sys.argv) > 1 else "U4G6R20509000263"
    tout = int(sys.argv[2]) if len(sys.argv) > 2 else 180
    handle_install_prompts(device, tout)
