def get_columns(cur, table):
    cur.execute(f"SHOW COLUMNS FROM `{table}`")
    return [c['Field'] for c in cur.fetchall()]

def has_permission(role, action):
    from models import ROLE_PERMISSIONS
    return action in ROLE_PERMISSIONS.get(role, [])
