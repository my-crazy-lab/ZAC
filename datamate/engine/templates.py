"""Khung SQL theo intent (EXECUTION-MVP.md §4.5).

Ký hiệu: ``{AS_OF}`` = ngày của câu hỏi; ``{TIME}`` = vị từ thời gian;
``{FILTER}`` = vị từ filters; ``{SUBJ_CODE}``/``{SUBJ_NAME}``/``{SUBJ_VALID}``.
"""

from __future__ import annotations

T1 = """SELECT {VALUE_EXPR} AS value
FROM {SOURCE} s
WHERE {TIME} AND {FILTER} AND s.{DATE_COL} <= {AS_OF}"""

T2 = """WITH g AS (
  SELECT {SUBJ_CODE} AS code, {SUBJ_NAME} AS name, {VALUE_EXPR} AS value
  FROM {SOURCE} s
  WHERE {TIME} AND {FILTER} AND {SUBJ_VALID} AND s.{DATE_COL} <= {AS_OF}
  GROUP BY 1, 2
  {HAVING}
)
SELECT name, value, code FROM g
ORDER BY value {DIR}, code ASC
{LIMIT_PLUS_1}"""

T3 = """WITH m AS (
  SELECT {VALUE_EXPR} AS v FROM {SOURCE} s
  WHERE {TIME_MAIN} AND {FILTER} AND s.{DATE_COL} <= {AS_OF}
), b AS (
  SELECT {VALUE_EXPR} AS v FROM {SOURCE} s
  WHERE {TIME_BASE} AND {FILTER} AND s.{DATE_COL} <= {AS_OF}
)
SELECT CASE WHEN '{MODE}' = 'pct'
            THEN (m.v - b.v) * 100.0 / NULLIF(b.v, 0)
            ELSE (m.v - b.v) END AS value
FROM m, b"""

T3_SUBJECT = """WITH m AS (
  SELECT {SUBJ_CODE} AS code, {SUBJ_NAME} AS name, {VALUE_EXPR} AS v FROM {SOURCE} s
  WHERE {TIME_MAIN} AND {FILTER} AND {SUBJ_VALID} AND s.{DATE_COL} <= {AS_OF}
  GROUP BY 1, 2
), b AS (
  SELECT {SUBJ_CODE} AS code, {SUBJ_NAME} AS name, {VALUE_EXPR} AS v FROM {SOURCE} s
  WHERE {TIME_BASE} AND {FILTER} AND {SUBJ_VALID} AND s.{DATE_COL} <= {AS_OF}
  GROUP BY 1, 2
)
SELECT m.name AS name,
       CASE WHEN '{MODE}' = 'pct'
            THEN (m.v - b.v) * 100.0 / NULLIF(b.v, 0)
            ELSE (m.v - b.v) END AS value,
       m.code AS code
FROM m FULL JOIN b ON m.code = b.code
ORDER BY value {DIR}, code ASC
{LIMIT_PLUS_1}"""

T4 = """{UNION_ALL}"""

T7 = """WITH g AS (
  SELECT {SUBJ_CODE} AS code, {SUBJ_NAME} AS name, {VALUE_EXPR} AS value
  FROM {SOURCE} s
  WHERE {TIME} AND {FILTER} AND {SUBJ_VALID} AND s.{DATE_COL} <= {AS_OF}
  GROUP BY 1, 2
), tot AS (
  SELECT {VALUE_EXPR} AS value FROM {SOURCE} s
  WHERE {TIME} AND s.{DATE_COL} <= {AS_OF}
)
SELECT g.name AS name, g.value * 100.0 / NULLIF(tot.value, 0) AS value, g.code AS code
FROM g, tot
ORDER BY value {DIR}, code ASC
{LIMIT_PLUS_1}"""

# T6 — tại một thời điểm (theo metric)
POINT_STOCK = """WITH snap AS (
  SELECT s.product_code, s.inv_qty, s.inv_date
  FROM v_inventory s
  WHERE s.inv_date <= {CUTOFF}
  QUALIFY ROW_NUMBER() OVER (PARTITION BY s.product_code ORDER BY s.inv_date DESC) = 1
)
SELECT s.product_code AS code,
       (SELECT p.product_name FROM v_products p WHERE p.product_code = s.product_code) AS name,
       SUM(s.inv_qty) AS value
FROM snap s
GROUP BY 1, 2
ORDER BY value {DIR}, code ASC
{LIMIT_PLUS_1}"""

POINT_STOCK_LOTS = """WITH sold AS (
  SELECT COALESCE(l.product_code, '') AS product_code,
         SUM(COALESCE(l.qty_base, l.qty)) AS sold_qty
  FROM v_lines l WHERE l.order_date <= {CUTOFF} GROUP BY 1
), lots_in AS (
  SELECT product_code, lot_date, lot_qty, lot_cost FROM v_lots WHERE lot_date <= {CUTOFF}
)
SELECT s.product_code AS code,
       (SELECT p.product_name FROM v_products p WHERE p.product_code = s.product_code) AS name,
       SUM(s.stock) AS value
FROM (
  SELECT product_code, SUM(lot_qty) AS stock FROM lots_in GROUP BY 1
) s LEFT JOIN sold ON sold.product_code = s.product_code
GROUP BY 1, 2
ORDER BY value {DIR}, code ASC
{LIMIT_PLUS_1}"""

POINT_DEBT = """WITH bal AS (
  SELECT s.customer_key AS code,
         (SELECT c.customer_name FROM v_customers c WHERE c.customer_key = s.customer_key) AS name,
         SUM(s.delta) AS value
  FROM v_debt_events s
  WHERE s.event_date <= {CUTOFF}
  GROUP BY 1, 2
  HAVING SUM(s.delta) > 0
)
SELECT name, value, code FROM bal
ORDER BY value {DIR}, code ASC
{LIMIT_PLUS_1}"""

POINT_DEBT_AGE = """WITH owed AS (
  SELECT s.customer_key AS code,
         (SELECT c.customer_name FROM v_customers c WHERE c.customer_key = s.customer_key) AS name,
         MIN(s.event_date) AS first_date
  FROM v_debt_events s
  WHERE s.event_date <= {CUTOFF} AND s.kind = 'order' AND s.delta > 0
  GROUP BY 1, 2
), paid AS (
  SELECT s.customer_key AS code, SUM(-s.delta) AS paid
  FROM v_debt_events s
  WHERE s.event_date <= {CUTOFF} AND s.kind = 'payment'
  GROUP BY 1
)
SELECT o.name AS name,
       DATE_DIFF('day', o.first_date, DATE '{CUTOFF}') AS value,
       o.code AS code
FROM owed o LEFT JOIN paid p ON p.code = o.code
WHERE COALESCE(o.delta_sum, 0) >= 0
ORDER BY value {DIR}, code ASC
{LIMIT_PLUS_1}"""

POINT_EXPIRING = """SELECT s.product_code AS code,
       (SELECT p.product_name FROM v_products p WHERE p.product_code = s.product_code) AS name,
       SUM(s.lot_qty) AS value
FROM v_lots s
WHERE s.expiry_date BETWEEN DATE '{CUTOFF}' AND DATE '{CUTOFF}' + INTERVAL {DAYS} DAY
GROUP BY 1, 2
ORDER BY value {DIR}, code ASC
{LIMIT_PLUS_1}"""
