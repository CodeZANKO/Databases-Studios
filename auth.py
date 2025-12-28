from functools import wraps
from flask import session, redirect, flash # type: ignore

def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if "db" in session:
            return f(*args, **kwargs)
        flash("Please login first", "warning")
        return redirect("/")
    return wrap

def role_required(roles=[]):
    """
    Decorator to restrict access based on user roles.
    Usage:
        @role_required(["admin", "manager"])
    """
    def decorator(f):
        @wraps(f)
        def wrap(*args, **kwargs):
            user_role = session.get("role")
            if user_role in roles:
                return f(*args, **kwargs)
            flash("You do not have permission to access this page", "danger")
            return redirect("/dashboard")
        return wrap
    return decorator

