from datetime import datetime

QUERY_HISTORY = []  # store last queries
AUDIT_LOGS = []     # track actions

ROLE_PERMISSIONS = {
    "admin": ["SELECT","INSERT","UPDATE","DELETE","DDL"],
    "editor": ["SELECT","INSERT","UPDATE"],
    "viewer": ["SELECT"]
}

def log_query(user, query):
    AUDIT_LOGS.append({
        "user": user,
        "query": query,
        "time": datetime.now()
    })
    QUERY_HISTORY.append({
        "user": user,
        "query": query,
        "time": datetime.now()
    })
