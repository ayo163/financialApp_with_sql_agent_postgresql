
import os
import json
import time
import asyncio
import logging
import markdown
import bleach

import load_env_vars

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_core.messages import ToolMessage

from tools import plot_sql_chart
from agent_toolkit import tools


# ==========================================
# LOGGING
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


# ==========================================
# FASTAPI CONFIGURATION
# ==========================================

app = FastAPI(title="AI SQL Agent")

templates = Jinja2Templates(
    directory="templates"
)

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)


# ==========================================
# OPENAI MODEL
# ==========================================

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise RuntimeError(
        "OPENAI_API_KEY is not configured"
    )

model = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=api_key,
    temperature=0,
    timeout=30,
    max_retries=1
)


# ==========================================
# SQL AGENT + PLOTLY TOOL
# ==========================================

all_tools = list(tools) + [plot_sql_chart]

agent = create_agent(
    model=model,
    tools=all_tools,
    system_prompt="""
    You are an AI PostgreSQL SQL assistant.

    Your responsibility is to answer questions
    accurately using the PostgreSQL database.

    DATABASE RULES:
    - All monetary values are in Nigerian Naira.
    - Display monetary values using ₦.
    - Format monetary values to two decimal places.
    - Use commas as thousand separators.
    - Present multiple records in Markdown tables.
    - Never invent database values.

    SQL RULES:
    - Use database tools to inspect the schema.
    - Use SELECT queries only.
    - Do not modify database records.
    - Never execute INSERT, UPDATE, DELETE,
      DROP, ALTER, TRUNCATE, or CREATE.

    VISUALIZATION RULES:
    - Only use plot_sql_chart when the user
      requests a chart, graph, or visualization.
    - Use bar charts for category comparisons.
    - Use line charts for trends over time.
    - Use pie charts for proportions.
    - Generate SQL queries using actual
      database tables and columns.
    - Ensure x_column and y_column match
      the returned SQL column aliases.
    - Do not invent chart data.
    - Call plot_sql_chart at most once
      per user request.
    - After the chart tool returns successfully,
      provide a short explanation and finish.
    - If chart generation fails, explain why.
    - Do not repeatedly retry failed tools.

    RESPONSE RULES:
    - Give clear and concise answers.
    - Do not expose raw tool JSON.
    - Do not include Plotly JSON in the answer.
    """
)


# ==========================================
# REQUEST MODEL
# ==========================================

class QuestionRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=2000
    )


# ==========================================
# HOME PAGE
# ==========================================

@app.get("/", response_class=HTMLResponse)
def home(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


# ==========================================
# FORMAT AGENT ANSWER
# ==========================================

def format_answer(answer: str):

    html = markdown.markdown(
        answer,
        extensions=["tables", "fenced_code"]
    )

    return bleach.clean(
        html,
        tags=[
            "p", "br", "strong", "em",
            "h1", "h2", "h3",
            "ul", "ol", "li",
            "table", "thead", "tbody",
            "tr", "th", "td",
            "code", "pre", "blockquote"
        ],
        strip=True
    )


# ==========================================
# EXTRACT PLOTLY CHART
# ==========================================

def extract_chart(messages):

    chart = None
    chart_error = None

    for message in messages:

        if not isinstance(message, ToolMessage):
            continue

        if message.name != "plot_sql_chart":
            continue

        try:
            result = json.loads(message.content)

            if result.get("status") == "success":
                chart = result.get("chart")

            elif result.get("status") == "error":
                chart_error = result.get("message")

            elif result.get("status") == "empty":
                chart_error = result.get("message")

        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Invalid Plotly tool response"
            )

    return chart, chart_error


# ==========================================
# SQL AGENT ENDPOINT
# ==========================================

@app.post("/ask")
async def ask_agent(data: QuestionRequest):

    start = time.perf_counter()

    logger.info(
        "Question received: %s",
        data.question
    )

    try:

        # Run the synchronous agent in a worker
        # thread so it doesn't block the event loop.
        result = await asyncio.wait_for(
            asyncio.to_thread(
                agent.invoke,
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": data.question
                        }
                    ]
                },
                config={"recursion_limit": 12}
            ),
            timeout=90
        )

        elapsed = time.perf_counter() - start

        logger.info(
            "Agent completed in %.2f seconds",
            elapsed
        )

        messages = result.get("messages", [])

        if not messages:
            raise ValueError(
                "Agent returned no messages"
            )

        # Extract final AI response
        answer = messages[-1].content

        if not isinstance(answer, str):
            answer = str(answer)

        # Extract Plotly chart
        chart, chart_error = extract_chart(
            messages
        )

        # Log chart status
        if chart:
            logger.info(
                "Plotly chart generated successfully"
            )

        if chart_error:
            logger.warning(
                "Plotly chart error: %s",
                chart_error
            )

        formatted_answer = format_answer(
            answer
        )

        return {
            "question": data.question,
            "answer": formatted_answer,
            "chart": chart,
            "chart_error": chart_error,
            "execution_time": round(elapsed, 2)
        }

    except asyncio.TimeoutError:

        logger.error(
            "SQL Agent timed out"
        )

        raise HTTPException(
            status_code=504,
            detail=(
                "The SQL Agent took too long "
                "to respond. Please try again."
            )
        )

    except Exception:

        logger.exception(
            "SQL Agent execution failed"
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to process your question. "
                "Check the server logs."
            )
        )
