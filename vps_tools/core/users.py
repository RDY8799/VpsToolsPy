import datetime
import os
import subprocess
from typing import List, Dict

try:
    import pwd
except ImportError:
    pwd = None


class UserManager:
    @staticmethod
    def list_users() -> List[Dict]:
        """List all users with UID > 999 (normal users)."""
        if pwd is None:
            return []
        users = []
        for user in pwd.getpwall():
            if user.pw_uid > 999 and user.pw_name != "nobody":
                try:
                    expiry = UserManager.get_user_expiry(user.pw_name)
                    password = UserManager.get_stored_password(user.pw_name)
                    limit = UserManager.get_user_limit(user.pw_name)
                    users.append(
                        {
                            "username": user.pw_name,
                            "uid": user.pw_uid,
                            "expiry": expiry,
                            "password": password,
                            "limit": limit,
                            "connected": UserManager.get_user_connections(user.pw_name),
                        }
                    )
                except Exception:
                    continue
        return users

    @staticmethod
    def get_user_expiry(username: str) -> str:
        try:
            result = subprocess.check_output(["chage", "-l", username], text=True)
            for line in result.split("\n"):
                if "Account expires" in line:
                    expiry = line.split(":")[1].strip()
                    return expiry if expiry != "never" else "Never"
        except Exception:
            return "Unknown"
        return "Unknown"

    @staticmethod
    def get_stored_password(username: str) -> str:
        """Reads stored password if available (emulating Bash behavior)."""
        path = f"/etc/rdy/mpass/{username}"
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read().strip()
        return "Unknown"

    @staticmethod
    def get_user_limit(username: str) -> str:
        path = f"/etc/rdy/limit/{username}"
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read().strip()
        return "?"

    @staticmethod
    def get_user_connections(username: str) -> int:
        try:
            output = subprocess.check_output(["ps", "-u", username], text=True)
            return output.count("sshd")
        except Exception:
            return 0

    @staticmethod
    def create_user(username, password, days, limit):
        try:
            expiry_date = (
                    datetime.date.today() + datetime.timedelta(days=int(days))
            ).strftime("%Y-%m-%d")
            subprocess.run(
                ["useradd", "-M", "-s", "/bin/false", username, "-e", expiry_date],
                check=True,
            )

            p = subprocess.Popen(
                ["passwd", username],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            p.communicate(input=f"{password}\n{password}\n")

            os.makedirs("/etc/rdy/mpass", exist_ok=True)
            os.makedirs("/etc/rdy/limit", exist_ok=True)
            os.makedirs("/etc/rdy/mdate", exist_ok=True)

            with open(f"/etc/rdy/mpass/{username}", "w") as f:
                f.write(password)
            with open(f"/etc/rdy/limit/{username}", "w") as f:
                f.write(str(limit))
            with open(f"/etc/rdy/mdate/{username}", "w") as f:
                f.write(expiry_date)

            return True
        except Exception as e:
            return str(e)

    @staticmethod
    def delete_user(username):
        try:
            subprocess.run(["userdel", "--force", username], check=True)
            for folder in ["mpass", "limit", "mdate", "time", "usuarios"]:
                path = f"/etc/rdy/{folder}/{username}"
                if os.path.exists(path):
                    if os.path.isdir(path):
                        import shutil

                        shutil.rmtree(path)
                    else:
                        os.remove(path)
            return True
        except Exception as e:
            return str(e)

    @staticmethod
    def disconnect_user(username):
        try:
            subprocess.run(["pkill", "-9", "-u", username], check=True)
            return True
        except Exception:
            return False

    @staticmethod
    def change_password(username, new_password):
        try:
            p = subprocess.Popen(
                ["passwd", username],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            p.communicate(input=f"{new_password}\n{new_password}\n")

            path = f"/etc/rdy/mpass/{username}"
            if os.path.exists(path):
                with open(path, "w") as f:
                    f.write(new_password)
            return True
        except Exception as e:
            return str(e)

    @staticmethod
    def change_limit(username, new_limit):
        path = f"/etc/rdy/limit/{username}"
        try:
            with open(path, "w") as f:
                f.write(str(new_limit))
            return True
        except Exception as e:
            return str(e)

    @staticmethod
    def change_expiry(username, year, month, day):
        try:
            expiry_date = f"{year}/{month}/{day}"
            subprocess.run(["chage", "-E", expiry_date, username], check=True)

            path = f"/etc/rdy/mdate/{username}"
            if os.path.exists(path):
                with open(path, "w") as f:
                    f.write(f"{year}-{month}-{day}")
            return True
        except Exception as e:
            return str(e)

    @staticmethod
    def backup_users(filename: str) -> str:
        backup_dir = "/etc/rdy/backups"
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%d-%m-%Y-%H%M%S")
        backup_path = f"{backup_dir}/{filename}_{timestamp}.bak"

        users = UserManager.list_users()
        try:
            with open(backup_path, "w") as f:
                for user in users:
                    # Format: username:password:limit:expiry
                    line = f"{user['username']}:{user['password']}:{user['limit']}:{user['expiry']}\n"
                    f.write(line)
            return backup_path
        except Exception as e:
            return f"Erro ao criar backup: {str(e)}"

    @staticmethod
    def restore_backup(filepath: str) -> bool:
        if pwd is None:
            return False
        if not os.path.exists(filepath):
            return False

        try:
            with open(filepath, "r") as f:
                for line in f:
                    if not line.strip():
                        continue
                    parts = line.strip().split(":")
                    if len(parts) >= 4:
                        username, password, limit, expiry = parts[:4]
                        # Check if user already exists
                        try:
                            pwd.getpwnam(username)
                        except KeyError:
                            # Use current logic for creation
                            subprocess.run(
                                ["useradd", "-M", "-s", "/bin/false", username],
                                check=True,
                            )
                            p = subprocess.Popen(
                                ["passwd", username],
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True,
                            )
                            p.communicate(input=f"{password}\n{password}\n")

                            os.makedirs("/etc/rdy/mpass", exist_ok=True)
                            os.makedirs("/etc/rdy/limit", exist_ok=True)
                            with open(f"/etc/rdy/mpass/{username}", "w") as f_meta:
                                f_meta.write(password)
                            with open(f"/etc/rdy/limit/{username}", "w") as f_meta:
                                f_meta.write(limit)
            return True
        except Exception as e:
            print(f"Erro ao restaurar: {str(e)}")
            return False
