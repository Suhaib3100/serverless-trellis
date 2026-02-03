#!/usr/bin/env python3
"""Upload files to RunPod pod using SSH via paramiko"""
import paramiko
import base64
import os
import sys

POD_ID = "wy34jof2tbfcc9"
SSH_HOST = "213.192.2.94"
SSH_PORT = 40130
SSH_USER = "root"
SSH_KEY_PATH = os.path.expanduser("~/.runpod/ssh/main")

def get_ssh_client():
    """Create SSH client connection"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    # Try with the runpod key
    try:
        key = paramiko.RSAKey.from_private_key_file(SSH_KEY_PATH)
        client.connect(SSH_HOST, port=SSH_PORT, username=SSH_USER, pkey=key, timeout=30)
        return client
    except Exception as e:
        print(f"SSH connection failed: {e}")
        return None

def run_command(ssh: paramiko.SSHClient, command: str) -> tuple:
    """Run command on remote"""
    stdin, stdout, stderr = ssh.exec_command(command)
    return stdout.read().decode(), stderr.read().decode()

def upload_file(ssh: paramiko.SSHClient, local_path: str, remote_path: str):
    """Upload file via SFTP"""
    sftp = ssh.open_sftp()
    sftp.put(local_path, remote_path)
    sftp.close()
    print(f"Uploaded: {local_path} -> {remote_path}")

if __name__ == "__main__":
    print("Connecting to pod via SSH...")
    ssh = get_ssh_client()
    
    if ssh is None:
        print("\n⚠️  SSH key not working. The pod was created before the key was added.")
        print("\nAlternative: Use the Web Terminal in RunPod dashboard:")
        print("  1. Go to https://www.runpod.io/console/pods")
        print("  2. Click on your pod -> Connect -> Web Terminal")  
        print("  3. Run these commands:\n")
        
        # Generate wget commands for web terminal
        print("# Download files directly from GitHub (you'll need to create a gist)")
        print("# Or paste the script content directly:\n")
        
        print("cat > /workspace/setup_test.sh << 'SETUP_EOF'")
        with open("test/setup_test.sh", "r") as f:
            print(f.read())
        print("SETUP_EOF")
        
        print("\nchmod +x /workspace/setup_test.sh")
        print("\n# Then run it:")
        print("cd /workspace && ./setup_test.sh")
        
        sys.exit(1)
    
    print("✅ Connected!\n")
    
    # Upload files
    print("--- Uploading files ---")
    upload_file(ssh, "test/setup_test.sh", "/workspace/setup_test.sh")
    upload_file(ssh, "handler.py", "/workspace/handler.py")
    
    # Make executable
    print("\n--- Making script executable ---")
    out, err = run_command(ssh, "chmod +x /workspace/setup_test.sh")
    
    # List files
    print("\n--- Files on pod ---")
    out, err = run_command(ssh, "ls -la /workspace/")
    print(out)
    
    print("\n✅ Files uploaded! Now run:")
    print("   cd /workspace && ./setup_test.sh")
    
    ssh.close()
