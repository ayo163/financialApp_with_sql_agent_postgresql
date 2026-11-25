
import os
import json
import pandas as pd
import plotly.express as px
import sqlglot

from sqlglot import exp
from sqlalchemy import create_engine, text
from langchain_core.tools import tool
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, URL

load_dotenv()


# IMPORTANT: Use a PostgreSQL user with
# SELECT-only permissions on approved tables.

DATABASE_URL = URL.create(
    drivername="postgresql+psycopg",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5432")),
    database=os.getenv("DB_NAME")
)

engine = create_engine(DATABASE_URL)

ALLOWED_TABLES = {"account", "transaction"}


def validate_chart_sql(sql):

    statements = sqlglot.parse(
        sql, read="postgres"
    )

    if len(statements) != 1:
        raise ValueError("Only one query is allowed")

    statement = statements[0]

    if not isinstance(statement, exp.Select):
        raise ValueError("Only SELECT is allowed")

    forbidden = (
        exp.Insert, exp.Update, exp.Delete,
        exp.Create, exp.Drop, exp.Alter,
        exp.Command, exp.Union,
        exp.Intersect, exp.Except,
        exp.Subquery, exp.With,
    )

    for node in statement.walk():
        if isinstance(node, forbidden):
            raise ValueError("Unsupported SQL operation")

    tables = list(statement.find_all(exp.Table))

    if not tables:
        raise ValueError("No database table specified")

    for table in tables:
        if table.name.lower() not in ALLOWED_TABLES:
            raise ValueError("Table is not permitted")

        if table.db and table.db.lower() != "public":
            raise ValueError("Schema is not permitted")

    return statement.sql(dialect="postgres")


@tool
def plot_sql_chart(
    sql: str,
    chart_type: str,
    x_column: str,
    y_column: str,
    title: str
) -> str:
    """
    Generate an interactive Plotly chart using
    PostgreSQL query results.

    Use this tool when the user requests a graph,
    chart, plot, or data visualization.

    Parameters:
    sql: Read-only SELECT query returning chart data.
    chart_type: bar, line, or pie.
    x_column: SQL result column for categories.
    y_column: SQL result column for numeric values.
    title: Chart title.

    Return Plotly JSON chart data.
    """

    try:
        if chart_type not in ("bar", "line", "pie"):
            raise ValueError("Unsupported chart type")

        safe_sql = validate_chart_sql(sql)

        # Enforce a maximum of 100 result rows
        limited_sql = f"""
            SELECT *
            FROM ({safe_sql}) AS chart_results
            LIMIT 100
        """

        with engine.begin() as conn:

            conn.execute(
                text("SET TRANSACTION READ ONLY")
            )

            conn.execute(
                text(
                    "SET LOCAL statement_timeout = '5000ms'"
                )
            )

            df = pd.read_sql(
                text(limited_sql),
                conn
            )

        if df.empty:
            return json.dumps({
                "status": "empty",
                "message": "No data found"
            })

        if (
            x_column not in df.columns
            or y_column not in df.columns
        ):
            raise ValueError("Invalid chart columns")

        df[y_column] = pd.to_numeric(
            df[y_column],
            errors="raise"
        )

        if chart_type == "bar":

            fig = px.bar(
                df,
                x=x_column,
                y=y_column,
                title=title
            )

        elif chart_type == "line":

            fig = px.line(
                df,
                x=x_column,
                y=y_column,
                title=title,
                markers=True
            )

        else:

            fig = px.pie(
                df,
                names=x_column,
                values=y_column,
                title=title
            )

        fig.update_layout(
            template="plotly_white",
            autosize=True
        )

        return json.dumps({
            "status": "success",
            "chart": json.loads(fig.to_json())
        })

    except Exception as e:

        return json.dumps({
            "status": "error",
            "message": str(e)
        })
