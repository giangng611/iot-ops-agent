import os

from storage.relational_store import (
    change_user_password,
    create_user,
    delete_user_account,
    get_user_by_username,
    update_username,
    verify_user,
)


def authenticate_user(username, password):
    return verify_user(username, password)


def register_user(username, password, access_code):
    required_code = os.getenv("ACCESS_CODE")

    if not required_code:
        return False, "Invalid access code", 500

    if access_code != required_code:
        return False, "Invalid access code", 403

    try:
        create_user(username, password)
    except Exception:
        return False, "Username already exists", 400

    return True, "registered", 200


def change_password(user_id, current_password, new_password):
    return change_user_password(user_id, current_password, new_password)


def change_username(user_id, new_username):
    if get_user_by_username(new_username):
        return False, "Username already exists"

    if not update_username(user_id, new_username):
        return False, "Unable to update username"

    return True, "Username updated successfully"


def delete_account(user_id, username, password):
    user = verify_user(username, password)

    if not user:
        return False, "Password is incorrect"

    if not delete_user_account(user_id):
        return False, "Unable to delete account"

    return True, "Account deleted"
