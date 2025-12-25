import os
import subprocess
import shutil

def create_icns(png_path, icns_path):
    iconset_path = "icon.iconset"
    if os.path.exists(iconset_path):
        shutil.rmtree(iconset_path)
    os.makedirs(iconset_path)
    
    # macOS iconset naming convention is strict
    # icon_16x16.png, icon_16x16@2x.png, etc.
    res_list = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png")
    ]
    
    print(f"Generating iconset from {png_path}...")
    for size, name in res_list:
        out_file = os.path.join(iconset_path, name)
        # Use sips to resize
        subprocess.run(["sips", "-z", str(size), str(size), png_path, "--out", out_file], check=True, capture_output=True)
    
    print(f"Creating {icns_path} using iconutil...")
    result = subprocess.run(["iconutil", "-c", "icns", iconset_path, "-o", icns_path], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"iconutil failed: {result.stderr}")
        return False
    
    # Optional cleanup
    shutil.rmtree(iconset_path)
    print("Done.")
    return True

if __name__ == "__main__":
    if create_icns("icon_stable.png", "icon.icns"):
        print("Success")
    else:
        print("Failure")
        exit(1)
