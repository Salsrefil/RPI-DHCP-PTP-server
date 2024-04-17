import subprocess

def get_grandmaster_address():
    # The command to get the Grandmaster identity
    cmd = ["sudo", "pmc", "-u", "-i", "eth0", "GET TIME_STATUS_NP"]
    try:
        # Execute the command
        result = subprocess.run(cmd, capture_output=True, text=True)
        # Check if the command was successful
        if result.returncode == 0:
            # Parse the output to find the grandmasterIdentity
            for line in result.stdout.split('\n'):
                if "gmIdentity" in line:
                    grandmaster_id = line.split(':')[-1].strip()
                    print(f"Grandmaster Identity: {grandmaster_id}")
                    return grandmaster_id
        else:
            print("Failed to get data:", result.stderr)
    except Exception as e:
        print("An error occurred:", e)

if __name__ == "__main__":
    get_grandmaster_address()