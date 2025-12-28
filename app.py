from flask import Flask, render_template, request, session, redirect, flash, jsonify,send_file
from db import connect_db
from auth import login_required, role_required
from models import log_query, ROLE_PERMISSIONS
from utils import get_columns, has_permission
import os
import io
import csv
import mysql.connector



app = Flask(__name__)
app.secret_key = "supersecret"

# LOGIN
@app.route("/", methods=["GET","POST"])
def login():
    if request.method=="POST":
        host = request.form["host"]
        user = request.form["username"]
        password = request.form["password"]
        dbname = request.form["dbname"]

        conn = connect_db({"host":host,"user":user,"password":password,"database":dbname})
        if conn:
            session["db"] = {"host":host,"user":user,"password":password,"database":dbname}
            session["role"] = "admin"  # default role
            return redirect("/dashboard")
        flash("Connection failed")
    return render_template("login.html")

# DASHBOARD
@app.route("/dashboard")
@login_required
def dashboard():
    conn = connect_db(session["db"])
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    tables = [t[0] for t in cur.fetchall()]
    return render_template("dashboard.html", tables=tables)

# TABLE VIEW + INLINE EDIT
@app.route("/table/<name>", methods=["GET","POST"])
@login_required
def table_view(name):
    conn = connect_db(session["db"])
    cur = conn.cursor(dictionary=True)

    search = request.form.get("search","")
    columns = get_columns(cur,name)
    query = f"SELECT * FROM `{name}`"
    if search:
        query += " WHERE " + " OR ".join([f"`{c}` LIKE '%{search}%'" for c in columns])


    cur.execute(query)
    rows = cur.fetchall()
    curtables = conn.cursor()
    curtables.execute("SHOW TABLES")
    tables = [t[0] for t in curtables.fetchall()]
    return render_template("table.html", name=name, rows=rows, columns=columns, pk=columns[0], tables=tables)

# INLINE UPDATE
@app.route("/inline-update/<table>/<pk>", methods=["POST"])
@login_required
def inline_update(table, pk):
    col = request.form["column"]
    value = request.form["value"]

    if not has_permission(session["role"], "UPDATE"):
        return "Permission denied", 403

    conn = connect_db(session["db"])
    cur = conn.cursor()
    pk_col = get_columns(cur, table)[0]
    cur.execute(f"UPDATE `{table}` SET `{col}`=%s WHERE `{pk_col}`=%s",(value,pk))
    conn.commit()
    log_query(session["db"]["user"], f"UPDATE {table} SET {col}={value} WHERE {pk_col}={pk}")
    return value

# SQL EDITOR
@app.route("/sql", methods=["GET","POST"])
@login_required
def sql_editor():
    result = None
    error = None
    if request.method=="POST":
        query = request.form["query"]
        if not has_permission(session["role"], query.strip().split()[0].upper()):
            error = "Permission denied"
        else:
            conn = connect_db(session["db"])
            cur = conn.cursor(dictionary=True)
            try:
                cur.execute(query)
                if query.strip().upper().startswith("SELECT"):
                    result = cur.fetchall()
                else:
                    conn.commit()
                log_query(session["db"]["user"], query)
            except Exception as e:
                error = str(e)

    conn = connect_db(session["db"])
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    tables = [t[0] for t in cur.fetchall()]
    return render_template("sql.html", result=result, error=error,tables=tables)

# QUERY HISTORY
@app.route("/history")
@login_required
def history():
    from models import QUERY_HISTORY
    conn = connect_db(session["db"])
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    tables = [t[0] for t in cur.fetchall()]
    return render_template("history.html", rows=QUERY_HISTORY,tables=tables)


@app.route("/er-graph")
@login_required
def er_graph():
    conn = connect_db(session["db"])
    cur = conn.cursor()
    cur.execute("SELECT table_name,column_name,referenced_table_name,referenced_column_name "
                "FROM information_schema.key_column_usage "
                "WHERE referenced_table_name IS NOT NULL AND table_schema=%s",
                (session["db"]["database"],))
    relations = cur.fetchall()
    curtable = conn.cursor()
    curtable.execute("SHOW TABLES")
    tables = [t[0] for t in curtable.fetchall()]
    return render_template("er_graph.html", relations=relations, tables=tables)



# Edit row
@app.route("/table/<table>/edit", methods=["POST"])
@login_required
def edit_row(table):
    data = request.json  # expects: {"id": 1, "column": "name", "value": "new_value"}
    row_id = data.get("id")
    column = data.get("column")
    value = data.get("value")

    if not row_id or not column:
        return jsonify({"status":"error","msg":"Invalid parameters"}), 400

    conn = connect_db(session["db"])
    cur = conn.cursor()
    try:
        cur.execute(f"UPDATE `{table}` SET `{column}`=%s WHERE id=%s", (value, row_id))
        conn.commit()
        return jsonify({"status":"success"})
    except Exception as e:
        return jsonify({"status":"error","msg":str(e)}), 500


