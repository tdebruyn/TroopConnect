1. Get a VPS with Red Hat Enterprise Linux, AlmaLinux or Rocky Linux
2. Create a A DNS record (with your registrar) and PTR record (with your VPS provider, who can also be your DNS registrar)
3. Create a user with sudo access
4. Configure the user for password-less SSH
5. Download this repo on your local computer
6. Rename the "deploy/ansible/config.yml-example" file to "config.yml" and run "python deploy/ansible/create-config.py" to update its values
7. Rename inventory.ini.example to inventory.ini and update the values
8. Run the Ansible playbook with "ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbook.yml"
9. Put the content of the "/var/lib/docker/volumes/troopconnect_dkim/\_data/yourdomain/default.txt" file as a TXT record in DNS (check DKIM guide)
