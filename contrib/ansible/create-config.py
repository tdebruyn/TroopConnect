import yaml
import subprocess
import os
import tempfile
import sys
import shutil

CLEAR_VAULT_FILE = 'clear-vault.yml'
CONFIG_FILE = 'config.yml'
VAULT_FILE = 'vault.yml'

def load_yaml(filename):
    try:
        with open(filename, 'r') as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        print(f"❌ Error: {filename} not found. Make sure it exists in the package.")
        sys.exit(1)

def write_yaml(filename, data):
    with open(filename, 'w') as f:
        yaml.dump(data, f, default_flow_style=False)

def prompt_update(data, is_secret=False, show_clear=True):
    updated = {}
    for key, current_value in data.items():
        if is_secret and show_clear:
            prompt = f"{key} [{current_value}]: "
            user_input = input(prompt)
        elif is_secret:
            # fallback: use getpass if hiding is needed
            from getpass import getpass
            user_input = getpass(f"{key}: ")
        else:
            prompt = f"{key} [{current_value}]: "
            user_input = input(prompt)
        updated[key] = user_input if user_input else current_value
    return updated

def update_config():
    print("=== Updating config.yml (non-sensitive data) ===")
    config_data = load_yaml(CONFIG_FILE)
    updated_config = prompt_update(config_data, is_secret=False)
    write_yaml(CONFIG_FILE, updated_config)
    print("✅ config.yml updated.")

def update_vault():
    print("\n=== Updating vault.yml (sensitive data) ===")
    clear_data_original = load_yaml(CLEAR_VAULT_FILE)

    # Prompt with current values shown in clear text
    updated_clear = prompt_update(clear_data_original, is_secret=True, show_clear=True)

    # Overwrite clear-vault.yml with updated values temporarily
    write_yaml(CLEAR_VAULT_FILE, updated_clear)

    # Encrypt it to vault.yml
    with tempfile.NamedTemporaryFile('w+', delete=False) as tmpfile:
        yaml.dump(updated_clear, tmpfile, default_flow_style=False)
        tmpfile_path = tmpfile.name

    try:
        subprocess.run(['ansible-vault', 'encrypt', tmpfile_path, '--output', VAULT_FILE], check=True)
        print("🔐 vault.yml encrypted successfully.")
    except subprocess.CalledProcessError:
        print("❌ Error: Failed to encrypt with Ansible Vault.")
    finally:
        os.unlink(tmpfile_path)

    # Restore original clear-vault.yml
    write_yaml(CLEAR_VAULT_FILE, clear_data_original)
    print("♻️ clear-vault.yml reverted to original values.")

def main():
    print("=== Ansible Config + Vault Interactive Editor ===\n")
    update_config()
    update_vault()
    print("\n🎉 Done! config.yml and vault.yml are ready to use. clear-vault.yml has been restored.")

if __name__ == "__main__":
    main()