# Delete row
@app.route("/table/<table>/delete", methods=["POST"])
@login_required
def delete_row(table):
    data = request.json  # expects: {"id": 1}
    row_id = data.get("id")
    if not row_id:
        return jsonify({"status":"error","msg":"Invalid ID"}), 400

    conn = connect_db(session["db"])
    cur = conn.cursor()
    try:
        cur.execute(f"DELETE FROM `{table}` WHERE id=%s", (row_id,))
        conn.commit()
        return jsonify({"status":"success"})
    except Exception as e:
        return jsonify({"status":"error","msg":str(e)}), 500


@app.route("/indexes/<table>")
@login_required
def indexes(table):
    conn = connect_db(session["db"])
    cur = conn.cursor(dictionary=True)
    cur.execute(f"SHOW INDEX FROM `{table}`")
    indexes = cur.fetchall()
    return render_template("indexes.html", table=table, indexes=indexes)



@app.route("/audit")
@login_required
@role_required(["admin"])
def audit_logs():
    from models import AUDIT_LOGS
    conn = connect_db(session["db"])
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    tables = [t[0] for t in cur.fetchall()]
    return render_template("audit.html", logs=AUDIT_LOGS, tables=tables)




@app.route("/export", methods=["GET", "POST"])
@login_required
def export_db():
    # Get db session safely
    db_session = session.get("db")
    if not db_session:
        flash("Please login first", "warning")
        return redirect("/login")

    # Connect to MySQL
    conn = connect_db(db_session)
    if not conn:
        flash("Database connection failed!", "danger")
        return redirect("/dashboard")

    cur = conn.cursor()

    # Get list of tables
    cur.execute("SHOW TABLES")
    tables = [t[0] for t in cur.fetchall()]

    # Handle POST export request
    if request.method == "POST":
        dbname = request.form.get("dbname")
        export_type = request.form.get("export_type")

        if not dbname or not export_type:
            flash("Please select database and export type", "warning")
            return redirect("/export")

        # Reconnect to selected database (use your connect_db function)
        export_conn = connect_db({
            "host": db_session["host"],
            "user": db_session["user"],
            "password": db_session["password"],
            "database": dbname
        })
        if not export_conn:
            flash("Failed to connect to selected database", "danger")
            return redirect("/export")

        export_cur = export_conn.cursor()

        if export_type == "csv":
            output = io.StringIO()
            for table in tables:
                export_cur.execute(f"SELECT * FROM `{table}`")
                rows = export_cur.fetchall()
                if not rows:
                    continue
                writer = csv.writer(output)
                # Write header
                writer.writerow([i[0] for i in export_cur.description])
                # Write data
                writer.writerows(rows)
                writer.writerow([])  # empty line between tables
            output.seek(0)
            return send_file(
                io.BytesIO(output.getvalue().encode()),
                mimetype="text/csv",
                download_name=f"{dbname}.csv",
                as_attachment=True
            )

        elif export_type == "sql":
            sql_dump = ""
            for table in tables:
                export_cur.execute(f"SHOW CREATE TABLE `{table}`")
                create_stmt = export_cur.fetchone()[1]
                sql_dump += f"{create_stmt};\n\n"

                export_cur.execute(f"SELECT * FROM `{table}`")
                rows = export_cur.fetchall()
                if rows:
                    for row in rows:
                        values = ",".join([
                            f"'{str(v).replace('\'','\\\'')}'" if v is not None else "NULL"
                            for v in row
                        ])
                        sql_dump += f"INSERT INTO `{table}` VALUES ({values});\n"
                sql_dump += "\n"

            return send_file(
                io.BytesIO(sql_dump.encode()),
                mimetype="application/sql",
                download_name=f"{dbname}.sql",
                as_attachment=True
            )

    return render_template("export.html", tables=tables)


@app.route("/import/<table>", methods=["GET","POST"])
@login_required
def import_csv(table):
    if request.method=="POST":
        file = request.files["file"]
        if file:
            conn = connect_db(session["db"])
            cur = conn.cursor()
            reader = csv.reader(io.StringIO(file.stream.read().decode()))
            cols = next(reader)
            for row in reader:
                cur.execute(f"INSERT INTO `{table}` ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})", row)
            conn.commit()
            flash("Imported successfully")

    conn = connect_db(session["db"])
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    tables = [t[0] for t in cur.fetchall()]
    return render_template("import.html", table=table, tables=tables)

@app.route("/switch-db", methods=["GET","POST"])
@login_required
def switch_db():
    if request.method=="POST":
        dbname = request.form["dbname"]
        session["db"]["database"] = dbname
        flash(f"Switched to database: {dbname}")
        return redirect("/dashboard")
    conn = connect_db(session["db"])
    cur = conn.cursor()
    # curtables = conn.cursor()
    cur.execute("SHOW DATABASES")
    # curtables.execute("SHOW TABLES")
    # tables = [t[0] for t in curtables.fetchall()]
    databases = [d[0] for d in cur.fetchall()]
    return render_template("switch_db.html", databases=databases)

@app.route("/about")
@login_required
def about():
    return render_template("about.html")    


# LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__=="__main__":
    app.run(debug=True)
