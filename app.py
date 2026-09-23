import sqlite3
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")
DB_PATH = "tracker.db"

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

def get_report_data():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Получение товаров, зафиксированных строго во время последнего прогона парсера
        products = cursor.execute("""
            WITH LatestRun AS (
                SELECT MAX(recorded_at) as max_date FROM price_history
            ),
            RankedPrices AS (
                SELECT 
                    p.id, p.title, p.url, h.price, h.recorded_at,
                    LAG(h.price) OVER (PARTITION BY p.id ORDER BY h.recorded_at ASC) as prev_price,
                    ROW_NUMBER() OVER (PARTITION BY p.id ORDER BY h.recorded_at DESC) as rn
                FROM products p
                JOIN price_history h ON h.product_id = p.id
            )
            SELECT 
                r.id,
                r.title, r.url, r.price as current_price,
                (r.price - r.prev_price) as price_diff,
                r.recorded_at
            FROM RankedPrices r
            JOIN LatestRun lr ON r.recorded_at = lr.max_date
            WHERE r.rn = 1
            ORDER BY current_price DESC;
        """).fetchall()

        history = cursor.execute("""
            SELECT product_id, price, recorded_at
            FROM price_history
            ORDER BY recorded_at ASC
        """).fetchall()

    return products, history

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    products, history = get_report_data()

    labels = sorted(list(set(row["recorded_at"] for row in history)))
    chart_datasets = []

    colors = [
        "#2563eb", "#dc2626", "#16a34a", "#d97706", 
        "#9333ea", "#0891b2", "#4f46e5", "#be123c"
    ]

    for idx, prod in enumerate(products):
        prod_history = {
            row["recorded_at"]: row["price"] 
            for row in history if row["product_id"] == prod["id"]
        }
        data_points = [prod_history.get(ts, None) for ts in labels]

        color = colors[idx % len(colors)]
        chart_datasets.append({
            "label": prod["title"][:28] + "...",
            "data": data_points,
            "borderColor": color,
            "backgroundColor": color,
            "fill": False,
            "tension": 0.2
        })

    # Передаем request явным именованным параметром
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "products": products,
            "labels": labels,
            "datasets": chart_datasets
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)