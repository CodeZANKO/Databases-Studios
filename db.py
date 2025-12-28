import mysql.connector
from mysql.connector import Error

def connect_db(db_config):
    """
    Connects to a MySQL database using the provided configuration.

    db_config = {
        "host": "...",
        "user": "...",
        "password": "...",
        "database": "..."  # Optional: can be None for multi-db operations
    }

    Returns:
        mysql.connector connection object if successful, None otherwise
    """
    try:
        conn = mysql.connector.connect(
            host=db_config.get("host"),
            user=db_config.get("user"),
            password=db_config.get("password"),
            database=db_config.get("database"),  # can be None
            auth_plugin='mysql_native_password'
        )
        if conn.is_connected():
            print(f"Connected to MySQL database: {db_config.get('database')}")
            return conn
        else:
            print("Failed to connect to the database.")
            return None
    except Error as e:
        print("DB Connection Error:", e)
        return None
