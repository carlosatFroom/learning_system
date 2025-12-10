import os
import sys
import subprocess
import platform

def print_step(step):
    print(f"\n{'='*40}")
    print(f"STEP: {step}")
    print(f"{'='*40}")

def check_python_version():
    print_step("Checking Python Version")
    version = sys.version_info
    print(f"Current Python: {sys.version}")
    if version.major < 3 or (version.major == 3 and version.minor < 9):
        print("❌ Error: Python 3.9+ is required.")
        sys.exit(1)
    print("✅ Python version OK.")

def create_venv():
    print_step("Creating Virtual Environment")
    venv_dir = "venv"
    
    if os.path.exists(venv_dir):
        print(f"ℹ️  '{venv_dir}' already exists. Skipping creation.")
        return

    try:
        import venv
        venv.create(venv_dir, with_pip=True)
        print(f"✅ Created virtual environment in '{venv_dir}'")
    except ImportError:
        print("❌ Error: 'venv' module not found.")
        print("On Debian/Ubuntu, try running: sudo apt-get install python3-venv")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to create venv: {e}")
        sys.exit(1)

def install_requirements():
    print_step("Installing Dependencies")
    
    # Determine pip path based on OS
    if platform.system() == "Windows":
        pip_cmd = os.path.join("venv", "Scripts", "pip")
    else:
        pip_cmd = os.path.join("venv", "bin", "pip")

    if not os.path.exists(pip_cmd):
        print(f"❌ Error: pip not found at {pip_cmd}")
        print("The virtual environment might be corrupt. Try deleting the 'venv' folder and running this script again.")
        sys.exit(1)

    req_file = os.path.join("backend", "requirements.txt")
    if not os.path.exists(req_file):
        print(f"❌ Error: {req_file} not found.")
        sys.exit(1)

    print(f"Installing from {req_file}...")
    try:
        subprocess.check_call([pip_cmd, "install", "-r", req_file])
        print("✅ Dependencies installed successfully.")
    except subprocess.CalledProcessError:
        print("❌ Error installing dependencies.")
        sys.exit(1)

def main():
    print("🚀 Starting Setup for Learning System...")
    check_python_version()
    create_venv()
    install_requirements()
    
    print("\n" + "*"*50)
    print("✅ SETUP COMPLETE!")
    print("*"*50)
    print("\nTo start the backend:")
    if platform.system() == "Windows":
        print("  venv\\Scripts\\uvicorn backend.main:app --reload")
    else:
        print("  venv/bin/uvicorn backend.main:app --reload")

if __name__ == "__main__":
    main()
